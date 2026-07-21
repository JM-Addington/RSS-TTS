"""HTTP transport for the MCP endpoint (Streamable HTTP, stateless mode).

Spec 2025-11-25 basic/transports:
- Single endpoint (/mcp) accepting POST; GET/DELETE -> 405 (no SSE stream,
  no sessions to terminate — we always answer application/json).
- MCP-Protocol-Version header validated on every request (absent => assume
  2025-03-26 per spec).
- Origin header validated against ALLOWED_HOSTS to block DNS rebinding.
- OAuth 2.1 bearer auth on every request; scope checks per tool.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.http.request import validate_host
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from . import auth, protocol


def _jsonrpc_http_error(status: int, code: int, message: str) -> JsonResponse:
    return JsonResponse(protocol.error_response(None, code, message), status=status)


def _origin_allowed(request: HttpRequest) -> bool:
    origin = request.headers.get("Origin")
    if not origin or origin == "null":
        return not origin  # "null" origins are rejected, absent Origin is fine
    try:
        host = urlsplit(origin).hostname or ""
    except ValueError:
        return False
    allowed_hosts = settings.ALLOWED_HOSTS or (
        ["localhost", "127.0.0.1", "[::1]"] if settings.DEBUG else []
    )
    issuer_host = urlsplit(auth.issuer_base()).hostname or ""
    trusted = {urlsplit(o).hostname for o in settings.CSRF_TRUSTED_ORIGINS}
    return validate_host(host, allowed_hosts) or host == issuer_host or host in trusted


@method_decorator(csrf_exempt, name="dispatch")
class McpEndpointView(View):
    """The single MCP Streamable HTTP endpoint."""

    http_method_names = ["post", "get", "delete", "options"]

    def http_method_not_allowed(self, request, *args, **kwargs):
        response = super().http_method_not_allowed(request, *args, **kwargs)
        response["Allow"] = "POST"
        return response

    def get(self, request: HttpRequest) -> HttpResponse:
        # No server-initiated SSE stream in stateless JSON mode.
        return HttpResponse(status=405, headers={"Allow": "POST"})

    def delete(self, request: HttpRequest) -> HttpResponse:
        # Stateless: there is no session to terminate (spec: MAY return 405).
        return HttpResponse(status=405, headers={"Allow": "POST"})

    def post(self, request: HttpRequest) -> HttpResponse:
        if not _origin_allowed(request):
            return _jsonrpc_http_error(
                403, protocol.INVALID_REQUEST, "Origin not allowed"
            )

        # AIDEV-NOTE: absent header => assume 2025-03-26 (spec-mandated default)
        version = request.headers.get("MCP-Protocol-Version")
        if version is not None and version not in protocol.SUPPORTED_PROTOCOL_VERSIONS:
            return _jsonrpc_http_error(
                400,
                protocol.INVALID_REQUEST,
                f"Unsupported MCP-Protocol-Version: {version}. Supported: "
                f"{', '.join(protocol.SUPPORTED_PROTOCOL_VERSIONS)}",
            )

        token, error = auth.authenticate(request)
        if error is not None:
            return error

        try:
            message: Any = json.loads(request.body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _jsonrpc_http_error(
                400, protocol.PARSE_ERROR, "Parse error: invalid JSON"
            )

        if isinstance(message, list):
            return _jsonrpc_http_error(
                400,
                protocol.INVALID_REQUEST,
                "JSON-RPC batching is not supported by MCP",
            )
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _jsonrpc_http_error(
                400, protocol.INVALID_REQUEST, "Invalid JSON-RPC 2.0 message"
            )

        # Per-tool scope enforcement before dispatch (403 + insufficient_scope
        # challenge enables incremental/step-up authorization in clients).
        if message.get("method") == "tools/call" and "id" in message:
            params = message.get("params") or {}
            tool = (
                protocol.get_tool(params.get("name"))
                if isinstance(params, dict) and isinstance(params.get("name"), str)
                else None
            )
            if tool is not None and not auth.token_has_scope(
                token, tool.required_scope
            ):
                return auth.forbidden_scope(tool.required_scope)

        response = protocol.dispatch(message, token.user)
        if response is None:
            return HttpResponse(status=202)
        return JsonResponse(response)
