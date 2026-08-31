"""OpenHuman-owned MCP adapters for n8n and Zendesk."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import Response

from app.mcp.credential_package import unpack_adapter_credential

router = APIRouter(prefix="/api/mcp/adapters", tags=["mcp-adapters"])

_ZENDESK_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_ticket",
        "description": "Read one Zendesk ticket by numeric ID",
        "inputSchema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "integer"}},
            "required": ["ticket_id"],
        },
    },
    {
        "name": "search_tickets",
        "description": "Search Zendesk tickets using a scoped query",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_user",
        "description": "Read one Zendesk user by numeric ID",
        "inputSchema": {
            "type": "object",
            "properties": {"user_id": {"type": "integer"}},
            "required": ["user_id"],
        },
    },
    {
        "name": "search_help_center",
        "description": "Search Zendesk Help Center articles",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "reply_to_ticket",
        "description": "Add a public or internal reply to a Zendesk ticket",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "integer"},
                "body": {"type": "string"},
                "public": {"type": "boolean", "default": True},
            },
            "required": ["ticket_id", "body"],
        },
    },
    {
        "name": "update_ticket_status",
        "description": "Update a Zendesk ticket status",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "integer"},
                "status": {
                    "type": "string",
                    "enum": ["new", "open", "pending", "hold", "solved", "closed"],
                },
            },
            "required": ["ticket_id", "status"],
        },
    },
]


def _rpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _tool_content(payload: Any) -> dict[str, Any]:
    import json

    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, separators=(",", ":"), default=str),
            }
        ]
    }


def _require_package(value: str | None, kind: str) -> dict[str, Any]:
    if not value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credential")
    try:
        return unpack_adapter_credential(value, kind)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid adapter credential",
        ) from exc


def _validate_zendesk_url(value: str) -> str:
    parsed = urlparse(value.rstrip("/"))
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host.endswith(".zendesk.com"):
        raise ValueError("Zendesk account URL must be https://<subdomain>.zendesk.com")
    return f"https://{host}"


async def _validate_public_https_url(value: str) -> str:
    parsed = urlparse(value.rstrip("/"))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("n8n MCP URL must be a credential-free HTTPS URL")

    def resolve() -> list[str]:
        return list(
            {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
        )

    addresses = await asyncio.to_thread(resolve)
    if not addresses or any(
        ipaddress.ip_address(address).is_private
        or ipaddress.ip_address(address).is_loopback
        or ipaddress.ip_address(address).is_link_local
        or ipaddress.ip_address(address).is_reserved
        for address in addresses
    ):
        raise ValueError("n8n MCP URL must resolve only to public addresses")
    return value.rstrip("/")


@router.post("/zendesk")
async def zendesk_mcp(
    payload: dict[str, Any],
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> dict[str, Any]:
    request_id = payload.get("id")
    method = payload.get("method")
    if method == "initialize":
        return _rpc_result(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "openhuman-zendesk", "version": "1.0.0"},
            },
        )
    if method == "notifications/initialized":
        return _rpc_result(request_id, {})
    if method == "tools/list":
        return _rpc_result(request_id, {"tools": _ZENDESK_TOOLS})
    if method != "tools/call":
        return _rpc_error(request_id, -32601, "Method not found")

    credential = _require_package(x_api_key, "zendesk")
    try:
        base_url = _validate_zendesk_url(str(credential["account_url"]))
        email = str(credential["email"])
        api_token = str(credential["api_token"])
        params = payload.get("params") or {}
        tool = params.get("name")
        arguments = params.get("arguments") or {}
        async with httpx.AsyncClient(
            base_url=base_url,
            auth=httpx.BasicAuth(f"{email}/token", api_token),
            timeout=30,
        ) as client:
            if tool == "get_ticket":
                response = await client.get(f"/api/v2/tickets/{int(arguments['ticket_id'])}.json")
            elif tool == "search_tickets":
                response = await client.get(
                    "/api/v2/search.json",
                    params={"query": f"type:ticket {arguments['query']}"},
                )
            elif tool == "get_user":
                response = await client.get(f"/api/v2/users/{int(arguments['user_id'])}.json")
            elif tool == "search_help_center":
                response = await client.get(
                    "/api/v2/help_center/articles/search.json",
                    params={"query": arguments["query"]},
                )
            elif tool == "reply_to_ticket":
                response = await client.put(
                    f"/api/v2/tickets/{int(arguments['ticket_id'])}.json",
                    json={
                        "ticket": {
                            "comment": {
                                "body": arguments["body"],
                                "public": bool(arguments.get("public", True)),
                            }
                        }
                    },
                )
            elif tool == "update_ticket_status":
                response = await client.put(
                    f"/api/v2/tickets/{int(arguments['ticket_id'])}.json",
                    json={"ticket": {"status": arguments["status"]}},
                )
            else:
                return _rpc_error(request_id, -32602, "Unknown Zendesk tool")
            response.raise_for_status()
            return _rpc_result(request_id, _tool_content(response.json()))
    except (KeyError, TypeError, ValueError) as exc:
        return _rpc_error(request_id, -32602, str(exc))
    except httpx.HTTPStatusError as exc:
        return _rpc_error(
            request_id,
            -32000,
            f"Zendesk API returned HTTP {exc.response.status_code}",
        )
    except httpx.HTTPError:
        return _rpc_error(request_id, -32000, "Zendesk API unavailable")


@router.post("/n8n")
async def n8n_mcp_relay(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> Response:
    credential = _require_package(x_api_key, "n8n")
    try:
        upstream_url = await _validate_public_https_url(str(credential["server_url"]))
        token = str(credential["token"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": request.headers.get("content-type", "application/json"),
        "Accept": request.headers.get("accept", "application/json, text/event-stream"),
        "mcp-protocol-version": request.headers.get("mcp-protocol-version", "2024-11-05"),
    }
    if session_id := request.headers.get("mcp-session-id"):
        headers["mcp-session-id"] = session_id
    body = await request.body()
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=60) as client:
            upstream = await client.post(upstream_url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="n8n MCP unavailable",
        ) from exc

    response_headers = {}
    if upstream_session := upstream.headers.get("mcp-session-id"):
        response_headers["mcp-session-id"] = upstream_session
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
        headers=response_headers,
    )
