"""Context variables to carry activity recording context through the agent graph.

Graph nodes (especially the tool executor) don't receive business context
(org_id, employee_name) via their function signature. We use contextvars to
thread this through, set before graph.ainvoke() in each gateway/router.
"""

from __future__ import annotations

import contextvars

# Set before graph execution; read in tool_executor node for per-tool recording.
activity_org_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "activity_org_id", default=None
)
activity_employee_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "activity_employee_id", default=None
)
activity_employee_name: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "activity_employee_name", default=None
)
activity_platform: contextvars.ContextVar[str] = contextvars.ContextVar(
    "activity_platform", default="api"
)
activity_channel_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "activity_channel_id", default=None
)
