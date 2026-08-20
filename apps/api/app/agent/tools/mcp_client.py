"""Compatibility shim — real implementation lives in ``app.agent.tools.mcp.client``."""

from app.agent.tools.mcp.client import MCPClientManager, ResolvedConnection

__all__ = ["MCPClientManager", "ResolvedConnection"]
