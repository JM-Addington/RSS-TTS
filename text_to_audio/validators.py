"""Custom validators for the text_to_audio app.

AIDEV-NOTE: SSRF validator — blocks private IPs, cloud metadata, bad schemes, DNS rebinding
"""

import ipaddress
import logging
import socket
import urllib.parse

from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Hostnames that should always be blocked regardless of DNS resolution
BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
    }
)

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Additional IP networks to block beyond what ipaddress considers private/reserved.
# Includes cloud metadata endpoints and CGNAT (RFC 6598) shared address space.
EXTRA_BLOCKED_NETWORKS = [
    ipaddress.ip_network("100.64.0.0/10"),  # RFC 6598 CGNAT / Alibaba metadata
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local (belt-and-suspenders)
]


def _is_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address is private, loopback, link-local, or otherwise blocked."""
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True

    # Check against extra blocked networks (cloud metadata, CGNAT)
    for network in EXTRA_BLOCKED_NETWORKS:
        if ip in network:
            return True

    # Check IPv4-mapped IPv6 addresses (e.g., ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return _is_ip_blocked(ip.ipv4_mapped)

    return False


def validate_url_not_ssrf(url: str) -> None:
    """Validate that a URL does not point to internal/private network addresses.

    Raises django.core.exceptions.ValidationError if the URL is potentially dangerous.
    Designed as a Django validator callable for use in serializer fields.

    Args:
        url: The URL string to validate.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        raise ValidationError("Invalid URL.")

    # 1. Scheme check
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValidationError(
            f"URL scheme '{parsed.scheme}' is not allowed. Only HTTP and HTTPS are permitted."
        )

    # 2. Extract hostname
    hostname = parsed.hostname  # Already lowercased and bracket-stripped for IPv6
    if not hostname:
        raise ValidationError("URL must contain a valid hostname.")

    # 3. Block known dangerous hostnames
    if hostname in BLOCKED_HOSTNAMES:
        raise ValidationError("Access to this host is not allowed.")

    # 4. Try to parse hostname directly as an IP address (catches decimal IPs, etc.)
    try:
        ip = ipaddress.ip_address(hostname)
        if _is_ip_blocked(ip):
            raise ValidationError(
                "Access to private or internal network addresses is not allowed."
            )
        # It's a valid public IP literal — allow it
        return
    except ValueError:
        # Not an IP literal — continue to DNS resolution
        pass

    # 5. Resolve hostname and check all returned IPs
    try:
        addrinfo = socket.getaddrinfo(
            hostname, parsed.port or 80, proto=socket.IPPROTO_TCP
        )
    except socket.gaierror:
        raise ValidationError(f"Could not resolve hostname: {hostname}")

    if not addrinfo:
        raise ValidationError(f"Could not resolve hostname: {hostname}")

    for family, _type, _proto, _canonname, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
            if _is_ip_blocked(ip):
                logger.warning(
                    "SSRF blocked: %s resolved to private IP %s", hostname, ip_str
                )
                raise ValidationError(
                    "Access to private or internal network addresses is not allowed."
                )
        except ValueError:
            continue
