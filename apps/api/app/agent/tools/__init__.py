"""Agent tool registry and built-in tool exports."""

from app.agent.tools.executor import BUILT_IN_TOOLS  # noqa: F401
from app.agent.tools.registry import registry  # noqa: F401


def register_built_in_tools() -> None:
    """Register all built-in tools with the ToolRegistry singleton.

    Called once at import time. Each tool is tagged with a toolset,
    risk level, and optional availability gate.
    """
    from app.agent.tools.cronjob_tools import cronjob
    from app.agent.tools.delegate_task import delegate_task
    from app.agent.tools.vision_tools import vision_analyze

    # New tools first with correct toolset (before they get picked up
    # from BUILT_IN_TOOLS below, which would tag them as "core").
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

    # Remaining core tools
    for tool in BUILT_IN_TOOLS:
        registry.register_safe(
            tool=tool,
            toolset="core",
            risk_level="low",
        )


# Build the registry singleton at import time
register_built_in_tools()
