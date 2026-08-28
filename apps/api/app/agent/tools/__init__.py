"""Agent tool exports, loaded only when an agent workflow requests them.

Database model imports pass through this package (for example
``app.agent.tools.mcp.models``). Keeping the package initializer lightweight
prevents model imports from loading every LangChain tool and optional SDK
during API startup.
"""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    """Provide the historical package exports without eager imports."""
    if name == "BUILT_IN_TOOLS":
        from app.agent.tools.executor import BUILT_IN_TOOLS

        return BUILT_IN_TOOLS
    if name == "registry":
        from app.agent.tools.registry import registry

        return registry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def register_built_in_tools() -> None:
    """Populate the optional ToolRegistry when registry-based use is needed."""
    from app.agent.tools.cronjob_tools import cronjob
    from app.agent.tools.delegate_task import delegate_task
    from app.agent.tools.executor import BUILT_IN_TOOLS
    from app.agent.tools.registry import registry
    from app.agent.tools.vision_tools import vision_analyze

    registry.register_safe(
        tool=delegate_task,
        toolset="delegation",
        risk_level="medium",
    )
    registry.register_safe(
        tool=cronjob,
        toolset="cronjob",
        risk_level="medium",
    )
    registry.register_safe(
        tool=vision_analyze,
        toolset="vision",
        risk_level="low",
    )

    for tool in BUILT_IN_TOOLS:
        registry.register_safe(
            tool=tool,
            toolset="core",
            risk_level="low",
        )


__all__ = ["BUILT_IN_TOOLS", "register_built_in_tools", "registry"]
