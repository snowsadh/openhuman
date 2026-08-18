from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """The state of the agent loop, extending LangGraph's MessagesState.

    Uses ``total=False`` semantics via MessagesState so all keys are optional
    and the graph can fill them incrementally.
    """

    # -- Context -----------------------------------------------------------
    employee_id: str  # PG UUID for lookup and tool context
    platform: str  # "discord" | "slack" | "api"

    # -- Guardrails --------------------------------------------------------
    input_blocked: bool
    block_reason: str | None
    guardrail_config: dict  # template guardrail_config propagated through graph
    output_guardrail_passed: bool

    # -- Prompt & tools ----------------------------------------------------
    system_prompt: str
    tools: list  # tool definitions available for this employee
    tool_round: int  # cycle counter (max 5)

    # -- Outputs -----------------------------------------------------------
    raw_response: str | None  # LLM's final text before formatting
    response: str | None  # formatted / safe-fallback output
    files: list[dict] = []  # list of FileAttachment dicts for Slack upload
    citations: list[dict]  # citation list for attribution
    error: str | None
