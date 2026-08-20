"""Human-escalation tools — fire-and-forget (Phase 5) and interactive (Phase 6).

Fire-and-forget (:func:`escalate_to_human`) posts a Slack message to a
configured escalation target and returns immediately so the graph stays fast.

Interactive (:func:`escalate_to_human_interactive`) posts Block Kit
**Approve / Deny** buttons and calls ``interrupt()`` to pause the graph until a
human decision arrives via Socket Mode.  Requires the Phase 4 Postgres
checkpointer and an ``escalation_policy`` with ``mode: "interactive"``.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.types import interrupt
from slack_sdk.web.async_client import AsyncWebClient

from app.core.security import decrypt_token
from app.employees.models import Employee

logger = logging.getLogger(__name__)


# =============================================================================
# Shared helpers
# =============================================================================


def _resolve_escalation_target(policy: dict, is_sensitive: bool) -> tuple[str | None, str | None]:
    """Return ``(target, label)`` from *policy*, or ``(None, None)`` on failure."""
    manager_slack_id: str | None = policy.get("manager_slack_id")
    default_channel: str | None = policy.get("default_escalation_channel")

    if is_sensitive and manager_slack_id:
        return manager_slack_id, f"manager DM ({manager_slack_id})"
    if default_channel:
        return default_channel, f"channel {default_channel}"
    if manager_slack_id:
        return manager_slack_id, f"manager DM ({manager_slack_id})"
    return None, None


async def _load_employee_and_policy(config: RunnableConfig) -> tuple[Employee, dict, str]:
    """Validate config and return ``(employee, policy, bot_token)``.

    Raises :class:`_EscalationError` with a JSON error payload on any failure.
    """
    if config is None or "configurable" not in config:
        raise _EscalationError({
            "status": "error",
            "message": "Escalation failed: no configuration available.",
        })

    cfg = config["configurable"]
    db = cfg.get("db")
    employee_id_str = cfg.get("employee_id")

    if db is None or employee_id_str is None:
        raise _EscalationError({
            "status": "error",
            "message": "Escalation failed: missing employee context.",
        })

    try:
        employee_id = UUID(employee_id_str)
    except (ValueError, TypeError):
        raise _EscalationError({
            "status": "error",
            "message": "Escalation failed: invalid employee ID.",
        })

    emp = await db.get(Employee, employee_id)
    if emp is None:
        raise _EscalationError({
            "status": "error",
            "message": "Escalation failed: employee not found.",
        })

    policy = emp.escalation_policy
    if not policy:
        raise _EscalationError({
            "status": "error",
            "message": (
                "Escalation failed: no escalation policy is configured for this "
                "employee. An admin must set the escalation_policy field with at "
                "least a manager_slack_id or default_escalation_channel."
            ),
        })

    if emp.slack_token_enc is None:
        raise _EscalationError({
            "status": "error",
            "message": "Escalation failed: this employee has no Slack token configured.",
        })

    try:
        bot_token = decrypt_token(emp.slack_token_enc)
    except Exception:
        logger.exception("Failed to decrypt Slack token for employee %s", employee_id)
        raise _EscalationError({
            "status": "error",
            "message": "Escalation failed: unable to decrypt Slack credentials.",
        }) from None

    return emp, policy, bot_token


class _EscalationError(Exception):
    """Carries a JSON error payload to short-circuit the tool."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload


# =============================================================================
# Fire-and-forget tool (Phase 5)
# =============================================================================


@tool
async def escalate_to_human(
    reason: str,
    is_sensitive: bool = False,
    config: RunnableConfig = None,
) -> str:
    """Escalate the current conversation to a human manager or team channel.

    Use this tool when:
    - A user explicitly asks to speak to a human
    - The query is outside the agent's knowledge or authority
    - A sensitive topic (salary, legal, PII) is detected
    - The agent has exhausted its available tools without resolving the issue

    This is a **fire-and-forget** escalation — the message is sent and the agent
    continues immediately.  The human follows up on their own time.

    Args:
        reason: A clear explanation of why this is being escalated, including
                relevant context from the conversation.
        is_sensitive: Set to True if the topic involves PII, compensation,
                      legal matters, or other sensitive data.  When True the
                      message is routed to the manager's DM instead of a
                      public channel.
    """
    try:
        emp, policy, bot_token = await _load_employee_and_policy(config)
    except _EscalationError as exc:
        return json.dumps(exc.payload)

    cfg = config["configurable"]  # type: ignore[index]
    platform = cfg.get("platform", "unknown")

    # -- Resolve target -------------------------------------------------------
    target, target_label = _resolve_escalation_target(policy, is_sensitive)
    if target is None:
        return json.dumps({
            "status": "error",
            "message": (
                "Escalation failed: escalation_policy is missing both "
                "'manager_slack_id' and 'default_escalation_channel'."
            ),
        })

    if platform != "slack":
        return json.dumps({
            "status": "error",
            "message": (
                f"Escalation is only supported on Slack. "
                f"This employee is on '{platform}'."
            ),
        })

    # -- Post the escalation message ------------------------------------------
    channel_id = cfg.get("channel_id", "unknown")
    thread_ts = cfg.get("thread_ts", "")

    blocks = _build_escalation_blocks(emp, reason, channel_id, thread_ts)

    try:
        client = AsyncWebClient(token=bot_token)
        await client.chat_postMessage(
            channel=target,
            text=f"🚨 Escalation from AI agent: {reason}",
            blocks=blocks,
        )
    except Exception:
        logger.exception("Failed to post escalation to %s", target_label)
        return json.dumps({
            "status": "error",
            "message": (
                f"Escalation failed: could not send message to {target_label}."
            ),
        })

    logger.info(
        "Escalation (fire-and-forget): employee=%s target=%s sensitive=%s",
        emp.id, target_label, is_sensitive,
    )

    return json.dumps({
        "status": "success",
        "message": (
            f"Escalated to {target_label}. "
            "A human supervisor has been notified and will follow up."
        ),
        "target": target_label,
    })


# =============================================================================
# Interactive tool (Phase 6)
# =============================================================================

_ESCALATION_APPROVE_ACTION = "escalation_approve"
_ESCALATION_DENY_ACTION = "escalation_deny"


@tool
async def escalate_to_human_interactive(
    reason: str,
    is_sensitive: bool = False,
    config: RunnableConfig = None,
) -> str:
    """Escalate to a human and **wait** for their approval before continuing.

    This tool pauses the agent until a human manager clicks **Approve** or
    **Deny** on a Slack message.  Use this when the agent *must* get explicit
    sign-off before proceeding (e.g. sending an email, making a purchase,
    disclosing restricted information).

    After calling this tool the agent will receive the manager's decision
    (``approved`` / ``denied``, who decided, and any note they left) and can
    act accordingly.

    Args:
        reason: A clear explanation of what needs approval and why.
        is_sensitive: Route to the manager's DM instead of the team channel.
    """
    try:
        emp, policy, bot_token = await _load_employee_and_policy(config)
    except _EscalationError as exc:
        return json.dumps(exc.payload)

    cfg = config["configurable"]  # type: ignore[index]
    platform = cfg.get("platform", "unknown")
    employee_id = cfg.get("employee_id", "unknown")

    if platform != "slack":
        return json.dumps({
            "status": "error",
            "message": "Interactive escalation is only supported on Slack.",
        })

    # -- Resolve target -------------------------------------------------------
    target, target_label = _resolve_escalation_target(policy, is_sensitive)
    if target is None:
        return json.dumps({
            "status": "error",
            "message": (
                "Escalation policy is missing both 'manager_slack_id' and "
                "'default_escalation_channel'."
            ),
        })

    channel_id = cfg.get("channel_id", "")
    thread_ts = cfg.get("thread_ts", "")
    thread_key = cfg.get("thread_id", "")

    # -- Post "waiting" message to the user's thread --------------------------
    client = AsyncWebClient(token=bot_token)
    try:
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"⏳ I've sent this to {target_label} for approval. I'll update you here when they respond.",
        )
    except Exception:
        logger.exception("Failed to post waiting message to user thread")

    # -- Post Block Kit message with Approve / Deny to the target -------------
    button_value_base = json.dumps({
        "thread_key": thread_key,
        "employee_id": employee_id,
        "channel_id": channel_id,
        "thread_ts": thread_ts,
        "platform": platform,
        "reason": reason[:500],
    })

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🔔 Approval Required"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*AI Agent:* <@{emp.slack_bot_user_id or 'unknown'}> is requesting approval.\n\n"
                    f"*Reason:* {reason}"
                ),
            },
        },
    ]

    if channel_id:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Context:* <https://slack.com/app_redirect?channel={channel_id}&message_ts={thread_ts}|View conversation>",
            },
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "✅ Approve"},
                "style": "primary",
                "action_id": _ESCALATION_APPROVE_ACTION,
                "value": button_value_base,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "❌ Deny"},
                "style": "danger",
                "action_id": _ESCALATION_DENY_ACTION,
                "value": button_value_base,
            },
        ],
    })

    try:
        manager_resp = await client.chat_postMessage(
            channel=target,
            text=f"🔔 Approval needed: {reason}",
            blocks=blocks,
        )
        manager_msg_ts = manager_resp.get("ts", "")
    except Exception:
        logger.exception("Failed to post approval request to %s", target_label)
        return json.dumps({
            "status": "error",
            "message": f"Failed to send approval request to {target_label}.",
        })

    logger.info(
        "Interactive escalation: employee=%s target=%s thread_key=%s",
        emp.id, target_label, thread_key,
    )

    # -- Pause the graph until a human clicks Approve / Deny -------------------
    # The Slack button handler in slack_bot.py will call
    #   graph.ainvoke(Command(resume={...}), config={...})
    # to resume from this point.  ``interrupt()`` returns whatever the
    # handler passes as ``Command(resume=...)``.
    decision: dict = interrupt({
        "type": "escalation_decision",
        "thread_key": thread_key,
        "employee_id": employee_id,
        "target": target_label,
        "reason": reason,
        "manager_msg_ts": manager_msg_ts,
        "manager_channel": target,
    })

    # -- We are back!  Process the decision ------------------------------------
    approved = decision.get("approved", False)
    decided_by = decision.get("by", "unknown")
    note = decision.get("note", "")

    logger.info(
        "Interactive escalation resumed: approved=%s by=%s thread_key=%s",
        approved, decided_by, thread_key,
    )

    if approved:
        return json.dumps({
            "status": "approved",
            "message": (
                "Escalation was **approved**. You may proceed with the requested action. "
                f"Approved by <@{decided_by}>."
                + (f" Note: {note}" if note else "")
            ),
            "approved": True,
            "approved_by": decided_by,
            "note": note,
        })
    else:
        return json.dumps({
            "status": "denied",
            "message": (
                "Escalation was **denied**. Do not proceed with the requested action. "
                f"Denied by <@{decided_by}>."
                + (f" Note: {note}" if note else "")
            ),
            "approved": False,
            "denied_by": decided_by,
            "note": note,
        })


# =============================================================================
# Block builders
# =============================================================================


def _build_escalation_blocks(
    emp: Employee,
    reason: str,
    channel_id: str,
    thread_ts: str,
) -> list[dict]:
    """Build Block Kit blocks for a fire-and-forget escalation message."""
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🚨 Escalation Request"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*From:* <@{emp.slack_bot_user_id or 'unknown'}>"},
                {"type": "mrkdwn", "text": f"*Reason:* {reason}"},
            ],
        },
    ]

    if channel_id and channel_id != "unknown":
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Original conversation:* "
                    f"<https://slack.com/app_redirect?channel={channel_id}"
                    f"&message_ts={thread_ts}|View in Slack>"
                ),
            },
        })

    return blocks
