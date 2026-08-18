from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.checkpointer import get_checkpointer
from app.agent.nodes import (
    CustomToolNode,
    build_prompt_node,
    formatter_node,
    input_guardrail_node,
    llm_call_node,
    output_guardrail_node,
)
from app.agent.state import AgentState


def route_after_guardrail(state: AgentState) -> str:
    """Route to end of graph if input is blocked, otherwise to prompt building."""
    if state.get("input_blocked"):
        return END
    return "build_prompt"


def route_after_llm(state: AgentState) -> str:
    """Route to tool execution node if tool calls exist and round limit is not exceeded."""
    messages = state.get("messages", [])
    if not messages:
        return "output_guardrail"

    # Find the last message
    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        # Check round limit to avoid infinite tool loops
        if state.get("tool_round", 0) < 5:
            return "tools"

    return "output_guardrail"


def build_graph(tools: list) -> CompiledStateGraph:
    """Construct and compile the agent StateGraph."""
    workflow = StateGraph(AgentState)

    # Register all nodes
    workflow.add_node("input_guardrail", input_guardrail_node)
    workflow.add_node("build_prompt", build_prompt_node)
    workflow.add_node("llm_call", llm_call_node)
    workflow.add_node("tools", CustomToolNode(tools))
    workflow.add_node("output_guardrail", output_guardrail_node)
    workflow.add_node("formatter", formatter_node)

    # Wire up edges
    workflow.add_edge(START, "input_guardrail")

    # Conditional routing from input_guardrail
    workflow.add_conditional_edges(
        "input_guardrail",
        route_after_guardrail,
        {
            END: END,
            "build_prompt": "build_prompt",
        },
    )

    workflow.add_edge("build_prompt", "llm_call")

    # Conditional routing from llm_call
    workflow.add_conditional_edges(
        "llm_call",
        route_after_llm,
        {
            "tools": "tools",
            "output_guardrail": "output_guardrail",
        },
    )

    # Loop back from tools to llm_call
    workflow.add_edge("tools", "llm_call")

    workflow.add_edge("output_guardrail", "formatter")
    workflow.add_edge("formatter", END)

    return workflow.compile(checkpointer=get_checkpointer())

