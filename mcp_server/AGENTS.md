# mcp_server — AGENTS.md

MCP (Model Context Protocol) server exposing OAuth 2.1-protected CRUD tools
for the RSS-TTS domain models. Built against **MCP spec 2025-11-25**.

## 1. Architecture

| Piece | File | Notes |
|---|---|---|
| Streamable HTTP endpoint | `views.py` (`McpEndpointView`, mounted at `/mcp`) | Stateless: POST-only JSON-RPC, `application/json` responses, no `Mcp-Session-Id`, GET/DELETE → 405. Forward-compatible with the session-less 2026-07-28 spec revision. |
| JSON-RPC dispatch | `protocol.py` | `initialize`, `ping`, `tools/list`, `tools/call`. Unknown tool → `-32602`; business/validation failure → `isError: true` tool result (SEP-1303). |
| Tool registry | `registry.py` | `@register(...)` decorator; declares JSON Schema, required scope, MCP annotations. |
| CRUD tools | `tools.py` | 5 ops × 4 entities (Feed, Article, FollowedFeed, UserVoicePreset). All queries filtered by the token's user; cross-user access reads as "not found". |
| Bearer auth (resource server) | `auth.py` | Validates opaque django-oauth-toolkit tokens. 401 carries `WWW-Authenticate` with `resource_metadata` (RFC 9728); insufficient scope → 403 `insufficient_scope`. |
| Discovery + DCR | `oauth_views.py` | RFC 8414 AS metadata, RFC 9728 PRM (root + `/mcp` suffixed), RFC 7591 dynamic client registration (open, IP rate-limited 10/min). |

The **authorization server** is django-oauth-toolkit mounted at `/o/`
(authorize, token, introspect, revoke). Settings in `rss_tts/settings.py`
(`OAUTH2_PROVIDER`): PKCE required, scopes `mcp:read`/`mcp:write`, 1 h access
tokens, rotating refresh tokens.

## 2. Spec invariants — do not break these

- `code_challenge_methods_supported: ["S256"]` must stay in the RFC 8414
  document; MCP clients MUST abort without it.
- 401 responses from `/mcp` must keep the `WWW-Authenticate` header with
  `resource_metadata="…/.well-known/oauth-protected-resource/mcp"` —
  claude.ai discovers the auth server from it.
- Tokens are accepted from the `Authorization: Bearer` header ONLY (never
  query strings).
- JSON-RPC batching is rejected (removed from MCP in 2025-06-18).
- `MCP_ISSUER_URL` must exactly match the URL users type into claude.ai.
- DCR must keep accepting `http://localhost:*` loopback redirect URIs
  (RFC 8252, used by Claude Code) while rejecting all other http URIs.

## 3. When to use what

- New tool? Add it to `tools.py` with `@register`, give it a JSON Schema with
  `additionalProperties: false`, the correct scope (`mcp:read` for reads,
  `mcp:write` for mutations), and honest annotations (`destructiveHint: true`
  only for deletes; `openWorldHint: false` — these tools are closed-world).
- Business/validation error? `raise ToolError("message")` — never let raw
  exceptions escape a handler.
- URL inputs must go through `_validate_public_url` (SSRF guard shared with
  the REST API).

## 4. Tests

`tests/mcp_server/` — helpers in `helpers.py` (`make_token`, `mcp_post`,
`call_tool`, `structured`). Every new tool needs: happy path, validation
error, and cross-user isolation tests. The end-to-end OAuth flow lives in
`test_oauth_flow.py`.

## 5. Glossary

- **PRM**: Protected Resource Metadata (RFC 9728) — how a client finds the AS.
- **DCR**: Dynamic Client Registration (RFC 7591) — claude.ai registers a
  client per user connection.
- **Stateless mode**: no MCP session ids; every POST is self-contained.
