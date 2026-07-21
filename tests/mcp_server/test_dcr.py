"""Tests for RFC 7591 Dynamic Client Registration.

claude.ai custom connectors register a new OAuth client per connection via
POST /oauth/register/ with a JSON body. Public clients (token_endpoint_auth_method
"none") get no secret; confidential clients get a one-time cleartext secret.
"""

import json

from django.core.cache import cache
from django.test import TestCase
from oauth2_provider.models import Application

REGISTER_URL = "/oauth/register/"


def register(client, payload):
    return client.post(
        REGISTER_URL, data=json.dumps(payload), content_type="application/json"
    )


class DynamicClientRegistrationTests(TestCase):
    def setUp(self):
        cache.clear()  # avoid rate-limit bleed between tests

    def test_register_public_client(self):
        response = register(
            self.client,
            {
                "client_name": "Claude",
                "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
            },
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("client_id", data)
        self.assertNotIn("client_secret", data)
        self.assertEqual(data["client_name"], "Claude")
        self.assertEqual(
            data["redirect_uris"], ["https://claude.ai/api/mcp/auth_callback"]
        )
        self.assertEqual(data["token_endpoint_auth_method"], "none")
        self.assertEqual(data["grant_types"], ["authorization_code", "refresh_token"])
        self.assertEqual(data["response_types"], ["code"])
        self.assertIn("client_id_issued_at", data)

        app = Application.objects.get(client_id=data["client_id"])
        self.assertEqual(app.client_type, Application.CLIENT_PUBLIC)
        self.assertEqual(
            app.authorization_grant_type, Application.GRANT_AUTHORIZATION_CODE
        )

    def test_register_confidential_client_returns_secret_once(self):
        response = register(
            self.client,
            {
                "client_name": "Server-side app",
                "redirect_uris": ["https://example.com/callback"],
                "token_endpoint_auth_method": "client_secret_basic",
            },
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["client_secret"])
        self.assertEqual(data["client_secret_expires_at"], 0)
        app = Application.objects.get(client_id=data["client_id"])
        self.assertEqual(app.client_type, Application.CLIENT_CONFIDENTIAL)
        # Stored secret must be hashed, never cleartext
        self.assertNotEqual(app.client_secret, data["client_secret"])

    def test_register_allows_loopback_http_redirect(self):
        """RFC 8252 loopback redirects (Claude Code) must be accepted."""
        response = register(
            self.client,
            {
                "client_name": "Claude Code",
                "redirect_uris": ["http://localhost:33418/callback"],
                "token_endpoint_auth_method": "none",
            },
        )
        self.assertEqual(response.status_code, 201)

    def test_register_rejects_non_loopback_http_redirect(self):
        response = register(
            self.client,
            {
                "client_name": "Bad",
                "redirect_uris": ["http://example.com/callback"],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_redirect_uri")

    def test_register_rejects_missing_redirect_uris(self):
        response = register(self.client, {"client_name": "No redirects"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_redirect_uri")

    def test_register_rejects_redirect_uri_with_fragment(self):
        response = register(
            self.client,
            {"redirect_uris": ["https://example.com/cb#fragment"]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_redirect_uri")

    def test_register_rejects_unsupported_grant_type(self):
        response = register(
            self.client,
            {
                "redirect_uris": ["https://example.com/cb"],
                "grant_types": ["client_credentials"],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_client_metadata")

    def test_register_rejects_invalid_json(self):
        response = self.client.post(
            REGISTER_URL, data="not json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_client_metadata")

    def test_register_get_not_allowed(self):
        response = self.client.get(REGISTER_URL)
        self.assertEqual(response.status_code, 405)
