"""End-to-end OAuth 2.1 flow: DCR -> authorize (PKCE S256) -> token -> MCP call.

Mirrors what claude.ai does when a user adds this server as a custom connector.
"""

import base64
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from tests.mcp_server.helpers import mcp_post, rpc

User = get_user_model()
BASE = "http://testserver"
REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"


@override_settings(MCP_ISSUER_URL=BASE)
class OAuthEndToEndTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="flowuser", email="flow@example.com", password="testpass123"
        )
        # Approve the user so the approval middleware doesn't log them out
        self.user.profile.is_approved = True
        self.user.profile.save()

    def _pkce_pair(self):
        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        return verifier, challenge

    def test_full_flow_public_client(self):
        # 1. Dynamic client registration (public client, PKCE only)
        response = self.client.post(
            "/oauth/register/",
            data=json.dumps(
                {
                    "client_name": "Claude",
                    "redirect_uris": [REDIRECT_URI],
                    "token_endpoint_auth_method": "none",
                    "grant_types": ["authorization_code", "refresh_token"],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        client_id = response.json()["client_id"]

        # 2. Authorization request with PKCE (user logged in and consenting)
        verifier, challenge = self._pkce_pair()
        self.client.force_login(self.user)
        auth_params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": "mcp:read mcp:write",
            "state": "xyz",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        response = self.client.get("/o/authorize/", data=auth_params)
        self.assertEqual(response.status_code, 200)  # consent form rendered

        response = self.client.post(
            "/o/authorize/", data={**auth_params, "allow": "Authorize"}
        )
        self.assertEqual(response.status_code, 302)
        redirect = urlparse(response["Location"])
        self.assertEqual(
            f"{redirect.scheme}://{redirect.netloc}{redirect.path}", REDIRECT_URI
        )
        query = parse_qs(redirect.query)
        self.assertEqual(query["state"], ["xyz"])
        code = query["code"][0]

        # 3. Token exchange with the PKCE verifier (no client secret)
        self.client.logout()
        response = self.client.post(
            "/o/token/",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": client_id,
                "code_verifier": verifier,
            },
        )
        self.assertEqual(response.status_code, 200)
        token_data = response.json()
        self.assertEqual(token_data["token_type"], "Bearer")
        self.assertIn("refresh_token", token_data)
        access_token = token_data["access_token"]

        # 4. Authenticated MCP request
        response = mcp_post(self.client, rpc("ping"), token=access_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], {})

        # 5. Refresh token rotation (public client)
        response = self.client.post(
            "/o/token/",
            data={
                "grant_type": "refresh_token",
                "refresh_token": token_data["refresh_token"],
                "client_id": client_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        refreshed = response.json()
        self.assertNotEqual(refreshed["access_token"], access_token)
        self.assertNotEqual(refreshed["refresh_token"], token_data["refresh_token"])

    def test_token_exchange_without_verifier_fails(self):
        """PKCE is mandatory: authorization requests without a challenge fail."""
        response = self.client.post(
            "/oauth/register/",
            data=json.dumps(
                {
                    "client_name": "NoPKCE",
                    "redirect_uris": [REDIRECT_URI],
                    "token_endpoint_auth_method": "none",
                }
            ),
            content_type="application/json",
        )
        client_id = response.json()["client_id"]
        self.client.force_login(self.user)
        response = self.client.post(
            "/o/authorize/",
            data={
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "scope": "mcp:read",
                "allow": "Authorize",
            },
        )
        # DOT with PKCE_REQUIRED redirects back with error=invalid_request
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(query.get("error"), ["invalid_request"])
