# RSS-TTS MCP Server

RSS-TTS exposes a [Model Context Protocol](https://modelcontextprotocol.io)
server so AI clients (claude.ai custom connectors, Claude Code, MCP
Inspector, the Claude Messages API MCP connector) can manage your feeds,
articles, followed RSS feeds, and voice presets with full CRUD.

- **Spec version**: 2025-11-25 (also accepts 2025-06-18 and 2025-03-26 clients)
- **Transport**: Streamable HTTP, stateless JSON mode — single endpoint `POST /mcp`
- **Authorization**: OAuth 2.1 (authorization code + PKCE S256), served by
  django-oauth-toolkit at `/o/`

## Endpoints

| Path | Purpose |
|---|---|
| `POST /mcp` | MCP endpoint (JSON-RPC 2.0 over HTTP) |
| `GET /.well-known/oauth-protected-resource[/mcp]` | RFC 9728 protected resource metadata |
| `GET /.well-known/oauth-authorization-server` | RFC 8414 authorization server metadata |
| `POST /oauth/register/` | RFC 7591 dynamic client registration |
| `GET/POST /o/authorize/` | Authorization endpoint (login + consent) |
| `POST /o/token/` | Token endpoint (code exchange, refresh) |
| `POST /o/revoke_token/`, `POST /o/introspect/` | Revocation / introspection |

## Connecting from claude.ai

1. Deploy with `MCP_ISSUER_URL` set to your public base URL (e.g.
   `https://rss.example.com`) — it must match what users type in exactly.
2. In claude.ai → Settings → Connectors → *Add custom connector*, enter
   `https://rss.example.com/mcp`.
3. Claude discovers the auth server via the 401 challenge, registers itself
   via DCR, and sends you through login + consent. Approve the scopes and
   you're connected.

Anthropic egress (`160.79.104.0/21`) must be able to reach the server over
HTTPS. No Caddy changes are needed: everything except `/audio/*` is already
proxied to Django.

## Scopes

| Scope | Grants |
|---|---|
| `mcp:read` | `list_*` / `get_*` tools |
| `mcp:write` | `create_*` / `update_*` / `delete_*` tools |

Calling a write tool with a read-only token returns HTTP 403 with an
`insufficient_scope` challenge, which OAuth-aware clients use to request
step-up consent.

## Tools

Full CRUD (create/list/get/update/delete) for each entity, always scoped to
the authenticated user:

- **Feeds**: `create_feed`, `list_feeds`, `get_feed`, `update_feed`,
  `delete_feed` (delete cascades to articles — annotated destructive)
- **Articles**: `create_article` (text or URL; async TTS — poll
  `get_article` until `COMPLETED`), `list_articles`, `get_article`,
  `update_article`, `delete_article`
- **Followed RSS feeds**: `create_followed_feed`, `list_followed_feeds`,
  `get_followed_feed`, `update_followed_feed`, `delete_followed_feed`
- **Voice presets**: `create_voice_preset`, `list_voice_presets`,
  `get_voice_preset`, `update_voice_preset`, `delete_voice_preset`

All tools return `structuredContent` plus a JSON text block, declare
`inputSchema` (`additionalProperties: false`), and carry MCP tool
annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`,
`openWorldHint: false`).

## Testing locally

```bash
# Inside docker (see TESTING.md)
python -m pytest tests/mcp_server -v
```

Interactive testing with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
# Transport: Streamable HTTP, URL: http://localhost:8084/mcp
# The inspector drives the OAuth flow (DCR -> authorize -> token) itself.
```

## Design notes

- **Stateless on purpose**: no `Mcp-Session-Id`, `GET /mcp` → 405 (no
  server-push SSE). This is legal under 2025-11-25 and matches the
  session-less direction of the 2026-07-28 spec revision, and it works
  unchanged under WSGI (gunicorn/runserver).
- **Resource-server security**: opaque tokens are validated against the
  co-hosted AS database (satisfying audience binding), accepted only from
  the `Authorization` header, and never passed through to upstream APIs.
- **Origin validation**: requests with an `Origin` header not matching
  `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`/`MCP_ISSUER_URL` are rejected (403)
  to block DNS-rebinding.
- **SSRF**: `create_article`/`create_followed_feed` URLs run through the same
  `validate_url_not_ssrf` guard as the REST API.
