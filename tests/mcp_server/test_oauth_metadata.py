"""Tests for OAuth 2.0 discovery metadata endpoints (RFC 8414 + RFC 9728).

The MCP authorization spec (2025-11-25) requires:
- RFC 9728 Protected Resource Metadata at /.well-known/oauth-protected-resource
  (root and path-suffixed for the /mcp endpoint).
- RFC 8414 Authorization Server Metadata advertising PKCE S256 support
  (clients MUST refuse to proceed if code_challenge_methods_supported is absent).
"""

from django.test import TestCase, override_settings

BASE = "http://testserver"


@override_settings(MCP_ISSUER_URL=BASE)
class AuthorizationServerMetadataTests(TestCase):
    """RFC 8414 authorization server metadata."""

    def test_metadata_endpoint_returns_json(self):
        response = self.client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_metadata_contains_required_fields(self):
        data = self.client.get("/.well-known/oauth-authorization-server").json()
        self.assertEqual(data["issuer"], BASE)
        self.assertEqual(data["authorization_endpoint"], f"{BASE}/o/authorize/")
        self.assertEqual(data["token_endpoint"], f"{BASE}/o/token/")
        self.assertEqual(data["registration_endpoint"], f"{BASE}/oauth/register/")
        self.assertIn("code", data["response_types_supported"])
        self.assertIn("authorization_code", data["grant_types_supported"])
        self.assertIn("refresh_token", data["grant_types_supported"])

    def test_metadata_advertises_pkce_s256(self):
        """Clients MUST abort if S256 is not advertised — spec-critical."""
        data = self.client.get("/.well-known/oauth-authorization-server").json()
        self.assertIn("S256", data["code_challenge_methods_supported"])

    def test_metadata_advertises_public_client_auth(self):
        """'none' must be offered so public clients (PKCE-only) can use /o/token/."""
        data = self.client.get("/.well-known/oauth-authorization-server").json()
        self.assertIn("none", data["token_endpoint_auth_methods_supported"])
        self.assertIn(
            "client_secret_basic", data["token_endpoint_auth_methods_supported"]
        )

    def test_metadata_advertises_mcp_scopes(self):
        data = self.client.get("/.well-known/oauth-authorization-server").json()
        self.assertIn("mcp:read", data["scopes_supported"])
        self.assertIn("mcp:write", data["scopes_supported"])

    def test_metadata_includes_revocation_and_introspection(self):
        data = self.client.get("/.well-known/oauth-authorization-server").json()
        self.assertEqual(data["revocation_endpoint"], f"{BASE}/o/revoke_token/")
        self.assertEqual(data["introspection_endpoint"], f"{BASE}/o/introspect/")

    def test_metadata_allows_cors_preflight_consumers(self):
        """Discovery documents must be fetchable cross-origin by browser clients."""
        response = self.client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")


@override_settings(MCP_ISSUER_URL=BASE)
class ProtectedResourceMetadataTests(TestCase):
    """RFC 9728 protected resource metadata for the MCP server."""

    def test_root_document(self):
        response = self.client.get("/.well-known/oauth-protected-resource")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["resource"], f"{BASE}/mcp")
        self.assertEqual(data["authorization_servers"], [BASE])

    def test_path_suffixed_document_for_mcp_endpoint(self):
        """RFC 9728 path-suffixed variant: /.well-known/oauth-protected-resource/mcp."""
        response = self.client.get("/.well-known/oauth-protected-resource/mcp")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["resource"], f"{BASE}/mcp")

    def test_document_lists_scopes_and_bearer_methods(self):
        data = self.client.get("/.well-known/oauth-protected-resource").json()
        self.assertEqual(sorted(data["scopes_supported"]), ["mcp:read", "mcp:write"])
        self.assertEqual(data["bearer_methods_supported"], ["header"])

    def test_document_allows_cors(self):
        response = self.client.get("/.well-known/oauth-protected-resource")
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")
