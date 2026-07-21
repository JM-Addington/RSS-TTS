"""Shared helpers for MCP server tests."""

import json
from datetime import timedelta

from django.utils import timezone
from oauth2_provider.models import AccessToken, Application

MCP_URL = "/mcp"
PROTOCOL_VERSION = "2025-11-25"


def make_application(user=None, **overrides):
    defaults = {
        "name": "Test MCP Client",
        "client_type": Application.CLIENT_PUBLIC,
        "authorization_grant_type": Application.GRANT_AUTHORIZATION_CODE,
        "redirect_uris": "https://claude.ai/api/mcp/auth_callback",
        "user": user,
    }
    defaults.update(overrides)
    return Application.objects.create(**defaults)


def make_token(user, scope="mcp:read mcp:write", expires_in=3600, application=None):
    """Create a bearer access token for `user` directly in the DB."""
    return AccessToken.objects.create(
        user=user,
        token=f"test-token-{user.pk}-{scope.replace(' ', '-')}-{expires_in}",
        application=application or make_application(user),
        expires=timezone.now() + timedelta(seconds=expires_in),
        scope=scope,
    )


def mcp_post(client, payload, token=None, **extra):
    """POST a JSON-RPC payload to the MCP endpoint."""
    headers = {
        "HTTP_ACCEPT": "application/json, text/event-stream",
        "HTTP_MCP_PROTOCOL_VERSION": PROTOCOL_VERSION,
    }
    if token is not None:
        headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    headers.update(extra)
    return client.post(
        MCP_URL,
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )


def rpc(method, params=None, req_id=1):
    payload = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        payload["params"] = params
    return payload


def call_tool(client, token, name, arguments=None, req_id=1):
    """Invoke tools/call and return the HTTP response."""
    return mcp_post(
        client,
        rpc("tools/call", {"name": name, "arguments": arguments or {}}, req_id),
        token=token,
    )


def tool_result(response):
    """Extract the JSON-RPC result from a tools/call response."""
    body = response.json()
    assert "error" not in body, f"unexpected JSON-RPC error: {body}"
    return body["result"]


def structured(response):
    """Extract structuredContent from a successful (non-isError) tool call."""
    result = tool_result(response)
    assert result.get("isError") is not True, f"tool returned error: {result}"
    return result["structuredContent"]
