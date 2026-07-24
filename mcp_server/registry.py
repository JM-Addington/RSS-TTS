"""Tool registry for the MCP server.

Each tool declares its JSON Schema, required OAuth scope, and MCP tool
annotations (readOnlyHint/destructiveHint/idempotentHint/openWorldHint).
Handlers receive (user, arguments) and return a JSON-serializable dict;
business/validation failures raise ToolError, which the protocol layer turns
into an isError=true tool result (MCP spec SEP-1303), never a protocol error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

READ_SCOPE = "mcp:read"
WRITE_SCOPE = "mcp:write"


class ToolError(Exception):
    """Business/validation error surfaced to the model as an isError result."""


@dataclass
class Tool:
    """A registered MCP tool."""

    name: str
    title: str
    description: str
    input_schema: dict[str, Any]
    required_scope: str
    handler: Callable[..., dict[str, Any]]
    annotations: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] | None = None

    def describe(self) -> dict[str, Any]:
        """Render the tools/list entry for this tool."""
        entry: dict[str, Any] = {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {"title": self.title, **self.annotations},
        }
        if self.output_schema is not None:
            entry["outputSchema"] = self.output_schema
        return entry


_REGISTRY: dict[str, Tool] = {}


def register(
    name: str,
    *,
    title: str,
    description: str,
    input_schema: dict[str, Any],
    scope: str,
    annotations: dict[str, Any],
    output_schema: dict[str, Any] | None = None,
) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    """Decorator registering a handler as an MCP tool."""

    def decorator(
        handler: Callable[..., dict[str, Any]],
    ) -> Callable[..., dict[str, Any]]:
        _REGISTRY[name] = Tool(
            name=name,
            title=title,
            description=description,
            input_schema=input_schema,
            required_scope=scope,
            handler=handler,
            annotations=annotations,
            output_schema=output_schema,
        )
        return handler

    return decorator


def get_tool(name: str) -> Tool | None:
    """Look up a tool by name."""
    return _REGISTRY.get(name)


def all_tools() -> list[Tool]:
    """All registered tools in registration order."""
    return list(_REGISTRY.values())


def read_annotations(idempotent: bool = True) -> dict[str, Any]:
    """Annotations for read-only, closed-world tools."""
    return {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": idempotent,
        "openWorldHint": False,
    }


def write_annotations(destructive: bool, idempotent: bool) -> dict[str, Any]:
    """Annotations for mutating, closed-world tools."""
    return {
        "readOnlyHint": False,
        "destructiveHint": destructive,
        "idempotentHint": idempotent,
        "openWorldHint": False,
    }
