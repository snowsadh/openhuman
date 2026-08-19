"""
Slack bot — one Socket Mode connection per AI employee.

An ``EmployeeSlackBot`` handles events for a **single** AI employee with
its own Slack app identity (Pattern A).  Each employee gets its own bot
user, sidebar entry, @mention, DMs, and avatar/name — no shared tokens.

When ``SLACK_IDENTITY_MODE=shared`` (legacy), the old ``WorkspaceSlackBot``
path in ``manager.py`` is used instead.
"""

from __future__ import annotations

import base64
import json
import logging
from uuid import UUID

import httpx
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.errors import SlackApiError
from sqlalchemy import select

from app.activity.context import (
    activity_channel_id,
    activity_employee_id,
    activity_employee_name,
    activity_org_id,
    activity_platform,
)
from app.activity.service import record_activity
from app.agent.jobs.queue import cancel_active_jobs_for_thread, is_cancel_intent
from app.agent.router import get_graph_for_employee
from app.channel_assignments.models import ChannelAssignment
from app.core.config import settings
from app.core.database import async_session_factory
from app.documents.models import Document
from app.employees.models import Employee
from app.memory.service import remember
from app.organizations.models import Organization
from app.storage import get_storage_backend

logger = logging.getLogger(__name__)

_SAFE_ERROR_MESSAGE = "I ran into a problem processing your request. Please try again later."

_MAX_SLACK_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class BaseSlackBot:
    """Shared logic for Slack Socket Mode bots."""

    _bot_label: str = "BaseSlackBot"

    def __init__(self, bot_token: str, app_token: str) -> None:
        self.bot_token = bot_token
        self.app_token = app_token
        self._build_app()
        self._handler = AsyncSocketModeHandler(self.app, app_token)
        self.bot_user_id: str | None = None
        self._register_event_handlers()

    def _build_app(self) -> None:
        """Hook for subclasses to customize AsyncApp creation."""
        self.app = AsyncApp(token=self.bot_token)

    def _register_event_handlers(self) -> None:
        self.app.event("app_mention")(self.handle_mention)
        self.app.event("message")(self.handle_message)
        self.app.action("escalation_approve")(self._handle_escalation_approve)
        self.app.action("escalation_deny")(self._handle_escalation_deny)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Resolve this bot's identity, then open the Socket Mode WebSocket connection.

        ``bot_user_id`` MUST be known before events start flowing — the
        mention-filtering guards in ``handle_mention`` /
        ``_process_slack_message`` only work when it's set, and they fail
        *open* (process the message) when it's ``None``. Resolving identity
        before connecting avoids a startup race where an early event could be
        mis-attributed to the wrong employee's bot.
        """
        try:
            auth_res = await self.app.client.auth_test()
            self.bot_user_id = auth_res.get("user_id")
        except Exception:
            logger.exception("Failed to fetch bot user_id before connecting")
            self.bot_user_id = None

        await self._handler.connect_async()

        if self.bot_user_id is None:
            # Retry once in the background so we don't permanently disable
            # mention filtering for the lifetime of this connection.
            try:
                auth_res = await self.app.client.auth_test()
                self.bot_user_id = auth_res.get("user_id")
            except Exception:
                logger.exception("Retry to fetch bot user_id also failed")

        logger.info(
            "%s connected (bot_user_id=%s)",
            self._bot_label,
            self.bot_user_id,
        )

    async def disconnect(self) -> None:
        """Close the Socket Mode WebSocket connection."""
        try:
            await self._handler.close_async()
        except Exception:
            logger.exception("Error closing %s Socket Mode connection", self._bot_label)
        logger.info("%s disconnected", self._bot_label)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def handle_mention(self, event: dict, say) -> None:
        """Respond to @mentions in public channels."""
        if not self.bot_user_id:
            logger.warning(
                "%s: bot_user_id unknown, ignoring app_mention to avoid "
                "responding on behalf of the wrong employee",
                self._bot_label,
            )
            return
        text = event.get("text", "")
        if f"<@{self.bot_user_id}>" not in text:
            return
        await self._process_slack_message(event, say)

    async def handle_message(self, event: dict, say) -> None:
        """Respond to DMs, or thread replies where the bot is already participating."""
        channel_type = event.get("channel_type")
        thread_ts = event.get("thread_ts")
        channel = event.get("channel")
        ts = event.get("ts")

        if channel_type == "im":
            await self._process_slack_message(event, say)
            return

        if thread_ts and thread_ts != ts and channel:
            if not self.bot_user_id:
                logger.warning(
                    "%s: bot_user_id unknown, ignoring thread reply to avoid "
                    "responding on behalf of the wrong employee",
                    self._bot_label,
                )
                return

            text = event.get("text", "")
            if f"<@{self.bot_user_id}>" in text:
                return

            try:
                replies = await self.app.client.conversations_replies(
                    channel=channel,
                    ts=thread_ts,
                    limit=50,
                )
                messages = replies.get("messages", [])
                # Only this bot's OWN prior messages count as "participating" —
                # checking for any bot_id would make every employee bot think
                # it's part of a thread as soon as any other employee replied.
                bot_participated = any(msg.get("user") == self.bot_user_id for msg in messages)
                if bot_participated:
                    await self._process_slack_message(event, say)
            except SlackApiError as e:
                logger.warning(
                    "Slack API error checking thread participation in channel %s, "
                    "thread %s: %s (error code: %s)",
                    channel,
                    thread_ts,
                    e.response.get("error", "unknown"),
                    e.response.status_code,
                )
            except Exception:
                logger.exception("Error checking thread participation for message event")

    # ------------------------------------------------------------------
    # Message processing (abstract — overridden by subclasses)
    # ------------------------------------------------------------------

    async def _process_slack_message(self, event: dict, say) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def _auto_ingest_message(
        self,
        text: str,
        event: dict,
        org: Organization | None,
        employee_id: UUID,
        employee_name: str,
    ) -> None:
        """Auto-ingest a Slack message into org memory (best-effort)."""
        if not (org and org.cognee_dataset_name and org.cognee_system_user_id):
            return
        try:
            speaker = event.get("user", "unknown")
            ch = event.get("channel", "unknown")
            ts = event.get("ts", "")
            ingest_text = f"Slack message from <@{speaker}> in <#{ch}> at {ts}:\n{text}"
            await remember(
                ingest_text,
                org.cognee_dataset_name,
                org.cognee_system_user_id,
                dataset_id=org.cognee_dataset_id,
                background=True,
            )
            try:
                async with async_session_factory() as s2:
                    await record_activity(
                        s2,
                        org.id,
                        "memory_operation",
                        f"Auto-ingested Slack message from {speaker} in #{ch}",
                        employee_id=employee_id,
                        employee_name=employee_name,
                        platform="slack",
                        metadata={
                            "operation": "auto_ingest",
                            "speaker": speaker,
                            "channel": ch,
                        },
                    )
            except Exception:
                pass
        except Exception:
            logger.debug(
                "Slack message Cognee ingest skipped for employee %s",
                employee_id,
                exc_info=True,
            )

    async def _process_file_attachments(
        self,
        files: list[dict],
        org: Organization | None,
        emp: Employee | None,
        employee_id: UUID,
        bot_token: str,
    ) -> None:
        """Download Slack file attachments, save to bucket, ingest into Cognee."""
        if not (files and org and org.cognee_dataset_name and org.cognee_system_user_id and emp):
            return
        backend = get_storage_backend()
        async with httpx.AsyncClient(timeout=30) as http_client:
            for file_info in files:
                try:
                    file_url = file_info.get("url_private")
                    if not file_url:
                        continue

                    if not file_url.startswith("https://files.slack.com/"):
                        logger.warning(
                            "Rejected non-Slack file URL for employee %s: %s",
                            employee_id,
                            file_url,
                        )
                        continue

                    file_size = file_info.get("size", 0)
                    if file_size > _MAX_SLACK_FILE_SIZE:
                        logger.debug(
                            "Slack file %s (%d bytes) exceeds size limit — skipping",
                            file_info.get("name"),
                            file_size,
                        )
                        continue

                    headers = {"Authorization": f"Bearer {bot_token}"}
                    resp = await http_client.get(file_url, headers=headers)
                    resp.raise_for_status()
                    file_bytes = resp.content

                    storage_path = await backend.save(
                        org_id=emp.org_id,
                        filename=file_info.get("name", "slack_file"),
                        content=file_bytes,
                        content_type=file_info.get("mimetype"),
                    )

                    async with async_session_factory() as doc_session:
                        doc = Document(
                            org_id=emp.org_id,
                            employee_id=employee_id,
                            filename=file_info.get("name", "slack_file"),
                            content_type=file_info.get("mimetype"),
                            size_bytes=len(file_bytes),
                            storage_path=storage_path,
                            storage_backend=settings.storage_backend,
                            status="uploaded",
                        )
                        doc_session.add(doc)
                        await doc_session.commit()

                    if settings.storage_backend == "s3":
                        cognee_input = f"s3://{settings.s3_bucket_name}/{storage_path}"
                    else:
                        cognee_input = storage_path
                    await remember(
                        cognee_input,
                        org.cognee_dataset_name,
                        org.cognee_system_user_id,
                        dataset_id=org.cognee_dataset_id,
                        background=True,
                    )

                except Exception:
                    logger.debug(
                        "Slack file attachment ingest skipped (employee=%s, file=%s)",
                        employee_id,
                        file_info.get("name", "unknown"),
                        exc_info=True,
                    )

    async def _cancel_and_respond(
        self,
        text: str,
        employee_id: UUID,
        employee_name: str,
        channel: str,
        thread_ts: str,
        org: Organization | None,
        say,
    ) -> bool:
        """Check for cancel intent and respond if detected. Returns True if cancelled."""
        if not is_cancel_intent(text):
            return False

        root_ts = thread_ts or "direct"
        thread_key = f"slack:{employee_id}:{channel}:{root_ts}"
        async with async_session_factory() as session:
            cancelled = await cancel_active_jobs_for_thread(session, thread_key)
        if cancelled:
            names = ", ".join(j.job_type for j in cancelled)
            if org:
                try:
                    async with async_session_factory() as s:
                        await record_activity(
                            s,
                            org.id,
                            "agent_run",
                            f"Cancelled {len(cancelled)} background task(s): {names}",
                            employee_id=employee_id,
                            employee_name=employee_name,
                            platform="slack",
                            status="cancelled",
                            metadata={
                                "cancelled_jobs": names,
                                "channel": channel,
                                "thread_ts": thread_ts,
                            },
                        )
                except Exception:
                    pass
            await say(
                text=f"🫡 Cancelled: {names}.",
                channel=channel,
                thread_ts=thread_ts,
                username=employee_name,
            )
        else:
            await say(
                text=(
                    "Nothing to cancel — there are no active background tasks in this conversation."
                ),
                channel=channel,
                thread_ts=thread_ts,
                username=employee_name,
            )
        return True

    # ------------------------------------------------------------------
    # File upload helper
    # ------------------------------------------------------------------

    @staticmethod
    def _reconnect_hint(employee_id: UUID | str | None) -> str:
        """Build a link back to the employee's dashboard so the user can
        re-run the Slack OAuth flow and pick up newly required scopes
        (e.g. ``files:write``) that an older connection may be missing."""
        if not employee_id:
            return "Please reconnect Slack from the employee's dashboard and try again."
        url = f"{settings.frontend_url.rstrip('/')}/dashboard/{employee_id}"
        return (
            "This usually means Slack was connected before file uploads were "
            "supported. Reconnect Slack for this employee here, then try again: "
            f"{url}"
        )

    # Slack error codes that indicate the bot token lacks a required scope
    # (as opposed to a transient or file-specific problem).
    _SCOPE_ERROR_CODES = {"missing_scope", "not_allowed_token_type", "invalid_scope"}

    async def _send_files(
        self,
        channel: str,
        files: list[dict],
        thread_ts: str | None = None,
    ) -> list[tuple[str, str]]:
        """Upload agent-generated files (charts, PDFs, etc.) to the Slack channel.

        Returns a list of ``(filename, error_code)`` for any files that
        failed to upload, so callers can tailor the failure message.
        """
        failed_uploads: list[tuple[str, str]] = []
        for f in files:
            filename = f.get("filename", "unknown")
            try:
                await self.app.client.files_upload_v2(
                    channel=channel,
                    file=base64.b64decode(f["data"]),
                    filename=filename,
                    title=f.get("title", filename),
                    thread_ts=thread_ts,
                )
            except SlackApiError as e:
                error_code = (
                    e.response.get("error") if getattr(e, "response", None) else "unknown_error"
                )
                failed_uploads.append((filename, error_code))
                logger.exception(
                    "Slack rejected file upload %s (channel=%s thread_ts=%s error=%s)",
                    filename,
                    channel,
                    thread_ts,
                    error_code,
                )
            except Exception:
                failed_uploads.append((filename, "unknown_error"))
                logger.exception(
                    "Failed to upload file %s (channel=%s thread_ts=%s)",
                    filename,
                    channel,
                    thread_ts,
                )
        return failed_uploads

    @classmethod
    def _file_upload_failure_message(
        cls,
        failed_uploads: list[tuple[str, str]],
        employee_id: UUID | str | None,
    ) -> str:
        """Compose a user-facing message for failed file uploads.

        Only suggests reconnecting Slack when the failure is actually caused
        by a missing OAuth scope; other errors get a more accurate message.
        """
        filenames = ", ".join(name for name, _ in failed_uploads)
        codes = {code for _, code in failed_uploads}
        if codes & cls._SCOPE_ERROR_CODES:
            return (
                f"I created the file, but Slack blocked the attachment upload for: {filenames}. "
                + cls._reconnect_hint(employee_id)
            )
        reasons = ", ".join(sorted(codes))
        return (
            f"I created the file, but Slack rejected the attachment upload for: {filenames} "
            f"(reason: {reasons}). Please try again, or contact support if this keeps happening."
        )

    # ------------------------------------------------------------------
    # Phase 6 — interactive escalation button handlers
    # ------------------------------------------------------------------

    async def _handle_escalation_approve(self, ack, body, client):
        await self._handle_escalation_button(ack, body, client, approved=True)

    async def _handle_escalation_deny(self, ack, body, client):
        await self._handle_escalation_button(ack, body, client, approved=False)

    async def _handle_escalation_button(self, ack, body, client, approved: bool) -> None:
        """Shared logic for Approve / Deny button clicks."""
        await ack()

        action = body.get("actions", [{}])[0]
        value_str = action.get("value", "{}")
        try:
            ctx = json.loads(value_str)
        except json.JSONDecodeError:
            logger.warning("Invalid escalation button value: %s", value_str)
            return

        thread_key: str = ctx.get("thread_key", "")
        channel_id: str = ctx.get("channel_id", "")
        thread_ts: str = ctx.get("thread_ts", "")
        employee_id_str: str = ctx.get("employee_id", "")
        platform: str = ctx.get("platform", "slack")

        if not thread_key or not employee_id_str:
            logger.warning("Escalation button missing thread_key or employee_id")
            return

        try:
            employee_id = UUID(employee_id_str)
        except (ValueError, TypeError):
            logger.warning("Invalid employee_id in escalation button: %s", employee_id_str)
            return

        decision = {
            "approved": approved,
            "by": body.get("user", {}).get("id", "unknown"),
            "note": "",
        }

        response_text = ""
        files: list[dict] = []
        try:
            async with async_session_factory() as session:
                graph, all_tools = await get_graph_for_employee(session, employee_id)
                config = {
                    "configurable": {
                        "db": session,
                        "employee_id": employee_id_str,
                        "all_tools": all_tools,
                        "thread_id": thread_key,
                        "platform": platform,
                        "channel_id": channel_id,
                        "thread_ts": thread_ts,
                    }
                }
                result = await graph.ainvoke(
                    Command(resume=decision),
                    config=config,
                )
                response_text = result.get("response", "")
                files = result.get("files", [])
        except GraphInterrupt:
            logger.info(
                "Graph re-paused during escalation resume (thread=%s)",
                thread_key,
            )
        except Exception:
            logger.exception(
                "Failed to resume graph for escalation (thread=%s)",
                thread_key,
            )
            response_text = "Something went wrong processing the escalation decision."

        try:
            async with async_session_factory() as s:
                emp = await s.get(Employee, employee_id)
                if emp:
                    await record_activity(
                        s,
                        emp.org_id,
                        "human_escalation",
                        f"Escalation {'approved' if approved else 'denied'} by {decision['by']}",
                        employee_id=employee_id,
                        employee_name=emp.name,
                        platform=platform,
                        status="succeeded",
                        metadata={
                            "approved": approved,
                            "channel": channel_id,
                            "thread_ts": thread_ts,
                        },
                    )
        except Exception:
            pass

        decision_text = "✅ Approved" if approved else "❌ Denied"
        decided_by = f"<@{decision['by']}>"
        try:
            await client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text=f"{decision_text} by {decided_by}: {ctx.get('reason', 'Escalation')}",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"{decision_text} by {decided_by}\n"
                                f"*Reason:* {ctx.get('reason', 'Escalation request')}"
                            ),
                        },
                    }
                ],
            )
        except Exception:
            logger.exception("Failed to update manager escalation message")

        if response_text and channel_id:
            try:
                await client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=response_text,
                )
            except Exception:
                logger.exception("Failed to post escalation response to user thread")

        if files and channel_id:
            failed_uploads = await self._send_files(
                channel=channel_id,
                files=files,
                thread_ts=thread_ts,
            )
            if failed_uploads:
                try:
                    await client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        text=self._file_upload_failure_message(failed_uploads, employee_id),
                    )
                except Exception:
                    logger.exception("Failed to post file upload failure notice")

        logger.info(
            "%s escalation resolved: approved=%s by=%s thread=%s",
            self._bot_label,
            approved,
            decision["by"],
            thread_key,
        )


class EmployeeSlackBot(BaseSlackBot):
    """One Slack Socket Mode connection per AI employee.

    Each employee has its own Slack app identity (its own ``xoxb-`` bot token
    and ``xapp-`` app-level token).  The bot responds in all channels by
    default; if the employee has ``channel_assignments`` those act as an
    allowlist — only messages in assigned channels (and DMs) are processed.
    """

    _bot_label: str = "EmployeeSlackBot"

    def __init__(
        self,
        employee_id: UUID,
        bot_token: str,
        app_token: str,
    ) -> None:
        self.employee_id = employee_id
        super().__init__(bot_token, app_token)

    def _build_app(self) -> None:
        import os

        slack_client_id = os.environ.pop("SLACK_CLIENT_ID", None)
        slack_client_secret = os.environ.pop("SLACK_CLIENT_SECRET", None)
        try:
            self.app = AsyncApp(token=self.bot_token)
        finally:
            if slack_client_id is not None:
                os.environ["SLACK_CLIENT_ID"] = slack_client_id
            if slack_client_secret is not None:
                os.environ["SLACK_CLIENT_SECRET"] = slack_client_secret

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def _process_slack_message(self, event: dict, say) -> None:
        """Process an incoming Slack event for this employee."""
        if "bot_id" in event:
            return

        if event.get("channel_type") != "im":
            if not self.bot_user_id:
                logger.warning(
                    "%s: bot_user_id unknown, ignoring channel message to "
                    "avoid responding on behalf of the wrong employee",
                    self._bot_label,
                )
                return
            text = event.get("text", "")
            if f"<@{self.bot_user_id}>" not in text:
                return

        text = event.get("text", "").strip()
        channel = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")
        is_dm = event.get("channel_type") == "im"

        if not is_dm and not await self._is_channel_allowed(channel):
            logger.debug(
                "Channel %s is not assigned to employee %s — ignoring",
                channel,
                self.employee_id,
            )
            return

        if not is_dm and channel:
            try:
                await self.app.client.conversations_join(channel=channel)
            except Exception:
                logger.debug(
                    "Failed to auto-join channel %s (private/lacks channels:join)",
                    channel,
                    exc_info=True,
                )

        employee_name = "OpenHuman Agent"
        org = None
        emp = None
        try:
            async with async_session_factory() as session:
                emp = await session.get(Employee, self.employee_id)
                if emp:
                    employee_name = f"{emp.name} ({emp.role})" if emp.role else emp.name
                    org = await session.scalar(
                        select(Organization).where(Organization.id == emp.org_id)
                    )
        except Exception:
            logger.exception("Failed to fetch employee/org info for Slack event")

        # -- Cancel fast path (before potentially slow ingest/file ops) --
        if await self._cancel_and_respond(
            text,
            self.employee_id,
            employee_name,
            channel,
            thread_ts,
            org,
            say,
        ):
            return

        # Auto-ingest + file processing
        await self._auto_ingest_message(text, event, org, self.employee_id, employee_name)
        files = event.get("files", [])
        await self._process_file_attachments(
            files,
            org,
            emp,
            self.employee_id,
            self.bot_token,
        )

        # Thread recording context for per-tool activity
        if org:
            activity_org_id.set(str(org.id))
        activity_employee_id.set(str(self.employee_id))
        activity_employee_name.set(employee_name)
        activity_platform.set("slack")
        activity_channel_id.set(channel)

        result = await self._run_agent(
            text,
            channel_id=channel,
            thread_ts=thread_ts,
        )

        if result is None:
            if org:
                try:
                    async with async_session_factory() as s:
                        await record_activity(
                            s,
                            org.id,
                            "human_escalation",
                            f"Escalation awaiting approval from: {text[:100]}",
                            employee_id=self.employee_id,
                            employee_name=employee_name,
                            platform="slack",
                            status="awaiting_approval",
                            metadata={
                                "channel": channel,
                                "thread_ts": thread_ts,
                                "slack_user": event.get("user"),
                                "is_dm": is_dm,
                            },
                        )
                except Exception:
                    pass
            return

        response_text = (
            result.get("response", "") or "I processed your request but had no response."
        )
        files = result.get("files", [])

        if org:
            try:
                async with async_session_factory() as s:
                    await record_activity(
                        s,
                        org.id,
                        "agent_conversation",
                        f"Responded to: {text[:100]}",
                        employee_id=self.employee_id,
                        employee_name=employee_name,
                        platform="slack",
                        status="succeeded",
                        description=json.dumps(
                            {
                                "response": response_text[:500],
                                "channel": channel,
                            }
                        ),
                        metadata={
                            "channel": channel,
                            "thread_ts": thread_ts,
                            "slack_user": event.get("user"),
                            "is_dm": is_dm,
                        },
                    )
            except Exception:
                pass

        await say(
            text=response_text,
            channel=channel,
            thread_ts=thread_ts,
            username=employee_name,
        )

        if files:
            failed_uploads = await self._send_files(
                channel=channel,
                files=files,
                thread_ts=thread_ts,
            )
            if failed_uploads:
                await say(
                    text=self._file_upload_failure_message(failed_uploads, self.employee_id),
                    channel=channel,
                    thread_ts=thread_ts,
                    username=employee_name,
                )

    # ------------------------------------------------------------------
    # Channel allowlist
    # ------------------------------------------------------------------

    async def _is_channel_allowed(self, channel_id: str) -> bool:
        """Return ``True`` if this employee should respond in *channel_id*."""
        async with async_session_factory() as session:
            any_assignments = await session.scalar(
                select(ChannelAssignment)
                .where(
                    ChannelAssignment.platform == "slack",
                    ChannelAssignment.employee_id == self.employee_id,
                )
                .limit(1)
            )
            if any_assignments is None:
                return True
            result = await session.execute(
                select(ChannelAssignment).where(
                    ChannelAssignment.platform == "slack",
                    ChannelAssignment.channel_id == channel_id,
                    ChannelAssignment.employee_id == self.employee_id,
                )
            )
            return result.scalars().first() is not None

    # ------------------------------------------------------------------
    # Agent invocation
    # ------------------------------------------------------------------

    async def _run_agent(
        self,
        content: str,
        channel_id: str = "",
        thread_ts: str = "",
    ) -> dict | None:
        """Run the LangGraph agent as this employee."""
        root_ts = thread_ts or "direct"
        thread_key = f"slack:{self.employee_id}:{channel_id}:{root_ts}"

        initial_state = {
            "messages": [HumanMessage(content=content)],
            "platform": "slack",
            "employee_id": str(self.employee_id),
            "tool_round": 0,
        }

        try:
            async with async_session_factory() as session:
                graph, all_tools = await get_graph_for_employee(
                    session,
                    self.employee_id,
                )
                config = {
                    "configurable": {
                        "db": session,
                        "employee_id": str(self.employee_id),
                        "all_tools": all_tools,
                        "thread_id": thread_key,
                        "platform": "slack",
                        "channel_id": channel_id,
                        "thread_ts": thread_ts,
                    }
                }
                result = await graph.ainvoke(initial_state, config=config)
                return result
        except GraphInterrupt:
            logger.info(
                "Graph paused for interactive approval (employee=%s, thread=%s)",
                self.employee_id,
                thread_key,
            )
            return None
        except Exception:
            logger.exception(
                "Agent graph failed for employee %s on Slack",
                self.employee_id,
            )
            return {"response": _SAFE_ERROR_MESSAGE, "files": []}


class WorkspaceSlackBot(BaseSlackBot):
    """Legacy shared-mode Slack bot — one Socket Mode connection per unique
    bot token, routing messages to multiple employees via channel assignments.

    Only used when ``SLACK_IDENTITY_MODE=shared``.  When ``per_employee`` mode
    is active, :class:`EmployeeSlackBot` is used instead (one per employee).
    """

    _bot_label: str = "WorkspaceSlackBot"

    def __init__(
        self,
        bot_token: str,
        app_token: str,
        employee_ids: list[UUID],
    ) -> None:
        self.employee_ids = employee_ids
        self._employee_id_set = frozenset(employee_ids)
        super().__init__(bot_token, app_token)

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def _process_slack_message(self, event: dict, say) -> None:
        """Route an incoming Slack event to the right employee and respond."""
        if "bot_id" in event:
            return

        text = event.get("text", "").strip()
        channel = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")
        is_dm = event.get("channel_type") == "im"

        employee_id = await self._resolve_employee(channel if not is_dm else None)
        if employee_id is None:
            logger.debug(
                "No employee assigned for channel=%s (token=...%s) — ignoring",
                channel,
                self.bot_token[-8:],
            )
            return

        # -- Cancel fast path (before potentially slow ingest/file ops) --
        if await self._cancel_and_respond(
            text,
            employee_id,
            "OpenHuman Agent",
            channel,
            thread_ts,
            None,
            say,
        ):
            return

        employee_name = "OpenHuman Agent"
        org = None
        emp = None
        async with async_session_factory() as session:
            emp = await session.get(Employee, employee_id)
            if emp:
                employee_name = f"{emp.name} ({emp.role})" if emp.role else emp.name
                org = await session.scalar(
                    select(Organization).where(Organization.id == emp.org_id)
                )
                await self._auto_ingest_message(
                    text,
                    event,
                    org,
                    employee_id,
                    employee_name,
                )

        # File processing
        files = event.get("files", [])
        await self._process_file_attachments(
            files,
            org,
            emp,
            employee_id,
            self.bot_token,
        )

        # Thread recording context for per-tool activity
        if org:
            activity_org_id.set(str(org.id))
        activity_employee_id.set(str(employee_id))
        activity_employee_name.set(employee_name)
        activity_platform.set("slack")
        activity_channel_id.set(channel)

        result = await self._run_agent(
            employee_id,
            text,
            channel_id=channel,
            thread_ts=thread_ts,
        )
        if result is None:
            return

        response_text = (
            result.get("response", "") or "I processed your request but had no response."
        )
        files = result.get("files", [])

        await say(
            text=response_text,
            channel=channel,
            thread_ts=thread_ts,
            username=employee_name,
        )

        if files:
            failed_uploads = await self._send_files(
                channel=channel,
                files=files,
                thread_ts=thread_ts,
            )
            if failed_uploads:
                await say(
                    text=self._file_upload_failure_message(failed_uploads, employee_id),
                    channel=channel,
                    thread_ts=thread_ts,
                    username=employee_name,
                )

    # ------------------------------------------------------------------
    # Channel → Employee routing
    # ------------------------------------------------------------------

    async def _resolve_employee(self, channel_id: str | None) -> UUID | None:
        """Return the employee UUID for *channel_id*, or ``None``."""
        async with async_session_factory() as session:
            if channel_id is not None:
                result = await session.execute(
                    select(ChannelAssignment).where(
                        ChannelAssignment.platform == "slack",
                        ChannelAssignment.channel_id == channel_id,
                        ChannelAssignment.employee_id.in_(self._employee_id_set),
                    )
                )
                ca = result.scalars().first()
                if ca is not None:
                    return ca.employee_id

                any_assignments = await session.scalar(
                    select(ChannelAssignment)
                    .where(
                        ChannelAssignment.platform == "slack",
                        ChannelAssignment.employee_id.in_(self._employee_id_set),
                    )
                    .limit(1)
                )
                if any_assignments is not None:
                    return None

            if self.employee_ids:
                return await self._find_unrestricted_employee(session)

            return None

    async def _find_unrestricted_employee(self, session) -> UUID | None:
        """Return first candidate with no Slack channel assignments."""
        result = await session.execute(
            select(ChannelAssignment.employee_id)
            .where(
                ChannelAssignment.platform == "slack",
                ChannelAssignment.employee_id.in_(self._employee_id_set),
            )
            .distinct()
        )
        assigned_ids = {row[0] for row in result.all()}

        for eid in self.employee_ids:
            if eid not in assigned_ids:
                return eid
        return self.employee_ids[0] if self.employee_ids else None

    # ------------------------------------------------------------------
    # Agent invocation
    # ------------------------------------------------------------------

    async def _run_agent(
        self,
        employee_id: UUID,
        content: str,
        channel_id: str = "",
        thread_ts: str = "",
    ) -> dict | None:
        """Run the LangGraph agent as *employee_id*."""
        root_ts = thread_ts or "direct"
        thread_key = f"slack:{employee_id}:{channel_id}:{root_ts}"

        initial_state = {
            "messages": [HumanMessage(content=content)],
            "platform": "slack",
            "employee_id": str(employee_id),
            "tool_round": 0,
        }

        try:
            async with async_session_factory() as session:
                graph, all_tools = await get_graph_for_employee(
                    session,
                    employee_id,
                )
                config = {
                    "configurable": {
                        "db": session,
                        "employee_id": str(employee_id),
                        "all_tools": all_tools,
                        "thread_id": thread_key,
                        "platform": "slack",
                        "channel_id": channel_id,
                        "thread_ts": thread_ts,
                    }
                }
                result = await graph.ainvoke(initial_state, config=config)
                return result
        except GraphInterrupt:
            logger.info(
                "Graph paused for interactive approval (employee=%s, thread=%s)",
                employee_id,
                thread_key,
            )
            return None
        except Exception:
            logger.exception(
                "Agent graph failed for employee %s on Slack",
                employee_id,
            )
            return {"response": _SAFE_ERROR_MESSAGE, "files": []}
