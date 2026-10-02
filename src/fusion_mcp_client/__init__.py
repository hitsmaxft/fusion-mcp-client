"""Client for Autodesk Fusion's local MCP service."""

from .client import (
    DEFAULT_URL,
    FusionMCPClient,
    FusionMCPError,
    FusionToolError,
    MCPProtocolError,
    MCPTransportError,
    default_screenshot_dir,
    unwrap_tool_result,
)

__version__ = "0.2.0"

__all__ = [
    "DEFAULT_URL",
    "FusionMCPClient",
    "FusionMCPError",
    "FusionToolError",
    "MCPProtocolError",
    "MCPTransportError",
    "default_screenshot_dir",
    "unwrap_tool_result",
]
