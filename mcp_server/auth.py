"""OAuth 2.1 bearer-token authentication for the MCP endpoint.

The MCP server acts as an OAuth 2.1 *resource server* (MCP spec 2025-11-25,
Authorization). django-oauth-toolkit (mounted at /o/) is the co-hosted
authorization server; tokens are opaque and validated against its database,
which also satisfies the spec's audience requirement (tokens issued by our AS
are only redeemable here — no other resource accepts them).

AIDEV-NOTE: 401 responses MUST carry WWW-Authenticate with resource_metadata
(RFC 9728) or claude.ai custom connectors cannot discover the auth server.
"""

from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from oauth2_provider.models import AccessToken

MCP_SCOPES = ("mcp:read", "mcp:write")


def issuer_base() -> str:
    """Canonical base URL of this deployment (issuer + resource host)."""
    return str(settings.MCP_ISSUER_URL).rstrip("/")


def resource_url() -> str:
    """Canonical MCP resource URI (RFC 8707 resource indicator target)."""
    return f"{issuer_base()}/mcp"


def resource_metadata_url() -> str:
    """RFC 9728 path-suffixed protected-resource metadata URL."""
    return f"{issuer_base()}/.well-known/oauth-protected-resource/mcp"


def _challenge(error: str | None, description: str | None, scope: str) -> str:
    parts = [f'resource_metadata="{resource_metadata_url()}"']
    if error:
        parts.append(f'error="{error}"')
    if description:
        parts.append(f'error_description="{description}"')
    parts.append(f'scope="{scope}"')
    return "Bearer " + ", ".join(parts)


def unauthorized(
    error: str | None = None,
    description: str | None = None,
    scope: str = "mcp:read mcp:write",
) -> HttpResponse:
    """401 with the RFC 6750 / RFC 9728 WWW-Authenticate challenge."""
    response = JsonResponse(
        {"error": error or "unauthorized", "error_description": description or ""},
        status=401,
    )
    response["WWW-Authenticate"] = _challenge(error, description, scope)
    return response


def forbidden_scope(required_scope: str) -> HttpResponse:
    """403 insufficient_scope challenge (RFC 6750 §3.1, MCP step-up auth)."""
    response = JsonResponse(
        {
            "error": "insufficient_scope",
            "error_description": f"Requires scope: {required_scope}",
        },
        status=403,
    )
    response["WWW-Authenticate"] = _challenge(
        "insufficient_scope", None, required_scope
    )
    return response


def authenticate(
    request: HttpRequest,
) -> tuple[AccessToken | None, HttpResponse | None]:
    """Validate the Authorization: Bearer header against issued tokens.

    Returns (token, None) on success or (None, error_response) on failure.
    Tokens are only ever read from the header — query-string tokens are
    prohibited by the MCP spec and ignored entirely.
    """
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None, unauthorized(
            description="Missing bearer token; see resource_metadata for the "
            "authorization server."
        )
    raw_token = header[len("Bearer ") :].strip()
    if not raw_token:
        return None, unauthorized(error="invalid_token")

    token = AccessToken.objects.select_related("user").filter(token=raw_token).first()
    if token is None or token.user is None:
        return None, unauthorized(
            error="invalid_token", description="Unknown access token."
        )
    if token.expires <= timezone.now():
        return None, unauthorized(
            error="invalid_token", description="Access token has expired."
        )
    if not any(scope in token.scope.split() for scope in MCP_SCOPES):
        return None, forbidden_scope("mcp:read mcp:write")
    return token, None


def token_has_scope(token: AccessToken, required_scope: str) -> bool:
    """Check a single required scope against the token's granted scopes."""
    return required_scope in token.scope.split()
