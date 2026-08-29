"""ArmorIQ-governed MCP execution for the constrained Zop agent runtime."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from armoriq_sdk import SessionOptions
from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from app.agent.armoriq import get_armoriq_client
from app.core.config import settings

logger = logging.getLogger(__name__)

MCP_SLUG = "openhuman-zop"
MCP_ACTION = "generate_response"
HR_MCP_SLUG = "openhuman-hr"
HR_RESPONSE_ACTION = "answer_hr_question"
HR_APPROVAL_ACTION = "prepare_pto_request"
SALES_MCP_SLUG = "openhuman-sales"
SALES_RESPONSE_ACTION = "draft_sales_response"
SALES_APPROVAL_ACTION = "prepare_discount_request"
SUPPORT_MCP_SLUG = "openhuman-support"
SUPPORT_RESPONSE_ACTION = "draft_support_response"
SUPPORT_APPROVAL_ACTION = "prepare_refund_request"

ROLE_RESPONSE_ACTIONS = {
    "hr": (HR_MCP_SLUG, HR_RESPONSE_ACTION),
    "hr_specialist": (HR_MCP_SLUG, HR_RESPONSE_ACTION),
    "sales": (SALES_MCP_SLUG, SALES_RESPONSE_ACTION),
    "sales_rep": (SALES_MCP_SLUG, SALES_RESPONSE_ACTION),
    "support": (SUPPORT_MCP_SLUG, SUPPORT_RESPONSE_ACTION),
    "support_agent": (SUPPORT_MCP_SLUG, SUPPORT_RESPONSE_ACTION),
}

router = APIRouter(prefix="/api/agent/armoriq", tags=["agent"])

_registration_lock = asyncio.Lock()
_registration_ready = False


class ArmorIQRuntimeError(RuntimeError):
    """Raised when the governed Zop execution path cannot complete safely."""


class GenerateResponseInput(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    system_prompt: str = Field(min_length=1, max_length=20_000)
    employee_id: str = Field(min_length=1, max_length=100)


class PTORequestInput(BaseModel):
    employee_name: str = Field(min_length=1, max_length=200)
    start_date: str = Field(min_length=8, max_length=40)
    end_date: str = Field(min_length=8, max_length=40)
    reason: str = Field(min_length=1, max_length=2_000)


class DiscountRequestInput(BaseModel):
    prospect_name: str = Field(min_length=1, max_length=200)
    discount_percent: float = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=2_000)


class RefundRequestInput(BaseModel):
    customer_reference: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=1_000_000)
    reason: str = Field(min_length=1, max_length=2_000)


MCP_SERVER_DEFINITIONS: dict[str, dict[str, Any]] = {
    MCP_SLUG: {
        "description": "OpenHuman governed general response generation",
        "path": "",
        "tools": {
            MCP_ACTION: {
                "description": "Generate a governed general OpenHuman employee response",
                "input_model": GenerateResponseInput,
                "handler": "openai",
            }
        },
    },
    HR_MCP_SLUG: {
        "description": "OpenHuman HR coworker tools with approval boundaries",
        "path": "/hr",
        "tools": {
            HR_RESPONSE_ACTION: {
                "description": "Answer an HR or people-operations question",
                "input_model": GenerateResponseInput,
                "handler": "openai",
            },
            HR_APPROVAL_ACTION: {
                "description": "Prepare a PTO request for human approval without submitting it",
                "input_model": PTORequestInput,
                "handler": "approval_request",
            },
        },
    },
    SALES_MCP_SLUG: {
        "description": "OpenHuman sales coworker tools with commercial guardrails",
        "path": "/sales",
        "tools": {
            SALES_RESPONSE_ACTION: {
                "description": "Draft a governed sales or lead-qualification response",
                "input_model": GenerateResponseInput,
                "handler": "openai",
            },
            SALES_APPROVAL_ACTION: {
                "description": "Prepare a discount proposal for human approval without sending it",
                "input_model": DiscountRequestInput,
                "handler": "approval_request",
            },
        },
    },
    SUPPORT_MCP_SLUG: {
        "description": "OpenHuman customer-support tools with refund guardrails",
        "path": "/support",
        "tools": {
            SUPPORT_RESPONSE_ACTION: {
                "description": "Draft a governed customer-support response",
                "input_model": GenerateResponseInput,
                "handler": "openai",
            },
            SUPPORT_APPROVAL_ACTION: {
                "description": "Prepare a refund request for human approval without issuing it",
                "input_model": RefundRequestInput,
                "handler": "approval_request",
            },
        },
    },
}


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
    """Idempotently upsert OpenHuman's role MCPs and safe default policy."""
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
                    "id": slug,
                    "url": (settings.armoriq_mcp_public_url.rstrip("/") + definition["path"]),
                    "description": definition["description"],
                    "auth": {
                        "type": "bearer",
                        "token": settings.armoriq_mcp_bearer_token,
                    },
                }
                for slug, definition in MCP_SERVER_DEFINITIONS.items()
            ],
            "policy": {
                "allow": [
                    f"{MCP_SLUG}.{MCP_ACTION}",
                    f"{HR_MCP_SLUG}.{HR_RESPONSE_ACTION}",
                    f"{SALES_MCP_SLUG}.{SALES_RESPONSE_ACTION}",
                    f"{SUPPORT_MCP_SLUG}.{SUPPORT_RESPONSE_ACTION}",
                ],
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


def _extract_action_result(result: Any) -> dict[str, Any]:
    """Normalize the MCP proxy's supported response shapes."""
    if isinstance(result, str):
        try:
            return _extract_action_result(json.loads(result))
        except json.JSONDecodeError:
            if result:
                return {"response": result}

    if isinstance(result, dict):
        response = result.get("response")
        if isinstance(response, str) and response:
            return result
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "text":
                    continue
                text_value = item.get("text")
                if isinstance(text_value, str):
                    try:
                        return _extract_action_result(json.loads(text_value))
                    except json.JSONDecodeError:
                        if text_value:
                            return {"response": text_value}

    raise ArmorIQRuntimeError("ArmorIQ MCP returned an invalid response")


def _extract_response_content(result: Any) -> str:
    payload = _extract_action_result(result)
    response = payload.get("response")
    if not isinstance(response, str) or not response:
        raise ArmorIQRuntimeError("ArmorIQ MCP returned no response content")
    return response


def resolve_role_response_action(employee_kind: str | None) -> tuple[str, str]:
    """Map an employee template/type to its least-privilege MCP boundary."""
    normalized = (employee_kind or "").strip().lower().replace("-", "_")
    return ROLE_RESPONSE_ACTIONS.get(normalized, (MCP_SLUG, MCP_ACTION))


async def generate_response_through_armoriq(
    *,
    content: str,
    system_prompt: str,
    employee_id: str,
    user_email: str,
    employee_kind: str | None = None,
) -> tuple[str, str, str, str]:
    """Execute OpenAI generation as a signed, policy-enforced MCP action."""
    await ensure_openhuman_mcp_registered()
    mcp_slug, action = resolve_role_response_action(employee_kind)
    params = {
        "content": content,
        "system_prompt": system_prompt,
        "employee_id": employee_id,
    }

    def execute() -> tuple[str, str, str, str]:
        client = get_armoriq_client()
        session = client.for_user(user_email).start_session(
            SessionOptions(
                mode="proxy",
                default_mcp_name=mcp_slug,
                llm=settings.openai_model,
                validity_seconds=settings.armoriq_approval_timeout_seconds + 60,
            )
        )
        tool_name = f"{mcp_slug}__{action}"
        try:
            token = session.start_plan(
                [{"name": tool_name, "args": params}],
                goal=content,
            )
            decision = session.check(tool_name, params, user_email=user_email)
            if not decision.allowed:
                raise ArmorIQRuntimeError(
                    f"ArmorIQ {decision.action}: {decision.reason or 'policy denied action'}"
                )
            raw_result = session.dispatch(tool_name, params)
            payload = _extract_action_result(raw_result)
            usage = payload.get("usage") or {}
            if isinstance(usage, dict):
                session.record_generation(
                    model=str(payload.get("model") or settings.openai_model),
                    input_tokens=float(usage.get("prompt_tokens") or 0),
                    output_tokens=float(usage.get("completion_tokens") or 0),
                    finish_reason=payload.get("finish_reason"),
                )
            response = payload.get("response")
            if not isinstance(response, str) or not response:
                raise ArmorIQRuntimeError("ArmorIQ MCP returned no response content")
            session.flush_observability()
            return response, token.plan_hash, mcp_slug, action
        finally:
            session.close()

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(execute),
            timeout=float(settings.armoriq_request_timeout_seconds) + 60,
        )
    except TimeoutError as exc:
        raise ArmorIQRuntimeError("ArmorIQ invocation timed out") from exc


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


async def _run_openai_action(data: GenerateResponseInput) -> dict[str, Any]:
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
    usage = payload.get("usage") or {}
    return {
        "response": content,
        "model": settings.openai_model,
        "usage": {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
        },
        "finish_reason": payload["choices"][0].get("finish_reason"),
    }


def _approval_request_result(server_slug: str, action: str, data: BaseModel) -> dict[str, Any]:
    """Return a side-effect-free proposal; ArmorIQ decides if it may execute."""
    return {
        "status": "prepared_for_human_approval",
        "mcp": server_slug,
        "action": action,
        "request": data.model_dump(mode="json"),
        "side_effect_performed": False,
    }


@router.get("/status")
async def armoriq_status() -> dict[str, Any]:
    """Expose a secret-free, judge-friendly view of the live governance boundary."""
    await ensure_openhuman_mcp_registered()
    return {
        "status": "ready",
        "agent": "openhuman",
        "default_action": "block",
        "servers": [
            {
                "slug": slug,
                "description": definition["description"],
                "tools": list(definition["tools"]),
            }
            for slug, definition in MCP_SERVER_DEFINITIONS.items()
        ],
    }


async def _handle_mcp_request(
    message: dict[str, Any],
    server_slug: str = MCP_SLUG,
) -> dict[str, Any]:
    definition = MCP_SERVER_DEFINITIONS.get(server_slug)
    if definition is None:
        return _jsonrpc_error(message.get("id"), -32601, "Unknown MCP server")
    method = message.get("method")
    message_id = message.get("id")
    if method == "initialize":
        return _jsonrpc_result(
            message_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": server_slug, "version": "1.1.0"},
            },
        )
    if method == "tools/list":
        return _jsonrpc_result(
            message_id,
            {
                "tools": [
                    {
                        "name": name,
                        "description": tool["description"],
                        "inputSchema": tool["input_model"].model_json_schema(),
                    }
                    for name, tool in definition["tools"].items()
                ]
            },
        )
    if method == "tools/call":
        params = message.get("params") or {}
        tool_name = params.get("name")
        tool = definition["tools"].get(tool_name)
        if tool is None:
            return _jsonrpc_error(message_id, -32601, "Unknown tool")
        try:
            data = tool["input_model"].model_validate(params.get("arguments") or {})
            if tool["handler"] == "openai":
                result = await _run_openai_action(data)
            else:
                result = _approval_request_result(server_slug, tool_name, data)
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
    response = await _handle_mcp_request(message, MCP_SLUG)

    async def stream() -> AsyncIterator[str]:
        yield f"event: message\ndata: {json.dumps(response)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/mcp/{server_kind}")
async def role_mcp_endpoint(
    server_kind: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    """Serve one role-specific MCP inventory through the ArmorIQ proxy."""
    server_slug = f"openhuman-{server_kind}"
    if server_slug not in MCP_SERVER_DEFINITIONS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown MCP server")
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
    response = await _handle_mcp_request(message, server_slug)

    async def stream() -> AsyncIterator[str]:
        yield f"event: message\ndata: {json.dumps(response)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
