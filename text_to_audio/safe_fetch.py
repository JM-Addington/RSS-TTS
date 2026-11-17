"""The pinned, SSRF-safe URL fetch for user-supplied URLs (article pages and followed feeds, #190).

ONE public function, fetch_url(url, ...). It runs synchronously in the calling process, bounded by
one wall clock, and returns the bytes with the final status and the Content-Type and
Content-Encoding header values. It LOGS NOTHING: each caller logs under its own codes, and a
FetchRefused carries the host to name (never the URL).

Ported from Tandem's tandem/core/utils_core_safe_fetch.py (origin/main a7a77da72) with minimal
edits: the default ports policy is {"http": 80, "https": 443}; FetchRefused carries the HTTP
``status`` for http_status (so callers keep per-status messages); the streaming ``sink`` and
``passthrough`` parameters, which nothing here used, were dropped.

AIDEV-NOTE: security; THIS is RSS-TTS's SSRF boundary for a fetched URL. The validator in
validators.py only gives early form feedback; it cannot stop redirects or rebinding. Each guard here:
  * A scheme and port from the CALLER's policy (``ports``: scheme -> its one port; default
    {"http": 80, "https": 443}); a URL with no port uses its scheme's. No userinfo, no
    whitespace/control/backslash, at most MAX_URL_LENGTH, an IDNA host. The request is built from
    the CHECKED parts only (host, ip, path+query), never re-parsed by another library.
  * A host whose LAST dot-label is all ASCII digits or 0x + hex digits, NOT a plain IPv4/IPv6
    literal (``2130706433``, ``0177.0.0.1``, ``0x7f.1``, ``1.0x7f``, ``127.1``) is refused
    ``url_host`` BEFORE any resolve, so nothing depends on libc's inet_aton leniency turning it into
    an address. Mutant M-NUMHOST (the check removed: the name reaches the resolver).
  * OUR OWN resolve (resolve_bounded, or the caller's resolver) and EVERY address validated
    (address_allowed: IPv4-mapped/compat unwrapped, 6to4 judged by its IPv4, NAT64 and Teredo
    refused), so one private record refuses the whole name. Mutant M-ALLIPS validates only the first.
  * The connect goes to the VALIDATED IP. https: urllib3's HTTPSConnectionPool at host=<ip> with
    server_hostname and assert_hostname = the name, so the certificate is still checked against the
    NAME. http: HTTPConnectionPool at host=<ip>, port 80. Both send Host: <name>. No second resolve
    can send the socket elsewhere (DNS rebinding). Mutant M-PIN connects by name.
  * No proxy: a urllib3 ConnectionPool never reads HTTP(S)_PROXY (only urllib3's ProxyManager or
    requests' trust_env would). Invalidated if this module ever uses requests,
    PoolManager.from_env or a ProxyManager. UNVERIFIED against urllib3's docs (carried from Tandem).
  * Redirects are followed BY HAND, at most MAX_REDIRECTS, and each Location goes back through the
    FULL check (scheme and port under the SAME policy; numeric host; resolve; every address; pin).
    Mutant M-HOP.
  * Size: a Content-Length over the cap is refused before the body, and a RUNNING count aborts the
    body at the cap whatever the header said. Mutant M-CAP.
  * Time: one deadline for the whole fetch, redirects and resolves included. Before each hop's
    resolve the time left is checked, and the DEFAULT resolve (resolve_bounded) waits at most
    min(RESOLVE_TIMEOUT_SECONDS, time left). urllib3's timeouts are PER RECV, so a server sending one
    byte inside each window could hold the fetch as long as it liked; the WALL CLOCK is enforced by
    Watchdog, which shuts the connection's socket down at the deadline whatever phase it is in. A
    fired watchdog is always ``timeout``. Invalidated if a connection is ever made other than through
    a pool whose ConnectionCls open_pinned wrapped (that is what arms the watchdog).
  * Content is never DECODED: decode_content=False and Accept-Encoding: identity, so a compressed
    body is counted as sent, never inflated past the cap. The Content-Type and Content-Encoding are
    RETURNED, not judged: the caller decides.
  * FetchRefused.host is a validated host (or None), never the URL, its path or its query.
"""

from __future__ import annotations

import functools
import ipaddress
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

DEFAULT_PORTS = {"http": 80, "https": 443}
# AIDEV-NOTE: 10, not Tandem's 3: real chains (doi.org -> publisher, nature.com's cookie hop) run
# past 3. Each hop is fully re-checked and shares one deadline, so the count only bounds work.
MAX_REDIRECTS = 10
TOTAL_TIMEOUT_SECONDS = 15
CONNECT_TIMEOUT_SECONDS = 5
RESOLVE_TIMEOUT_SECONDS = 3
READ_CHUNK_BYTES = 64 * 1024
MAX_URL_LENGTH = 2048
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
DEFAULT_USER_AGENT = "RSS-TTS-Fetch/1"
_HEX_LABEL = re.compile(r"0[xX][0-9a-fA-F]*")

# The closed refusal tokens (FetchRefused.code).
URL_SCHEME = "url_scheme"
URL_PORT = "url_port"
URL_HOST = "url_host"
DNS_FAILED = "dns_failed"
ADDRESS_REFUSED = "address_refused"
REDIRECT_LIMIT = "redirect_limit"
TOO_LARGE = "too_large"
TIMEOUT = "timeout"
HTTP_STATUS = "http_status"
CONNECT_FAILED = "connect_failed"
FETCH_CODES = frozenset(
    {
        URL_SCHEME,
        URL_PORT,
        URL_HOST,
        DNS_FAILED,
        ADDRESS_REFUSED,
        REDIRECT_LIMIT,
        TOO_LARGE,
        TIMEOUT,
        HTTP_STATUS,
        CONNECT_FAILED,
    }
)
#: The codes that mean "the URL or its answer was refused by policy" (never retried by callers).
POLICY_CODES = frozenset(
    {URL_SCHEME, URL_PORT, URL_HOST, ADDRESS_REFUSED, REDIRECT_LIMIT, TOO_LARGE}
)

#: IPv6 prefixes that carry an IPv4 address a NAT or tunnel would reach: refused outright,
#: because is_global is True for NAT64 even when the embedded address is private.
_NAT64 = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
)
#: Ranges ipaddress calls is_global that are not ordinary unicast destinations:
#: fec0::/10, deprecated IPv6 site-local (RFC 3879), still routed inside some sites;
#: 192.88.99.0/24, the 6to4 relay anycast (RFC 7526);
#: 168.63.129.16/32, Azure's WireServer: public, but answers only inside Azure (host metadata/agent).
#: Checked AFTER the IPv4-mapped unwrap.
_EXTRA_REFUSED = (
    ipaddress.ip_network("fec0::/10"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("168.63.129.16/32"),
)


class FetchRefused(Exception):
    """The fetch refused the URL or the answer. ``code`` is one closed token; ``host`` the validated
    host to name in a log line (the host JUDGED for address_refused, else the first hop's), or None
    when the refusal came before any host was accepted. ``status`` is the HTTP status for
    http_status, else None."""

    def __init__(
        self, code: str, host: str | None = None, status: int | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.host = host
        self.status = status


@dataclass(frozen=True)
class FetchResult:
    data: bytes
    #: The host of the URL ASKED for (the first hop), for display.
    host: str
    #: The host the bytes came from (the last hop).
    final_host: str
    redirects: int
    status: int
    #: The response's header values as sent, None when absent. Never judged here.
    content_type: str | None
    content_encoding: str | None
    #: The URL the bytes came from (after redirects): the base for relative links in the body.
    final_url: str = ""


@dataclass(frozen=True)
class _Target:
    scheme: str
    host: str
    ip: str
    port: int
    path: str


def address_allowed(raw: str) -> bool:
    """True only for a globally routable unicast address (module note)."""
    try:
        ip: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(
            str(raw).split("%", 1)[0]
        )
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if any(ip in net for net in _NAT64) or ip.teredo is not None:
            return False
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.sixtofour is not None:
            ip = ip.sixtofour
    if any(ip.version == net.version and ip in net for net in _EXTRA_REFUSED):
        return False
    return (
        ip.is_global
        and not ip.is_multicast
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def numeric_host(ascii_host: str) -> bool:
    """True for a host spelled as a number that is not a plain IP literal (module note): its LAST
    dot-label all ASCII digits, or 0x/0X followed only by hex digits. The caller tries ipaddress
    first. Only the last label is judged: inet_aton's forms (a, a.b, a.b.c, a.b.c.d) are numbers in
    EVERY part, so a non-numeric last label is never one; ``0x7f.1`` and ``1.0x7f`` are caught while
    ``0xdeadbeef.com`` is a name. UNVERIFIED against glibc's source: from inet_aton(3).
    """
    last = ascii_host.rstrip(".").rsplit(".", 1)[-1]
    return (last.isascii() and last.isdigit()) or bool(_HEX_LABEL.fullmatch(last))


def _resolve(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def resolve_bounded(host: str, timeout: float = RESOLVE_TIMEOUT_SECONDS) -> list[str]:
    """Every address ``host`` resolves to, or concurrent.futures.TimeoutError after ``timeout``
    seconds. getaddrinfo takes no timeout, so the lookup runs in a one-worker pool and is ABANDONED
    (not killed) on a timeout: the worker thread finishes on its own and its answer is discarded.
    """
    executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="safe-fetch-resolve"
    )
    try:
        return executor.submit(_resolve, host).result(timeout=max(0.0, timeout))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def checked_target(url: str, resolver, ports=None) -> _Target:  # noqa: C901
    """The (scheme, name, pinned ip, port, path) to request for ``url``, or FetchRefused."""
    ports = DEFAULT_PORTS if ports is None else ports
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        raise FetchRefused(URL_HOST)
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        raise FetchRefused(URL_HOST)
    if "\\" in url:
        raise FetchRefused(URL_HOST)
    try:
        parts = urlsplit(url)
    except ValueError:
        raise FetchRefused(URL_HOST) from None
    scheme = parts.scheme.lower()
    if scheme not in ports:
        raise FetchRefused(URL_SCHEME)
    if "@" in parts.netloc:
        raise FetchRefused(URL_HOST)
    try:
        port = parts.port
    except ValueError:
        raise FetchRefused(URL_PORT) from None
    if port not in (None, ports[scheme]):
        raise FetchRefused(URL_PORT)
    host = parts.hostname
    if not host:
        raise FetchRefused(URL_HOST)
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise FetchRefused(URL_HOST) from None
    try:
        literal = ipaddress.ip_address(ascii_host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [str(literal)]
    else:
        # AIDEV-NOTE: security; numeric/hex host forms never reach a resolver (M-NUMHOST): libc's
        # inet_aton would turn 0177.0.0.1 / 127.1 into loopback. Invalidated if this check moves
        # after the resolver call.
        if numeric_host(ascii_host):
            raise FetchRefused(URL_HOST)
        try:
            addresses = list(resolver(ascii_host))
        except (FutureTimeoutError, socket.gaierror, UnicodeError, OSError):
            raise FetchRefused(DNS_FAILED) from None
        if not addresses:
            raise FetchRefused(DNS_FAILED)
    # AIDEV-NOTE: security; EVERY address (M-ALLIPS): one private answer refuses the name, because
    # the pin below takes addresses[0] and a resolver may order answers however the attacker likes.
    for address in addresses:
        if not address_allowed(address):
            raise FetchRefused(ADDRESS_REFUSED, host=ascii_host)
    pinned = str(ipaddress.ip_address(str(addresses[0]).split("%", 1)[0]))
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return _Target(
        scheme=scheme, host=ascii_host, ip=pinned, port=ports[scheme], path=path
    )


class Watchdog:
    """Shuts every socket it watches down when ``seconds`` have passed (module note).

    Each watched socket is DUPLICATED and the duplicate is what gets shut down and later closed:
    shutdown acts on the connection, not the descriptor, so it reaches urllib3's socket (and the
    SSLSocket that later takes its descriptor over) while the number we hold can never be reused
    by an unrelated socket before cancel() closes it.
    """

    def __init__(self, seconds: float):
        self._lock = threading.Lock()
        self._socks: list = []
        self._fired = False
        self._done = False
        self._timer = threading.Timer(max(0.0, seconds), self._fire)
        self._timer.daemon = True
        self._timer.start()

    @property
    def fired(self) -> bool:
        return self._fired

    def watch(self, sock) -> None:
        dup = sock.dup()
        with self._lock:
            if self._done:
                dup.close()
                return
            self._socks.append(dup)
            if self._fired:
                self._shut(dup)

    @staticmethod
    def _shut(sock) -> None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _fire(self) -> None:
        with self._lock:
            if self._done:
                return
            self._fired = True
            for sock in self._socks:
                self._shut(sock)

    def cancel(self) -> None:
        self._timer.cancel()
        with self._lock:
            self._done = True
            socks, self._socks = self._socks, []
        for sock in socks:
            try:
                sock.close()
            except OSError:
                pass


def _watched_connection_cls(base, watchdog: Watchdog):
    """``base`` (urllib3's HTTP(S)Connection) with every new socket handed to ``watchdog`` the
    moment it is connected, before TLS, so the handshake is covered too."""

    class WatchedConnection(base):
        def _new_conn(self):
            sock = super()._new_conn()
            watchdog.watch(sock)
            return sock

    return WatchedConnection


def pinned_pool_kwargs(scheme: str, *, ip: str, host: str, timeout: float) -> dict:
    """The keyword arguments of the urllib3 pool for ``scheme`` pinned to ``ip`` (module note):
    HTTPSConnectionPool's for https (TLS checked against ``host``), HTTPConnectionPool's for http.
    """
    import urllib3

    kwargs: dict = {
        "host": ip,
        "timeout": urllib3.Timeout(
            connect=min(CONNECT_TIMEOUT_SECONDS, timeout), read=timeout
        ),
        "retries": False,
        "maxsize": 1,
    }
    if scheme == "https":
        import certifi

        kwargs.update(
            port=443,
            server_hostname=host,
            assert_hostname=host,
            cert_reqs="CERT_REQUIRED",
            ca_certs=certifi.where(),
        )
    elif scheme == "http":
        kwargs["port"] = 80
    else:
        raise ValueError(f"no pinned pool for scheme {scheme!r}")
    return kwargs


def open_pinned(pool, watchdog: Watchdog, *, host, path, accept, user_agent):
    """GET ``path`` through ``pool`` (built from pinned_pool_kwargs) with every socket under
    ``watchdog``. Returns urllib3's unread response carrying the watchdog as
    ``safe_fetch_watchdog``; the caller releases it (release cancels the watchdog)."""
    pool.ConnectionCls = _watched_connection_cls(pool.ConnectionCls, watchdog)
    try:
        response = pool.urlopen(
            "GET",
            path,
            headers={
                "Host": host_header(host),
                "User-Agent": user_agent,
                "Accept": accept,
                "Accept-Encoding": "identity",
            },
            redirect=False,
            retries=False,
            preload_content=False,
            decode_content=False,
            assert_same_host=False,
        )
    except BaseException:
        watchdog.cancel()
        if watchdog.fired:
            raise FetchRefused(TIMEOUT) from None
        raise
    response.safe_fetch_watchdog = watchdog
    return response


def host_header(host: str) -> str:
    """The Host header value for ``host``: an IPv6 literal goes in brackets (RFC 7230 5.4)."""
    return f"[{host}]" if ":" in host else host


def connect_pinned(
    *,
    ip: str,
    host: str,
    path: str,
    timeout: float,
    accept: str = "*/*",
    scheme: str = "https",
    user_agent: str = DEFAULT_USER_AGENT,
    watchdog_cls=None,
):
    """GET ``path`` from ``ip`` (port 443 with TLS checked against ``host``, or port 80 for http).
    The default connector. ``watchdog_cls`` defaults to Watchdog."""
    import urllib3

    # AIDEV-NOTE: security; the wall-clock bound (module note). Armed BEFORE the connect, for
    # exactly the time left, so connect + TLS + head + body share it.
    watchdog = (watchdog_cls or Watchdog)(timeout)
    pool_cls: type = (
        urllib3.HTTPSConnectionPool if scheme == "https" else urllib3.HTTPConnectionPool
    )
    # AIDEV-NOTE: security; the pool is built at host=<validated ip> (M-PIN). Passing ``host``
    # here would let urllib3 re-resolve the name, which is exactly the DNS-rebinding hole.
    pool = pool_cls(**pinned_pool_kwargs(scheme, ip=ip, host=host, timeout=timeout))
    return open_pinned(
        pool, watchdog, host=host, path=path, accept=accept, user_agent=user_agent
    )


def timed_out(response) -> bool:
    """True when the response's Watchdog (if it has one) has fired."""
    watchdog = getattr(response, "safe_fetch_watchdog", None)
    return isinstance(watchdog, Watchdog) and watchdog.fired


def network_code(exc: BaseException) -> str:
    """timeout or connect_failed for an exception from the connector or a read."""
    import urllib3.exceptions as u3

    if isinstance(exc, (TimeoutError, socket.timeout, u3.TimeoutError)):
        return TIMEOUT
    return CONNECT_FAILED


def header(response, name: str):
    headers = getattr(response, "headers", None) or {}
    value = headers.get(name)
    if value is None and hasattr(headers, "items"):
        for key, item in headers.items():
            if key.lower() == name.lower():
                return item
    return value


def release(response) -> None:
    watchdog = getattr(response, "safe_fetch_watchdog", None)
    if isinstance(watchdog, Watchdog):
        watchdog.cancel()
    for method in ("release_conn", "close"):
        func = getattr(response, method, None)
        if callable(func):
            try:
                func()
            except Exception:  # noqa: BLE001 -- releasing must never mask the outcome
                pass


def read_capped(response, cap: int, deadline: float, clock) -> bytes:
    """The body, capped at ``cap`` bytes. Any read failure becomes timeout or connect_failed."""
    declared = header(response, "Content-Length")
    if declared is not None:
        declared = str(declared).strip()
        if not (declared.isascii() and declared.isdigit()) or int(declared) > cap:
            raise FetchRefused(TOO_LARGE)
    received = bytearray()
    count = 0
    try:
        for chunk in response.stream(READ_CHUNK_BYTES):
            if not chunk:
                continue
            # AIDEV-NOTE: security; the RUNNING count (M-CAP), whatever Content-Length said: a
            # server can omit the header or lie in it. Invalidated if the body is ever read whole.
            if count + len(chunk) > cap:
                raise FetchRefused(TOO_LARGE)
            count += len(chunk)
            received += chunk
            if clock() > deadline or timed_out(response):
                raise FetchRefused(TIMEOUT)
    except FetchRefused:
        raise
    except Exception as exc:  # noqa: BLE001 -- every read failure is one of two tokens
        if timed_out(response):
            raise FetchRefused(TIMEOUT) from None
        raise FetchRefused(network_code(exc)) from None
    # A body with no Content-Length simply ENDS when the watchdog shuts the socket: the bytes so
    # far are truncated, never a success.
    if timed_out(response):
        raise FetchRefused(TIMEOUT)
    return bytes(received)


def next_url(current: str, location: str) -> str:
    """``location`` resolved against ``current``, or FetchRefused(url_host). urljoin runs urlsplit,
    which raises ValueError on e.g. "http://[x/": a refusal, never a bare exception out of
    fetch_url (callers loop over many users' feeds). The result is NOT checked here."""
    try:
        return urljoin(current, location)
    except ValueError:
        raise FetchRefused(URL_HOST) from None


def fetch_url(
    url: str,
    *,
    ports=None,
    cap: int,
    total_timeout: float = TOTAL_TIMEOUT_SECONDS,
    accept: str | None = None,
    user_agent: str | None = None,
    resolver=None,
    connector=None,
    clock=time.monotonic,
) -> FetchResult:
    """The bytes at ``url`` (module note for every guard), or FetchRefused.

    ``resolver(host) -> [address, ...]`` and ``connector(*, ip, host, path, timeout, ...)`` are
    injectable so tests run with no DNS and no network; the defaults are resolve_bounded, bounded
    on each hop by the smaller of RESOLVE_TIMEOUT_SECONDS and the time left, and connect_pinned
    (given ``user_agent``). The connector is passed ``accept`` only when one is given, and
    ``scheme`` only for a non-https hop.
    """
    ports = DEFAULT_PORTS if ports is None else dict(ports)
    if connector is None:
        connector = functools.partial(
            connect_pinned, user_agent=user_agent or DEFAULT_USER_AGENT
        )
    deadline = clock() + total_timeout
    first_host = None
    current = url
    redirects = 0
    try:
        while True:
            # AIDEV-NOTE: security; the wall clock covers the RESOLVE too: no hop starts a
            # resolve once the deadline has passed, and the default resolve waits at most the
            # time left. A resolve failing because the deadline passed is ``timeout``.
            remaining = deadline - clock()
            if remaining <= 0:
                raise FetchRefused(TIMEOUT)
            hop_resolver = resolver or functools.partial(
                resolve_bounded, timeout=min(RESOLVE_TIMEOUT_SECONDS, remaining)
            )
            try:
                target = checked_target(current, hop_resolver, ports)
            except FetchRefused as refused:
                if refused.code == DNS_FAILED and deadline - clock() <= 0:
                    raise FetchRefused(TIMEOUT, host=refused.host) from None
                raise
            first_host = first_host or target.host
            remaining = deadline - clock()
            if remaining <= 0:
                raise FetchRefused(TIMEOUT)
            extra = {} if accept is None else {"accept": accept}
            if target.scheme != "https":
                extra["scheme"] = target.scheme
            try:
                response = connector(
                    ip=target.ip,
                    host=target.host,
                    path=target.path,
                    timeout=remaining,
                    **extra,
                )
            except FetchRefused:
                raise
            except Exception as exc:  # noqa: BLE001
                raise FetchRefused(network_code(exc)) from None
            try:
                status = int(getattr(response, "status", 0) or 0)
                if status in REDIRECT_STATUSES:
                    location = header(response, "Location")
                    if not location:
                        raise FetchRefused(HTTP_STATUS, status=status)
                    redirects += 1
                    if redirects > MAX_REDIRECTS:
                        raise FetchRefused(REDIRECT_LIMIT)
                    # AIDEV-NOTE: security; back to the TOP of the loop, so the new URL goes
                    # through checked_target in full, under the same ports policy (M-HOP).
                    # Invalidated if a redirect is ever followed by urllib3 (redirect=True).
                    current = next_url(current, str(location))
                    continue
                if status != 200:
                    raise FetchRefused(HTTP_STATUS, status=status)
                data = read_capped(response, cap, deadline, clock)
                content_type = header(response, "Content-Type")
                content_encoding = header(response, "Content-Encoding")
            finally:
                release(response)
            return FetchResult(
                data=data,
                host=first_host,
                final_host=target.host,
                redirects=redirects,
                status=status,
                content_type=None if content_type is None else str(content_type),
                content_encoding=(
                    None if content_encoding is None else str(content_encoding)
                ),
                final_url=current,
            )
    except FetchRefused as refused:
        if refused.host is None:
            refused.host = first_host
        raise
