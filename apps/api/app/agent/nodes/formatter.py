import json
import re

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.state import AgentState

# Marker prefix for built-in file-generation tool (executor.py)
_FILE_MARKER_PREFIX = "__OPENHUMAN_FILE__"


def _iter_content_texts(content: object) -> list[str]:
    """Normalize a ``ToolMessage.content`` value into a flat list of text
    strings.

    Built-in tools (e.g. ``create_document``) return a plain string.
    MCP tool results (via ``langchain-mcp-adapters``) come back as a list
    of content blocks, e.g. ``[{"type": "text", "text": "..."}]`` — those
    need to be unwrapped before marker detection can work.
    """
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        texts: list[str] = []
        for block in content:
            if isinstance(block, str):
                texts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                texts.append(block["text"])
        return texts
    return []


def _extract_file_markers(content: object) -> list[dict] | None:
    """If any text block within *content* starts with the file marker
    prefix, parse and return the file attachment dicts. Otherwise None."""
    markers: list[dict] = []
    for text in _iter_content_texts(content):
        if not text.startswith(_FILE_MARKER_PREFIX):
            continue
        try:
            payload = text[len(_FILE_MARKER_PREFIX):]
            markers.append(json.loads(payload))
        except (json.JSONDecodeError, KeyError):
            continue
    return markers or None


# Stock AI-assistant phrasings the model tends to default to at the start/end
# of a response when nothing tells it otherwise. Matched case-insensitively;
# anchored to start/end of string or line so we don't clip legitimate mid-
# sentence uses (e.g. "as an AI system might phrase it" inside a quote).
_AI_ISM_PATTERNS = [
    (r"^\s*as an ai[,.]?\s*", ""),
    (r"^\s*i'm (an? )?(ai |virtual )?assistant[,.]?\s*", ""),
    (r"\s*is there anything else i can help (you )?with\??\s*$", ""),
    (r"\s*feel free to ask if you have (any )?(more |other )?questions[.!]?\s*$", ""),
    (r"^\s*(great|good) question[!.]?\s*", ""),
    # Numbered recaps of what the user just said/asked/did — a common
    # gpt-4o-mini habit ("1. You said... 2. You asked...") that reads as
    # robotic rather than conversational.
    (r"^\s*\d+\.\s+you (said|asked|mentioned|told|noted)\b.*$\n?", ""),
    # Common robotic/helpdesk greetings and offers
    (r"\bhow (can|may) i (help|assist) you( today| with that| with this)?\??\s*", ""),
    (r"\bwhat can i do for you( today)?\??\s*", ""),
    # Default/robotic starting or ending emojis
    (r"^\s*[👋😊🤖🎯]\s*", ""),
    (r"\s*[👋😊🤖🎯]\s*$", ""),
]

# Markdown table rows (e.g. "| Policy | Detail |") that slip through despite
# the system prompt asking for plain prose.
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_BOLD_LABEL_RE = re.compile(r"\*\*(.+?)\*\*")


def _strip_ai_isms(text: str) -> str:
    for pattern, replacement in _AI_ISM_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE | re.MULTILINE)
    return text.strip()


def _strip_unwanted_markdown(text: str) -> str:
    # Collapse bold-as-pseudo-header usage ("**Policy:** ...") to plain text.
    text = _BOLD_LABEL_RE.sub(r"\1", text)
    # Drop leftover markdown table rows entirely rather than rendering pipes.
    lines = [ln for ln in text.split("\n") if not _TABLE_ROW_RE.match(ln)]
    return "\n".join(lines).strip()


async def formatter_node(state: AgentState) -> dict:
    """Format final output response according to platform constraints.

    Handles:
    - Blocked inputs / failed output guardrails (safe-fallback already set)
    - Tool-round-limit reached without a text response
    - Platform-specific length truncation (Discord 2000, Slack 4000)
    - Empty message lists
    """
    # If a guardrail blocked the message the response is already set in state
    if state.get("input_blocked") or not state.get("output_guardrail_passed", True):
        result = {"response": state.get("response")}
        if state.get("files"):
            result["files"] = state["files"]
        return result

    messages = state.get("messages", [])
    if not messages:
        return {"response": "", "files": state.get("files", [])}

    # Find the last assistant message
    ai_msg = next(
        (m for m in reversed(messages) if isinstance(m, AIMessage)), None
    )
    if not ai_msg:
        return {"response": "", "files": state.get("files", [])}

    response_text = str(ai_msg.content) if ai_msg.content else ""

    # When the tool-round limit was reached and the LLM returned tool_calls
    # instead of a text answer, produce a graceful fallback.
    if not response_text.strip() and state.get("tool_round", 0) >= 5:
        response_text = (
            "I wasn't able to complete this request within the allowed "
            "number of research steps. Could you try rephrasing or "
            "breaking it into smaller questions?"
        )
    else:
        # Only touch real model output — not the tool-round-limit fallback
        # message above, which is already written in the desired style.
        response_text = _strip_ai_isms(response_text)
        response_text = _strip_unwanted_markdown(response_text)

    platform = state.get("platform", "api")

    # Platform-specific formatting rules
    if platform == "discord":
        # Discord limit is 2000 characters
        if len(response_text) > 2000:
            response_text = (
                response_text[:1900]
                + "... [Truncated due to Discord character limits]"
            )
    elif platform == "slack":
        # Slack limit is 4000 characters
        if len(response_text) > 4000:
            response_text = (
                response_text[:3900]
                + "... [Truncated due to Slack character limits]"
            )

    # Scan tool messages for file markers — from the built-in create_document
    # tool (plain string content) as well as MCP tools like the Pitch Deck
    # generator (content comes back as a list of text blocks).
    file_attachments = list(state.get("files", []) or [])
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.content:
            markers = _extract_file_markers(msg.content)
            if markers:
                file_attachments.extend(markers)

    result = {"response": response_text}
    if file_attachments:
        result["files"] = file_attachments
    return result