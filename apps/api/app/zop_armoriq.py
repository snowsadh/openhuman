"""ArmorIQ-governed MCP execution for the constrained Zop agent runtime."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from armoriq_sdk.models import InvokeOptions
from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from app.agent.armoriq import get_armoriq_client, mint_intent_token
from app.core.config import settings

logger = logging.getLogger(__name__)

MCP_SLUG = "openhuman-zop"
MCP_ACTION = "generate_response"

router = APIRouter(prefix="/api/agent/armoriq", tags=["agent"])

_registration_lock = asyncio.Lock()
_registration_ready = False


class ArmorIQRuntimeError(RuntimeError):
    """Raised when the governed Zop execution path cannot complete safely."""


class GenerateResponseInput(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    system_prompt: str = Field(min_length=1, max_length=20_000)
    employee_id: str = Field(min_length=1, max_length=100)


def _require_runtime_configuration() -> None:
    if not settings.armoriq_api_key:
        raise ArmorIQRuntimeError("ArmorIQ API key is not configured")
    if not settings.armoriq_mcp_bearer_token:
        raise ArmorIQRuntimeError("ArmorIQ MCP bearer token is not configured")
    if not settings.armoriq_mcp_public_url.startswith("https://"):
        raise ArmorIQRuntimeError("ArmorIQ MCP public URL must use HTTPS")
    if not settings.openai_api_key:
        raise ArmorIQRuntimeError("OpenAI API key is not configured")


async def ensure_openhuman_mcp_registered() -> None:
    """Idempotently upsert the Zop MCP and its narrow allow policy."""
    global _registration_ready
    if _registration_ready:
        return

    _require_runtime_configuration()
    async with _registration_lock:
        if _registration_ready:
            return

        payload = {
            "version": "v1",
            "identity": {
                "api_key": settings.armoriq_api_key,
                "user_id": "openhuman-service",
                "agent_id": "openhuman",
            },
            "environment": "production",
            "proxy": {
                "url": settings.armoriq_proxy_url,
                "timeout": settings.armoriq_request_timeout_seconds,
                "max_retries": 3,
            },
            "mcp_servers": [
                {
                    "id": MCP_SLUG,
                    "url": settings.armoriq_mcp_public_url,
                    "description": "OpenHuman governed response generation",
                    "auth": {
                        "type": "bearer",
                        "token": settings.armoriq_mcp_bearer_token,
                    },
                }
            ],
            "policy": {
                "allow": [f"{MCP_SLUG}.{MCP_ACTION}"],
                "deny": [],
            },
            "intent": {
                "ttl_seconds": settings.armoriq_approval_timeout_seconds + 60,
                "require_csrg": True,
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=float(settings.armoriq_request_timeout_seconds),
                follow_redirects=True,
            ) as client:
                response = await client.post(
                    settings.armoriq_register_url,
                    headers={
                        "Authorization": f"Bearer {settings.armoriq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if response.status_code >= 400:
                raise ArmorIQRuntimeError(
                    f"ArmorIQ registration returned HTTP {response.status_code}"
                )
        except httpx.HTTPError as exc:
            raise ArmorIQRuntimeError("ArmorIQ registration request failed") from exc

        _registration_ready = True
        logger.info("ArmorIQ MCP registration is ready")


def _extract_response_content(result: Any) -> str:
    """Normalize the MCP proxy's supported response shapes."""
    if isinstance(result, str):
        try:
            return _extract_response_content(json.loads(result))
        except json.JSONDecodeError:
            if result:
                return result

    if isinstance(result, dict):
        response = result.get("response")
        if isinstance(response, str) and response:
            return response
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "text":
                    continue
                text_value = item.get("text")
                if isinstance(text_value, str):
                    try:
                        return _extract_response_content(json.loads(text_value))
                    except json.JSONDecodeError:
                        if text_value:
                            return text_value

    raise ArmorIQRuntimeError("ArmorIQ MCP returned an invalid response")


async def generate_response_through_armoriq(
    *,
    content: str,
    system_prompt: str,
    employee_id: str,
    user_email: str,
) -> tuple[str, str]:
    """Execute OpenAI generation as a signed, policy-enforced MCP action."""
    await ensure_openhuman_mcp_registered()
    params = {
        "content": content,
        "system_prompt": system_prompt,
        "employee_id": employee_id,
    }
    token = await asyncio.to_thread(
        mint_intent_token,
        prompt=content,
        steps=[
            {
                "mcp": MCP_SLUG,
                "action": MCP_ACTION,
                "tool": MCP_ACTION,
                "params": params,
                "description": "Generate the authorized OpenHuman employee response",
            }
        ],
        user_email=user_email,
        metadata={"employee_id": employee_id, "platform": "zop"},
    )
    options = InvokeOptions(wait_for_approval=False, user_email=user_email)
    try:
        invocation = await asyncio.wait_for(
            asyncio.to_thread(
                get_armoriq_client().invoke_with_policy,
                MCP_SLUG,
                MCP_ACTION,
                token,
                params,
                options,
            ),
            timeout=float(settings.armoriq_request_timeout_seconds) + 60,
        )
    except TimeoutError as exc:
        raise ArmorIQRuntimeError("ArmorIQ invocation timed out") from exc

    return _extract_response_content(invocation.result), token.plan_hash


def _authorized(authorization: str | None) -> bool:
    expected = settings.armoriq_mcp_bearer_token
    if not expected or not authorization or not authorization.startswith("Bearer "):
        return False
    return hmac.compare_digest(authorization.removeprefix("Bearer "), expected)


def _jsonrpc_result(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _jsonrpc_error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": message},
    }


async def _run_openai_action(data: GenerateResponseInput) -> dict[str, str]:
    base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": data.system_prompt},
                        {"role": "user", "content": data.content},
                    ],
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise ArmorIQRuntimeError("OpenAI action failed") from exc
    if not isinstance(content, str) or not content:
        raise ArmorIQRuntimeError("OpenAI returned an empty response")
    return {"response": content, "model": settings.openai_model}


async def _handle_mcp_request(message: dict[str, Any]) -> dict[str, Any]:
    method = message.get("method")
    message_id = message.get("id")
    if method == "initialize":
        return _jsonrpc_result(
            message_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": MCP_SLUG, "version": "1.0.0"},
            },
        )
    if method == "tools/list":
        return _jsonrpc_result(
            message_id,
            {
                "tools": [
                    {
                        "name": MCP_ACTION,
                        "description": "Generate an OpenHuman employee response",
                        "inputSchema": GenerateResponseInput.model_json_schema(),
                    }
                ]
            },
        )
    if method == "tools/call":
        params = message.get("params") or {}
        if params.get("name") != MCP_ACTION:
            return _jsonrpc_error(message_id, -32601, "Unknown tool")
        try:
            data = GenerateResponseInput.model_validate(params.get("arguments") or {})
            result = await _run_openai_action(data)
        except ValidationError:
            return _jsonrpc_error(message_id, -32602, "Invalid tool arguments")
        except ArmorIQRuntimeError:
            logger.exception("Governed OpenAI MCP action failed")
            return _jsonrpc_error(message_id, -32000, "Tool execution failed")
        return _jsonrpc_result(
            message_id,
            {"content": [{"type": "text", "text": json.dumps(result)}]},
        )
    return _jsonrpc_error(message_id, -32601, "Method not found")


@router.post("/mcp")
async def mcp_endpoint(
    request: Request,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """Serve the authenticated MCP endpoint used only by the ArmorIQ proxy."""
    if not _authorized(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid MCP authorization",
        )
    try:
        message = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON-RPC request",
        ) from exc
    response = await _handle_mcp_request(message)

    async def stream() -> AsyncIterator[str]:
        yield f"event: message\ndata: {json.dumps(response)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
