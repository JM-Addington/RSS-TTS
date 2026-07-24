"""App configuration for the MCP server."""

from django.apps import AppConfig


class McpServerConfig(AppConfig):
    """Django app config for mcp_server."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "mcp_server"
    verbose_name = "MCP Server"
