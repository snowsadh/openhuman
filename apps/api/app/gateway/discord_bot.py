import asyncio
import base64
import io
import json
import logging
from uuid import UUID

import discord
import httpx
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphInterrupt
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

# Safe fallback message exposed to public channels — never includes raw
# exception details.
_SAFE_ERROR_MESSAGE = (
    "I ran into a problem processing your request. Please try again later."
)

_MAX_DISCORD_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_TYPING_HEARTBEAT_INTERVAL = 5  # seconds


class EmployeeDiscordBot(discord.Client):
    """Discord Client wrapper representing a single AI employee instance."""

    def __init__(self, employee_id: UUID, *args, **kwargs):  # type: ignore[no-untyped-def]
        intents = discord.Intents.default()
        intents.message_content = True
        kwargs["intents"] = intents
        super().__init__(*args, **kwargs)

        self.employee_id = employee_id

    async def on_ready(self) -> None:
        logger.info(
            "Discord bot for employee %s connected as %s", self.employee_id, self.user,
        )

    # ------------------------------------------------------------------
    # Message filter helpers
    # ------------------------------------------------------------------

    def _is_dm(self, message: discord.Message) -> bool:
        return isinstance(message.channel, discord.DMChannel)

    def _is_mentioned(self, message: discord.Message) -> bool:
        return self.user in message.mentions if self.user else False

    async def _is_assigned_channel(self, channel_id: int) -> bool:
        """Return True if this employee has no channel assignments (respond
        everywhere), or if *channel_id* appears in their assignments."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(ChannelAssignment).where(
                    ChannelAssignment.employee_id == self.employee_id,
                    ChannelAssignment.platform == "discord",
                )
            )
            assignments = result.scalars().all()
        if not assignments:
            return True
        return any(a.channel_id == str(channel_id) for a in assignments)

    # ------------------------------------------------------------------
    # Typing heartbeat for long-running agent invocations
    # ------------------------------------------------------------------

    async def _typing_heartbeat(self, channel: discord.abc.Messageable) -> None:
        """Send typing indicator periodically until cancelled."""
        try:
            while True:
                await channel.trigger_typing()
                await asyncio.sleep(_TYPING_HEARTBEAT_INTERVAL)
        except (asyncio.CancelledError, Exception):
            pass

    # ------------------------------------------------------------------
    # Memory auto-ingestion
    # ------------------------------------------------------------------

    async def _auto_ingest_message(
        self,
        text: str,
        author_id: int,
        channel_id: str,
        org: Organization | None,
    ) -> None:
        """Auto-ingest a Discord message into org memory (best-effort)."""
        if not (org and org.cognee_dataset_name and org.cognee_system_user_id):
            return
        try:
            ingest_text = (
                f"Discord message from user {author_id} in channel {channel_id}:\n{text}"
            )
            await remember(
                ingest_text,
                org.cognee_dataset_name,
                org.cognee_system_user_id,
                dataset_id=org.cognee_dataset_id,
                background=True,
            )
        except Exception:
            logger.debug(
                "Discord message Cognee ingest skipped for employee %s",
                self.employee_id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # File attachment processing
    # ------------------------------------------------------------------

    async def _process_file_attachments(
        self,
        attachments: list[discord.Attachment],
        org: Organization | None,
        emp: Employee | None,
    ) -> None:
        """Download Discord file attachments, save to bucket, ingest into Cognee."""
        if not (attachments and org and org.cognee_dataset_name
                and org.cognee_system_user_id and emp):
            return
        backend = get_storage_backend()
        async with httpx.AsyncClient(timeout=30) as http_client:
            for attachment in attachments:
                try:
                    if attachment.size > _MAX_DISCORD_FILE_SIZE:
                        logger.debug(
                            "Discord file %s (%d bytes) exceeds size limit — skipping",
                            attachment.filename,
                            attachment.size,
                        )
                        continue

                    resp = await http_client.get(attachment.url)
                    resp.raise_for_status()
                    file_bytes = resp.content

                    storage_path = await backend.save(
                        org_id=emp.org_id,
                        filename=attachment.filename,
                        content=file_bytes,
                        content_type=attachment.content_type,
                    )

                    async with async_session_factory() as doc_session:
                        doc = Document(
                            org_id=emp.org_id,
                            employee_id=self.employee_id,
                            filename=attachment.filename,
                            content_type=attachment.content_type,
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
                        "Discord file attachment ingest skipped (employee=%s, file=%s)",
                        self.employee_id,
                        attachment.filename,
                        exc_info=True,
                    )

    # ------------------------------------------------------------------
    # Message handler
    # ------------------------------------------------------------------

    async def on_message(self, message: discord.Message) -> None:
        # Ignore messages from the bot itself
        if message.author == self.user:
            return

        # Must be a DM or a mention
        if not self._is_dm(message) and not self._is_mentioned(message):
            return

        # Channel assignment filter — skip if employee is only supposed to
        # respond in specific channels.
        if not self._is_dm(message):
            if not await self._is_assigned_channel(message.channel.id):
                return

        # Clean the content (remove the bot mention tag)
        content = message.content
        if not self._is_dm(message) and self._is_mentioned(message):
            content = content.replace(
                f"<@!{self.user.id}>", ""
            ).replace(
                f"<@{self.user.id}>", ""
            )
        content = content.strip()

        # -- Phase 3: lightweight cancel keyword fast path -------------------
        if is_cancel_intent(content):
            channel_id = str(message.channel.id)
            message_id = str(message.id)
            thread_key = f"discord:{self.employee_id}:{channel_id}:{message_id}"
            async with async_session_factory() as session:
                cancelled = await cancel_active_jobs_for_thread(session, thread_key)
            if cancelled:
                names = ", ".join(j.job_type for j in cancelled)
                await message.reply(f"🫡 Cancelled: {names}.")
                try:
                    async with async_session_factory() as s:
                        emp = await s.get(Employee, self.employee_id)
                        if emp:
                            await record_activity(
                                s,
                                emp.org_id,
                                "agent_run",
                                f"Cancelled {len(cancelled)} background task(s): {names}",
                                employee_id=self.employee_id,
                                employee_name=emp.name,
                                platform="discord",
                                status="cancelled",
                                metadata={
                                    "cancelled_jobs": names,
                                    "channel_id": str(message.channel.id),
                                },
                            )
                except Exception:
                    pass
            else:
                await message.reply(
                    "Nothing to cancel — there are no active "
                    "background tasks in this conversation."
                )
            return

        # Fetch employee + org info
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
            logger.exception("Failed to fetch employee/org info for Discord event")

        # Auto-ingest + file processing
        await self._auto_ingest_message(content, message.author.id, str(message.channel.id), org)
        await self._process_file_attachments(message.attachments, org, emp)

        # Thread recording context for per-tool activity
        if org:
            activity_org_id.set(str(org.id))
        activity_employee_name.set(employee_name)
        activity_employee_id.set(str(self.employee_id))
        activity_platform.set("discord")
        activity_channel_id.set(str(message.channel.id))

        # Typing heartbeat while agent runs (long-running agents can exceed
        # Discord's default typing timeout)
        heartbeat_task = asyncio.ensure_future(self._typing_heartbeat(message.channel))

        try:
            result = await self._run_agent(
                content,
                channel_id=str(message.channel.id),
                message_id=str(message.id),
            )
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        # GraphInterrupt (HITL pause) — no response to send yet
        if result is None:
            if org:
                try:
                    async with async_session_factory() as s:
                        await record_activity(
                            s,
                            org.id,
                            "human_escalation",
                            f"Escalation awaiting approval from: {content[:100]}",
                            employee_id=self.employee_id,
                            employee_name=employee_name,
                            platform="discord",
                            status="awaiting_approval",
                            metadata={
                                "channel_id": str(message.channel.id),
                                "discord_user_id": str(message.author.id),
                                "is_dm": self._is_dm(message),
                            },
                        )
                except Exception:
                    pass
            return

        response_text = (
            result.get("response", "") or "I processed your request but had no response."
        )
        files = result.get("files", [])

        # Record activity
        try:
            async with async_session_factory() as s:
                emp = await s.get(Employee, self.employee_id)
                if emp:
                    await record_activity(
                        s,
                        emp.org_id,
                        "agent_conversation",
                        f"Responded to: {content[:100]}",
                        employee_id=self.employee_id,
                        employee_name=employee_name,
                        platform="discord",
                        status="succeeded",
                        description=json.dumps({
                            "response": response_text[:500] if response_text else None,
                            "channel_id": str(message.channel.id),
                        }),
                        metadata={
                            "channel_id": str(message.channel.id),
                            "message_id": str(message.id),
                            "discord_user_id": str(message.author.id),
                            "is_dm": self._is_dm(message),
                        },
                    )
        except Exception:
            pass

        # Discord message character limit — chunk at 2000
        for i in range(0, len(response_text), 2000):
            await message.reply(response_text[i : i + 2000])

        # Upload agent-generated files as Discord attachments
        if files:
            for f in files:
                filename = f.get("filename", "unknown")
                try:
                    file_bytes = base64.b64decode(f["data"])
                    discord_file = discord.File(
                        io.BytesIO(file_bytes),
                        filename=filename,
                    )
                    await message.reply(file=discord_file)
                except Exception:
                    logger.exception(
                        "Failed to upload file %s to Discord for employee %s",
                        filename, self.employee_id,
                    )
                    await message.reply(
                        f"I created **{filename}** but couldn't attach it here. "
                        "Please check the employee dashboard to download it."
                    )

    # ------------------------------------------------------------------
    # Agent invocation
    # ------------------------------------------------------------------

    async def _run_agent(
        self,
        content: str,
        channel_id: str = "",
        message_id: str = "",
    ) -> dict | None:
        """Run the LangGraph agent with a fresh DB session.

        Returns:
          * A ``dict`` with ``"response"`` and ``"files"`` keys on success or
            recoverable error (caller must check ``"error"`` for error state).
          * ``None`` when the graph pauses for interactive approval (HITL
            escalation).

        Never leaks raw exception details to the caller — returns a safe
        fallback message on failure.
        """
        root_id = message_id or "direct"
        thread_key = f"discord:{self.employee_id}:{channel_id}:{root_id}"

        initial_state = {
            "messages": [HumanMessage(content=content)],
            "platform": "discord",
            "employee_id": str(self.employee_id),
            "tool_round": 0,
        }

        try:
            async with async_session_factory() as session:
                graph, all_tools = await get_graph_for_employee(
                    session, self.employee_id,
                )
                config = {
                    "configurable": {
                        "db": session,
                        "employee_id": str(self.employee_id),
                        "all_tools": all_tools,
                        "thread_id": thread_key,
                        "platform": "discord",
                        "channel_id": channel_id,
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
                "Agent graph failed for employee %s on Discord", self.employee_id,
            )
            return {"response": _SAFE_ERROR_MESSAGE, "files": []}
