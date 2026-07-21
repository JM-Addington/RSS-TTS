"""JSON-RPC 2.0 protocol layer for the MCP endpoint (spec 2025-11-25).

Stateless by design: no Mcp-Session-Id is ever issued, every request is
self-contained, which is also forward-compatible with the session-less
2026-07-28 spec revision.

Method routing: initialize, ping, tools/list, tools/call. Unknown tools are
protocol errors (-32602); tool business failures are isError results.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.contrib.auth.models import User

from . import tools  # noqa: F401  # importing registers all tools
from .registry import ToolError, all_tools, get_tool

logger = logging.getLogger(__name__)

PROTOCOL_VERSION_LATEST = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-03-26", "2025-06-18", "2025-11-25")

SERVER_INFO = {
    "name": "rss-tts-mcp",
    "title": "RSS-TTS MCP Server",
    "version": "1.0.0",
}

SERVER_INSTRUCTIONS = (
    "Manage RSS-TTS podcast feeds. Create feeds, submit articles (text or "
    "URL) for text-to-speech narration, follow external RSS feeds, and "
    "manage voice presets. Articles process asynchronously: poll get_article "
    "until status is COMPLETED, then use audio_url / the feed's rss_url."
)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def error_response(req_id: Any, code: int, message: str) -> dict[str, Any]:
    """Build a JSON-RPC error response object."""
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def result_response(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-RPC success response object."""
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
    requested = params.get("protocolVersion")
    negotiated = (
        requested
        if requested in SUPPORTED_PROTOCOL_VERSIONS
        else PROTOCOL_VERSION_LATEST
    )
    return {
        "protocolVersion": negotiated,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": SERVER_INFO,
        "instructions": SERVER_INSTRUCTIONS,
    }


def handle_tools_list() -> dict[str, Any]:
    return {"tools": [tool.describe() for tool in all_tools()]}


def handle_tools_call(
    req_id: Any, params: dict[str, Any], user: User
) -> dict[str, Any]:
    name = params.get("name")
    tool = get_tool(name) if isinstance(name, str) else None
    if tool is None:
        return error_response(req_id, INVALID_PARAMS, f"Unknown tool: {name!r}")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return error_response(req_id, INVALID_PARAMS, "'arguments' must be an object")
    try:
        payload = tool.handler(user, arguments)
    except ToolError as exc:
        return result_response(
            req_id,
            {
                "content": [{"type": "text", "text": f"Error: {exc}"}],
                "isError": True,
            },
        )
    except Exception:
        # AIDEV-NOTE: safety net — never let a handler bug become a Django 500;
        # log the traceback, return a generic -32603 without leaking details.
        logger.exception("Unhandled error in MCP tool %r", tool.name)
        return error_response(
            req_id, INTERNAL_ERROR, "Internal error while executing tool"
        )
    return result_response(
        req_id,
        {
            "content": [{"type": "text", "text": json.dumps(payload, default=str)}],
            "structuredContent": payload,
            "isError": False,
        },
    )


def dispatch(message: dict[str, Any], user: User) -> dict[str, Any] | None:
    """Dispatch a single JSON-RPC request/notification.

    Returns a response object, or None when the message is a notification or
    a client response (nothing to send back beyond HTTP 202).
    """
    method = message.get("method")
    req_id = message.get("id")

    if method is None:
        # Client-to-server response (sampling etc. — we never request any).
        return None

    is_notification = "id" not in message
    if is_notification:
        # notifications/initialized, notifications/cancelled, ... nothing to do.
        return None

    params = message.get("params") or {}
    if not isinstance(params, dict):
        return error_response(req_id, INVALID_REQUEST, "'params' must be an object")

    if method == "initialize":
        return result_response(req_id, handle_initialize(params))
    if method == "ping":
        return result_response(req_id, {})
    if method == "tools/list":
        return result_response(req_id, handle_tools_list())
    if method == "tools/call":
        return handle_tools_call(req_id, params, user)
    return error_response(req_id, METHOD_NOT_FOUND, f"Method not found: {method}")
