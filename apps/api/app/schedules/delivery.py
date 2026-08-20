from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

import aiohttp
from slack_sdk.web.async_client import AsyncWebClient

from app.employees.models import Employee
from app.employees.service import decrypt_discord_token, decrypt_slack_token


class DeliveryError(RuntimeError):
    pass


def is_silent_response(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True
    first = stripped.splitlines()[0].strip().upper()
    return first.startswith("[SILENT]") or stripped.upper() in {"SILENT", "NO_REPLY", "NO REPLY"}


def _file_value(item: Any, key: str, default: str = "") -> str:
    if isinstance(item, dict):
        return str(item.get(key, default))
    return str(getattr(item, key, default))


async def deliver_result(
    employee: Employee,
    *,
    platform: str,
    channel_id: str,
    thread_id: str | None,
    text: str,
    files: list[Any],
    idempotency_key: str,
) -> None:
    if platform == "slack":
        token = decrypt_slack_token(employee)
        if not token:
            raise DeliveryError("Slack bot token is not configured for this employee")
        client = AsyncWebClient(token=token)
        response = await client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_id,
            text=text,
            client_msg_id=idempotency_key,
        )
        if not response.get("ok"):
            raise DeliveryError(f"Slack rejected scheduled delivery: {response.get('error', 'unknown')}")
        for item in files:
            raw = BytesIO(base64.b64decode(_file_value(item, "data")))
            await client.files_upload_v2(
                channel=channel_id,
                thread_ts=thread_id,
                filename=_file_value(item, "filename", "attachment"),
                file=raw,
                title=_file_value(item, "title", "Scheduled attachment"),
            )
        return

    if platform == "discord":
        token = decrypt_discord_token(employee)
        if not token:
            raise DeliveryError("Discord bot token is not configured for this employee")
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        payload: dict[str, Any] = {
            "content": text[:2000],
            "nonce": idempotency_key,
            "enforce_nonce": True,
        }
        if thread_id:
            payload["message_reference"] = {"message_id": thread_id}
        form = aiohttp.FormData()
        form.add_field("payload_json", __import__("json").dumps(payload), content_type="application/json")
        for index, item in enumerate(files):
            form.add_field(
                f"files[{index}]",
                base64.b64decode(_file_value(item, "data")),
                filename=_file_value(item, "filename", f"attachment-{index}"),
                content_type=_file_value(item, "content_type", "application/octet-stream"),
            )
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, data=form, headers={"Authorization": f"Bot {token}"}, timeout=30
            ) as response:
                if response.status not in (200, 201):
                    body = (await response.text())[:300]
                    raise DeliveryError(f"Discord rejected scheduled delivery ({response.status}): {body}")
        return

    raise DeliveryError(f"Unsupported delivery platform: {platform}")
