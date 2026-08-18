from uuid import UUID

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import AgentState
from app.employees.models import Employee
from app.employees.templates import get_employee_template
from app.organizations.models import Organization

# Appended to every employee's system prompt, after persona/personality/duties,
# so response *style* is consistent regardless of specialization and doesn't
# need to be duplicated inside each EmployeeTemplate.system_prompt_template.
COMMUNICATION_STYLE_BLOCK = (
    "\n\nCommunication style and behavior:\n"
    "- Act like a real coworker messaging on Slack or Discord, not a passive customer service chatbot. You are part of the team, working alongside them.\n"
    "- Respond to casual greetings and small talk (e.g. \"hi\", \"hello\", \"hey\", \"how's it going?\") naturally and casually like a coworker (e.g., \"Hey! Doing well, how's your day going?\", \"Hey there! What's up?\", \"Morning! Just reviewing some docs, what's on your mind?\").\n"
    "- Prohibit transactional help desk phrasing: never ask \"How can I help you today?\", \"How can I assist you?\", or \"What can I do for you?\" in response to greetings or general chat.\n"
    "- Default to plain prose. Only use markdown (tables, headers, bullet lists, bold) when the "
    "person asks for a list/table/comparison, or the content genuinely requires it (e.g. code, "
    "step-by-step instructions with more than 4 steps).\n"
    "- Avoid AI-assistant phrasing: no \"As an AI...\", no \"I'm here to help with...\", no restating "
    "what the user just said back to them, no numbered recaps of the conversation.\n"
    "- Keep emojis minimal, casual, and natural. Never use generic or robotic/AI-like emojis (e.g. 👋, 😊, 🤖, 🎯) automatically in greetings or general messages. Use them only if a human teammate naturally would (e.g., a simple 👍 or no emoji at all).\n"
    "- Skip sign-off questions like \"Let me know if you need anything else!\" unless the situation "
    "genuinely warrants a next step.\n"
    "- Keep responses proportional to the question — a quick question gets a quick answer, not a "
    "structured writeup."
)


def _summarize_connected_tools(tool_names: list[str]) -> str:
    """Create a short prompt block describing currently connected tools."""
    builtin_tools = sorted(name for name in tool_names if not name.startswith("mcp__"))
    mcp_servers = sorted({
        parts[1]
        for name in tool_names
        if name.startswith("mcp__") and len((parts := name.split("__", 2))) >= 3
    })

    lines = [
        "\n\nTool execution rules:",
        "- If the user asks for a file, attachment, export, PDF, PPTX, TXT, or document, you must use create_document when that tool is available. Never claim you cannot create or upload files when create_document is available.",
        "- If the user asks for a pitch deck, slides, or presentation, use the Pitch Deck MCP tool (create_pitch_deck) when available — it generates a styled .pptx directly. If only Canva MCP is available, use that instead. Otherwise fall back to create_document.",
        "- Do not say you are only a language model or that the user must manually create the file when the needed tools are available.",
    ]
    if builtin_tools:
        lines.append("- Built-in tools available right now: " + ", ".join(builtin_tools) + ".")
    if mcp_servers:
        lines.append("- Connected MCP servers available right now: " + ", ".join(mcp_servers) + ".")
    return "\n".join(lines)


async def build_prompt_node(state: AgentState, config: RunnableConfig) -> dict:
    """Load employee and organization metadata, assemble system prompt, and
    return it separately from conversation history.

    The LLM node prepends this prompt at call time. Storing SystemMessages in
    MessagesState would append them after the user message and duplicate them
    in persisted threads on every turn.
    """
    configurable = config.get("configurable", {})
    db: AsyncSession | None = configurable.get("db")
    employee_id_str = configurable.get("employee_id")
    all_tools = configurable.get("all_tools", []) or []

    if not db or not employee_id_str:
        # Fallback to generic assistant when no DB connection is available
        system_prompt = (
            "You are a helpful AI assistant. Help team members with research, "
            "information lookup, calculations, and general tasks."
        )
        system_prompt += COMMUNICATION_STYLE_BLOCK
        return {
            "system_prompt": system_prompt,
            "tool_round": 0,
            "guardrail_config": {},
            "citations": [],
        }

    employee_id = UUID(employee_id_str)

    # Fetch employee and organisation details
    emp = await db.scalar(select(Employee).where(Employee.id == employee_id))
    if not emp:
        system_prompt = "You are a helpful AI assistant." + COMMUNICATION_STYLE_BLOCK
        return {
            "system_prompt": system_prompt,
            "tool_round": 0,
            "guardrail_config": {},
            "citations": [],
        }

    org = await db.scalar(select(Organization).where(Organization.id == emp.org_id))
    org_name = org.name if org else "the Organization"

    # Use built-in template based on specialisation
    template = get_employee_template(emp)

    # Format the template system prompt
    system_prompt = template.system_prompt_template.format(
        name=emp.name, org_name=org_name
    )

    # Append custom personality settings if present
    if emp.personality:
        traits = emp.personality.get("traits", [])
        tone = emp.personality.get("tone")
        parts: list[str] = []
        if traits:
            parts.append(f"Your traits are: {', '.join(traits)}.")
        if tone:
            parts.append(f"Your communication tone should be {tone}.")
        if parts:
            system_prompt += "\nPersonality Profile: " + " ".join(parts)

    # Append custom duties if present
    custom_duties = emp.duties or []
    duties = list(set(template.suggested_duties + custom_duties))
    if duties:
        system_prompt += (
            "\nYour specific duties and core responsibilities include:\n"
            + "\n".join(f"- {duty}" for duty in duties)
        )

    # Shared response-style instructions, appended last so they apply
    # regardless of specialization/personality/duties above.
    system_prompt += COMMUNICATION_STYLE_BLOCK
    system_prompt += _summarize_connected_tools([t.name for t in all_tools if hasattr(t, "name")])

    return {
        "system_prompt": system_prompt,
        "tool_round": 0,
        "guardrail_config": template.guardrail_config,
        "citations": [],
    }
