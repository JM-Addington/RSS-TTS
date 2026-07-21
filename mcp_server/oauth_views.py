"""OAuth discovery metadata (RFC 8414, RFC 9728) and DCR (RFC 7591) views.

django-oauth-toolkit (mounted at /o/) provides the authorization, token,
introspection, and revocation endpoints; these views advertise them so MCP
clients (claude.ai custom connectors, Claude Code, MCP Inspector) can
discover and register automatically.

AIDEV-NOTE: code_challenge_methods_supported MUST list S256 — MCP clients are
required to abort if it is missing (spec 2025-11-25 authorization).
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlsplit

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from oauth2_provider.generators import generate_client_id, generate_client_secret
from oauth2_provider.models import Application

from .auth import issuer_base, resource_url

MCP_SCOPES_SUPPORTED = ["mcp:read", "mcp:write"]
SUPPORTED_GRANT_TYPES = {"authorization_code", "refresh_token"}
SUPPORTED_AUTH_METHODS = {"none", "client_secret_basic", "client_secret_post"}
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _cors_json(payload: dict[str, Any], status: int = 200) -> JsonResponse:
    """Discovery documents must be fetchable cross-origin by browser clients."""
    response = JsonResponse(payload, status=status)
    response["Access-Control-Allow-Origin"] = "*"
    return response


@require_http_methods(["GET"])
def authorization_server_metadata(request: HttpRequest) -> JsonResponse:
    """RFC 8414 authorization server metadata document."""
    base = issuer_base()
    return _cors_json(
        {
            "issuer": base,
            "authorization_endpoint": f"{base}/o/authorize/",
            "token_endpoint": f"{base}/o/token/",
            "registration_endpoint": f"{base}/oauth/register/",
            "revocation_endpoint": f"{base}/o/revoke_token/",
            "introspection_endpoint": f"{base}/o/introspect/",
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": sorted(SUPPORTED_GRANT_TYPES),
            "token_endpoint_auth_methods_supported": sorted(SUPPORTED_AUTH_METHODS),
            "code_challenge_methods_supported": ["S256"],
            "scopes_supported": MCP_SCOPES_SUPPORTED,
        }
    )


@require_http_methods(["GET"])
def protected_resource_metadata(request: HttpRequest) -> JsonResponse:
    """RFC 9728 protected resource metadata for the MCP endpoint."""
    return _cors_json(
        {
            "resource": resource_url(),
            "authorization_servers": [issuer_base()],
            "scopes_supported": MCP_SCOPES_SUPPORTED,
            "bearer_methods_supported": ["header"],
            "resource_name": "RSS-TTS MCP Server",
        }
    )


def _dcr_error(error: str, description: str) -> JsonResponse:
    return JsonResponse({"error": error, "error_description": description}, status=400)


def _validate_redirect_uris(redirect_uris: Any) -> str | None:
    """Return an error message, or None when the URIs are acceptable."""
    if (
        not isinstance(redirect_uris, list)
        or not redirect_uris
        or not all(isinstance(uri, str) and uri for uri in redirect_uris)
    ):
        return "redirect_uris must be a non-empty array of URIs"
    for uri in redirect_uris:
        try:
            parts = urlsplit(uri)
        except ValueError:
            return f"Malformed redirect URI: {uri}"
        if parts.fragment:
            return f"Redirect URI must not contain a fragment: {uri}"
        if parts.scheme == "https" and parts.netloc:
            continue
        # RFC 8252 §7.3: http is only acceptable for loopback redirects
        if parts.scheme == "http" and parts.hostname in LOOPBACK_HOSTS:
            continue
        return f"Redirect URI must be https or a loopback http URI: {uri}"
    return None


# AIDEV-NOTE: open (unauthenticated) DCR per RFC 7591 — required by claude.ai
# connectors, which register a fresh client per user connection. Rate-limited
# to keep unauthenticated Application creation abusable only slowly.
@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key="ip", rate="10/m", block=True)
def register_client(request: HttpRequest) -> JsonResponse:
    """RFC 7591 dynamic client registration endpoint."""
    try:
        metadata = json.loads(request.body)
        if not isinstance(metadata, dict):
            raise ValueError
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return _dcr_error("invalid_client_metadata", "Body must be a JSON object")

    redirect_uris = metadata.get("redirect_uris")
    if error := _validate_redirect_uris(redirect_uris):
        return _dcr_error("invalid_redirect_uri", error)

    grant_types = metadata.get("grant_types", ["authorization_code"])
    if (
        not isinstance(grant_types, list)
        or not set(grant_types) <= SUPPORTED_GRANT_TYPES
    ):
        return _dcr_error(
            "invalid_client_metadata",
            f"grant_types must be a subset of {sorted(SUPPORTED_GRANT_TYPES)}",
        )
    if "authorization_code" not in grant_types:
        return _dcr_error(
            "invalid_client_metadata", "authorization_code grant is required"
        )

    response_types = metadata.get("response_types", ["code"])
    if response_types != ["code"]:
        return _dcr_error(
            "invalid_client_metadata", 'Only response_types ["code"] is supported'
        )

    auth_method = metadata.get("token_endpoint_auth_method", "none")
    if auth_method not in SUPPORTED_AUTH_METHODS:
        return _dcr_error(
            "invalid_client_metadata",
            f"token_endpoint_auth_method must be one of {sorted(SUPPORTED_AUTH_METHODS)}",
        )

    client_name = metadata.get("client_name", "")
    if not isinstance(client_name, str):
        return _dcr_error("invalid_client_metadata", "client_name must be a string")

    is_public = auth_method == "none"
    client_id = generate_client_id()
    client_secret = "" if is_public else generate_client_secret()

    application = Application(
        name=client_name[:255] or "MCP client",
        client_id=client_id,
        client_secret=client_secret,  # hashed on save by django-oauth-toolkit
        client_type=(
            Application.CLIENT_PUBLIC if is_public else Application.CLIENT_CONFIDENTIAL
        ),
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris=" ".join(redirect_uris),
        user=None,
    )
    application.save()

    payload: dict[str, Any] = {
        "client_id": client_id,
        "client_id_issued_at": int(time.time()),
        "client_name": application.name,
        "redirect_uris": redirect_uris,
        "grant_types": grant_types,
        "response_types": ["code"],
        "token_endpoint_auth_method": auth_method,
        "scope": " ".join(MCP_SCOPES_SUPPORTED),
    }
    if not is_public:
        # Cleartext secret is returned exactly once; only a hash is stored.
        payload["client_secret"] = client_secret
        payload["client_secret_expires_at"] = 0
    return _cors_json(payload, status=201)
