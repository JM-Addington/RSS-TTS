"""Transport + authorization tests for the /mcp endpoint.

Covers MCP spec 2025-11-25 Streamable HTTP requirements (stateless mode):
- POST JSON-RPC with application/json responses
- GET/DELETE -> 405 (no server-initiated SSE stream, no sessions)
- MCP-Protocol-Version header validation
- Origin validation (DNS-rebinding defence)
- OAuth 2.1 bearer auth: 401 + WWW-Authenticate with resource_metadata,
  audience/expiry validation, scope enforcement (403 insufficient_scope).
"""

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from tests.mcp_server.helpers import (
    MCP_URL,
    PROTOCOL_VERSION,
    make_token,
    mcp_post,
    rpc,
)

User = get_user_model()
BASE = "http://testserver"


class McpEndpointBase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="mcpuser", email="mcp@example.com", password="testpass123"
        )
        self.token = make_token(self.user)


@override_settings(MCP_ISSUER_URL=BASE)
class AuthenticationTests(McpEndpointBase):
    def test_missing_token_returns_401_with_www_authenticate(self):
        response = mcp_post(self.client, rpc("initialize"))
        self.assertEqual(response.status_code, 401)
        challenge = response["WWW-Authenticate"]
        self.assertTrue(challenge.startswith("Bearer "))
        self.assertIn(
            f'resource_metadata="{BASE}/.well-known/oauth-protected-resource/mcp"',
            challenge,
        )
        self.assertIn("scope=", challenge)

    def test_invalid_token_returns_401_invalid_token(self):
        response = mcp_post(self.client, rpc("ping"), token="wrong-token")
        self.assertEqual(response.status_code, 401)
        self.assertIn('error="invalid_token"', response["WWW-Authenticate"])

    def test_expired_token_returns_401(self):
        expired = make_token(self.user, expires_in=-60)
        response = mcp_post(self.client, rpc("ping"), token=expired.token)
        self.assertEqual(response.status_code, 401)

    def test_token_in_query_string_is_rejected(self):
        """Tokens MUST NOT be accepted in query strings (spec MUST NOT)."""
        response = self.client.post(
            f"{MCP_URL}?access_token={self.token.token}",
            data=json.dumps(rpc("ping")),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_valid_token_allows_request(self):
        response = mcp_post(self.client, rpc("ping"), token=self.token.token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], {})


@override_settings(MCP_ISSUER_URL=BASE)
class TransportTests(McpEndpointBase):
    def test_get_returns_405(self):
        response = self.client.get(MCP_URL)
        self.assertEqual(response.status_code, 405)

    def test_delete_returns_405(self):
        """Stateless server: no sessions to terminate."""
        response = self.client.delete(MCP_URL)
        self.assertEqual(response.status_code, 405)

    def test_unsupported_protocol_version_header_returns_400(self):
        response = mcp_post(
            self.client,
            rpc("ping"),
            token=self.token.token,
            HTTP_MCP_PROTOCOL_VERSION="1999-01-01",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_protocol_version_header_is_tolerated(self):
        """Spec: absent header => server SHOULD assume 2025-03-26."""
        response = self.client.post(
            MCP_URL,
            data=json.dumps(rpc("ping")),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token.token}",
        )
        self.assertEqual(response.status_code, 200)

    def test_disallowed_origin_returns_403(self):
        response = mcp_post(
            self.client,
            rpc("ping"),
            token=self.token.token,
            HTTP_ORIGIN="https://evil.example.com",
        )
        self.assertEqual(response.status_code, 403)

    def test_notification_returns_202_with_no_body(self):
        payload = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        response = mcp_post(self.client, payload, token=self.token.token)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b"")

    def test_parse_error_returns_jsonrpc_error(self):
        response = self.client.post(
            MCP_URL,
            data="{not json",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token.token}",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], -32700)

    def test_batch_request_is_rejected(self):
        """JSON-RPC batching was removed from MCP in 2025-06-18."""
        response = mcp_post(
            self.client,
            [rpc("ping", req_id=1), rpc("ping", req_id=2)],
            token=self.token.token,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], -32600)

    def test_unknown_method_returns_method_not_found(self):
        response = mcp_post(self.client, rpc("bogus/method"), token=self.token.token)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["error"]["code"], -32601)
        self.assertEqual(body["id"], 1)

    def test_response_content_type_is_json(self):
        response = mcp_post(self.client, rpc("ping"), token=self.token.token)
        self.assertEqual(response["Content-Type"], "application/json")


@override_settings(MCP_ISSUER_URL=BASE)
class InitializeTests(McpEndpointBase):
    def test_initialize_negotiates_protocol_version(self):
        response = mcp_post(
            self.client,
            rpc(
                "initialize",
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            ),
            token=self.token.token,
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertEqual(result["protocolVersion"], PROTOCOL_VERSION)
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "rss-tts-mcp")

    def test_initialize_with_unknown_version_falls_back_to_latest(self):
        response = mcp_post(
            self.client,
            rpc(
                "initialize",
                {
                    "protocolVersion": "2099-01-01",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            ),
            token=self.token.token,
        )
        result = response.json()["result"]
        self.assertEqual(result["protocolVersion"], PROTOCOL_VERSION)

    def test_initialize_with_older_supported_version_echoes_it(self):
        response = mcp_post(
            self.client,
            rpc(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            ),
            token=self.token.token,
        )
        self.assertEqual(response.json()["result"]["protocolVersion"], "2025-06-18")


@override_settings(MCP_ISSUER_URL=BASE)
class ScopeEnforcementTests(McpEndpointBase):
    def test_read_scope_cannot_call_write_tool(self):
        read_only = make_token(self.user, scope="mcp:read")
        response = mcp_post(
            self.client,
            rpc("tools/call", {"name": "create_feed", "arguments": {"name": "X"}}),
            token=read_only.token,
        )
        self.assertEqual(response.status_code, 403)
        challenge = response["WWW-Authenticate"]
        self.assertIn('error="insufficient_scope"', challenge)
        self.assertIn('scope="mcp:write"', challenge)

    def test_write_scope_token_without_read_cannot_list(self):
        write_only = make_token(self.user, scope="mcp:write")
        response = mcp_post(
            self.client,
            rpc("tools/call", {"name": "list_feeds", "arguments": {}}),
            token=write_only.token,
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn('scope="mcp:read"', response["WWW-Authenticate"])

    def test_token_without_mcp_scopes_is_rejected_up_front(self):
        no_scope = make_token(self.user, scope="something:else")
        response = mcp_post(self.client, rpc("ping"), token=no_scope.token)
        self.assertEqual(response.status_code, 403)
