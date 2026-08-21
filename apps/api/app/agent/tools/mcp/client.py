"""Real MCP client manager backed by ``langchain-mcp-adapters``.

Given a list of resolved connections (connector_slug + decrypted credentials),
builds per-server transport configurations, connects via ``MultiServerMCPClient``,
loads tools, and prefixes names as ``mcp__{slug}__{tool}``.

Includes per-connector circuit breaking, rate limiting, timeouts, and
structured logging for observability (Phase 4 hardening).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import socket
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from armoriq_sdk.exceptions import (
    ArmorIQException,
    MCPInvocationException,
    PolicyBlockedException,
    PolicyHoldException,
)
from armoriq_sdk.models import IntentToken, InvokeOptions
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.activity.service import record_activity_from_context
from app.agent.armoriq import get_armoriq_client, parse_mcp_tool_name
from app.agent.tools.mcp.connectors.registry import REGISTRY, ConnectorSpec
from app.agent.tools.mcp.security import validate_connection
from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Protects against flaky MCP servers.

    States
    ------
    - **closed** — normal operation; requests pass through.
    - **open** — failure threshold exceeded; requests are rejected immediately.
    - **half_open** — recovery timeout elapsed; one test request is allowed.

    After ``failure_threshold`` consecutive failures the circuit opens for
    ``recovery_timeout`` seconds.  When the recovery window expires the next
    request is allowed through (half-open).  If it succeeds the circuit closes;
    if it fails the circuit re-opens immediately.
    """

    def __init__(
        self,
        slug: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ) -> None:
        self.slug = slug
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._state: str = "closed"  # closed | open | half_open

    # -- public properties ---------------------------------------------------

    @property
    def is_open(self) -> bool:
        """Return ``True`` if requests should be rejected without attempting."""
        if self._state == "closed":
            return False
        if self._state == "half_open":
            return False
        # OPEN — has the recovery window elapsed?
        if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
            self._state = "half_open"
            logger.info(
                "Circuit breaker for '%s' entering half-open state",
                self.slug,
            )
            return False
        return True

    @property
    def state(self) -> str:
        """Expose current state for diagnostics ("closed" / "open" / "half_open")."""
        # Refresh in case recovery timeout has elapsed while we were open.
        _ = self.is_open  # side-effect: may transition open → half_open
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    # -- state transitions ---------------------------------------------------

    def record_success(self) -> None:
        """Reset failure count and close the circuit."""
        if self._state != "closed":
            logger.info(
                "Circuit breaker for '%s' closed after successful request",
                self.slug,
            )
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        """Increment failure count; open circuit if threshold reached."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == "half_open":
            logger.warning(
                "Circuit breaker for '%s' re-opened after half-open failure",
                self.slug,
            )
            self._state = "open"
        elif self._failure_count >= self.failure_threshold:
            logger.warning(
                "Circuit breaker for '%s' opened after %d consecutive failures",
                self.slug,
                self._failure_count,
            )
            self._state = "open"


# Module-level registry so circuit state survives across requests.
_circuit_breakers: dict[str, CircuitBreaker] = {}


def _get_circuit_breaker(slug: str) -> CircuitBreaker:
    """Return (creating if necessary) the circuit breaker for *slug*."""
    if slug not in _circuit_breakers:
        _circuit_breakers[slug] = CircuitBreaker(slug)
    return _circuit_breakers[slug]


# ---------------------------------------------------------------------------
# Rate Limiter (sliding window)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Simple sliding-window rate limiter keyed per connector slug."""

    def __init__(self, slug: str, max_per_minute: int = 60) -> None:
        self.slug = slug
        self.max_per_minute = max_per_minute
        self._window: list[float] = []  # monotonic timestamps of recent calls

    @property
    def is_allowed(self) -> bool:
        """Return ``True`` if a call is within the current rate limit."""
        if self.max_per_minute <= 0:
            return True  # unlimited
        now = time.monotonic()
        cutoff = now - 60.0
        # Prune expired timestamps.
        self._window = [t for t in self._window if t > cutoff]
        return len(self._window) < self.max_per_minute

    def record_call(self) -> None:
        """Record that a call was made."""
        if self.max_per_minute > 0:
            self._window.append(time.monotonic())

    @property
    def current_count(self) -> int:
        """Number of calls in the current 60 s window (diagnostics)."""
        cutoff = time.monotonic() - 60.0
        self._window = [t for t in self._window if t > cutoff]
        return len(self._window)


# Module-level registry so rate-limit state survives across requests.
_rate_limiters: dict[str, RateLimiter] = {}


def _get_rate_limiter(slug: str, max_per_minute: int = 60) -> RateLimiter:
    """Return (creating if necessary) the rate limiter for *slug*."""
    if slug not in _rate_limiters:
        _rate_limiters[slug] = RateLimiter(slug, max_per_minute)
    return _rate_limiters[slug]


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------


def log_mcp_call(
    server: str,
    tool: str,
    latency_ms: float,
    *,
    success: bool,
    error: str | None = None,
) -> None:
    """Emit a structured log record for a single MCP tool invocation.

    The log record's ``extra`` dict carries ``mcp_server``, ``mcp_tool``,
    ``latency_ms``, ``success``, and optionally ``error`` so that log
    aggregators can index these fields without parsing the message string.
    """
    extra: dict[str, Any] = {
        "mcp_server": server,
        "mcp_tool": tool,
        "latency_ms": round(latency_ms, 2),
        "success": success,
    }
    if error:
        extra["error"] = error

    if success:
        logger.info(
            "MCP tool '%s' on '%s' completed in %.1f ms",
            tool,
            server,
            latency_ms,
            extra=extra,
        )
    else:
        logger.error(
            "MCP tool '%s' on '%s' failed after %.1f ms: %s",
            tool,
            server,
            latency_ms,
            error,
            extra=extra,
        )


# ---------------------------------------------------------------------------
# Connection + Manager
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResolvedConnection:
    """A single MCP connection ready to be dialled.

    Created by the router / service layer after decrypting stored credentials.
    """

    slug: str
    connector: ConnectorSpec
    credentials: str | None  # decrypted API key / PAT / access token
    auth_type: str | None = None  # stored connection auth mode; falls back to connector default
    server_url: str | None = None  # stored per-connection endpoint override for dynamic connectors


class MCPClientManager:
    """Manages per-request tool loading from configured MCP servers.

    **Phase 4 hardening** — every managed tool is wrapped with:

    * **Circuit breaking** — after *N* consecutive failures the server is
      skipped for a recovery window, preventing wasted attempts.
    * **Rate limiting** — sliding-window cap on calls per minute per server.
    * **Per-call timeout** — ``asyncio.wait_for`` so one hung tool cannot
      stall the entire agent turn.
    * **Structured logging** — ``log_mcp_call`` emits ``mcp_server``,
      ``mcp_tool``, ``latency_ms``, ``success``, ``error`` on every invocation.

    Usage::

        mgr = MCPClientManager()
        tools = await mgr.connect([
            ResolvedConnection(slug="github", connector=spec, credentials="ghp_xxx"),
        ])
        # ... run agent turn with tools ...
        await mgr.disconnect()
    """

    def __init__(self) -> None:
        self._client: MultiServerMCPClient | None = None
        self._server_names: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def connect(self, connections: list[ResolvedConnection]) -> list[BaseTool]:
        """Resolve *connections* into MCP tools.

        Each connection is checked against its circuit breaker before
        dialling.  Unreachable servers are logged and **skipped** — the
        agent turn continues with whatever tools loaded successfully.
        """
        if not connections:
            return []

        # Build server configs keyed by slug (no prefix yet).
        server_configs: dict[str, dict[str, Any]] = {}
        skipped_circuits: list[str] = []

        for conn in connections:
            cb = _get_circuit_breaker(conn.slug)

            # -- circuit breaker gate ------------------------------------
            if cb.is_open:
                logger.warning(
                    "Circuit breaker open for '%s' — skipping MCP connection",
                    conn.slug,
                )
                skipped_circuits.append(conn.slug)
                continue

            # -- security validation gate ---------------------------------
            security_issues = validate_connection(conn)
            if security_issues:
                logger.warning(
                    "Security validation failed for MCP connector '%s': %s",
                    conn.slug,
                    "; ".join(security_issues),
                )
                cb.record_failure()
                continue

            try:
                if not self._is_server_reachable(conn):
                    target = (
                        conn.connector.command
                        if conn.connector.transport == "stdio"
                        else conn.connector.base_url
                    )
                    logger.warning(
                        "Skipping MCP connector '%s' because its runtime target is unavailable: %s",
                        conn.slug,
                        target,
                    )
                    cb.record_failure()
                    continue
                server_configs[conn.slug] = self._build_server_config(conn)
            except Exception:
                logger.exception("Failed to build config for MCP connector '%s'", conn.slug)
                cb.record_failure()

        if skipped_circuits:
            logger.info(
                "Skipped %d MCP server(s) due to open circuit breakers: %s",
                len(skipped_circuits),
                ", ".join(skipped_circuits),
            )

        if not server_configs:
            return []

        # Use ``tool_name_prefix=False`` so tools keep their original names.
        # We add the ``mcp__{slug}__`` prefix manually for a clean namespace
        # convention.
        self._client = MultiServerMCPClient(
            connections=server_configs,
            tool_name_prefix=False,
            handle_tool_errors=True,
        )

        # Load tools per-server so we know which slug each tool belongs to.
        tools: list[BaseTool] = []
        for slug in server_configs:
            cb = _get_circuit_breaker(slug)
            spec = REGISTRY.get(slug)
            timeout = spec.request_timeout_seconds if spec else 30.0

            try:
                server_tools = await asyncio.wait_for(
                    self._client.get_tools(server_name=slug),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Timeout loading tools from MCP server '%s' (%.1f s)",
                    slug,
                    timeout,
                )
                cb.record_failure()
                continue
            except Exception:
                logger.exception("Failed to load tools from MCP server '%s'", slug)
                cb.record_failure()
                continue

            for raw in server_tools:
                new_name = f"mcp__{slug}__{raw.name}"
                try:
                    renamed = raw.model_copy(update={"name": new_name})
                except Exception:
                    logger.warning("Could not copy/rename tool '%s' — skipping", raw.name)
                    continue

                # Wrap with structured logging + rate limiting + timeout
                # + circuit-breaker integration.
                wrapped = self._wrap_tool(renamed, slug, spec)
                tools.append(wrapped)

            # Connection succeeded — reset circuit breaker.
            cb.record_success()

        self._server_names = list(server_configs)
        logger.info(
            "MCP client loaded %d tools from %d server(s)",
            len(tools),
            len(server_configs),
        )
        return tools

    async def disconnect(self) -> None:
        """Release any held MCP resources.

        The underlying ``MultiServerMCPClient`` creates per-tool-call
        sessions, so there is no persistent connection to tear down.  This
        exists for API symmetry and future pooling support.
        """
        self._client = None
        self._server_names = []

    # ------------------------------------------------------------------
    # Tool wrapping (Phase 4 — observability + resilience)
    # ------------------------------------------------------------------

    def _wrap_tool(
        self,
        tool: BaseTool,
        slug: str,
        spec: ConnectorSpec | None,
    ) -> BaseTool:
        """Wrap *tool* with ArmorIQ enforcement and resilience guards.

        Every invocation of the returned tool will:

        1. Check the circuit breaker — reject immediately if open.
        2. Check the rate limiter — reject if the per-minute cap is hit.
        3. Require a signed plan token and execute through ArmorIQ ``invoke``.
        4. Log the outcome (``mcp_server``, ``mcp_tool``, ``latency_ms``,
           ``success``, ``error``).
        5. Report success/failure to the circuit breaker.
        """
        cb = _get_circuit_breaker(slug)
        max_rpm = spec.rate_limit_per_minute if spec else 60
        rl = _get_rate_limiter(slug, max_rpm)
        timeout = spec.request_timeout_seconds if spec else 30.0
        parsed_name = parse_mcp_tool_name(tool.name)
        action = parsed_name[1] if parsed_name else tool.name

        async def guarded_ainvoke(input: Any, config: Any = None, **kwargs: Any) -> Any:
            # -- circuit breaker gate (per-invocation) -------------------
            if cb.is_open:
                raise RuntimeError(
                    f"MCP server '{slug}' is temporarily unavailable (circuit breaker open)"
                )

            # -- rate limiter gate ---------------------------------------
            if not rl.is_allowed:
                raise RuntimeError(
                    f"Rate limit exceeded for MCP server '{slug}' ({max_rpm} calls/min)"
                )

            rl.record_call()

            configurable = (config or {}).get("configurable", {})
            token_data = configurable.get("armoriq_intent_token")
            if not token_data:
                exc = PolicyBlockedException(
                    "MCP execution refused because no ArmorIQ intent token is present",
                    enforcement_action="block",
                    reason="missing_intent_token",
                )
                await record_activity_from_context(
                    "armoriq_blocked",
                    f"ArmorIQ blocked {slug}.{action}",
                    status="blocked",
                    metadata={"mcp": slug, "action": action, "reason": exc.reason},
                )
                raise exc

            token = IntentToken.model_validate(token_data)
            holds: list[dict[str, Any]] = []
            event_loop = asyncio.get_running_loop()

            def on_hold(info: Any) -> None:
                holds.append(info.model_dump(mode="json"))
                if len(holds) == 1:
                    asyncio.run_coroutine_threadsafe(
                        record_activity_from_context(
                            "armoriq_held",
                            f"ArmorIQ held {slug}.{action} for approval",
                            status="pending",
                            metadata={
                                "mcp": slug,
                                "action": action,
                                "plan_hash": token.plan_hash,
                            },
                        ),
                        event_loop,
                    )

            options = InvokeOptions(
                wait_for_approval=True,
                delegation_timeout_ms=settings.armoriq_approval_timeout_seconds * 1000,
                user_email=configurable.get("armoriq_user_email"),
                on_hold=on_hold,
            )

            # -- execute through ArmorIQ with timeout + structured logging -
            start = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: get_armoriq_client().invoke_with_policy(
                            slug,
                            action,
                            token,
                            input,
                            options,
                        )
                    ),
                    timeout=max(
                        timeout,
                        settings.armoriq_approval_timeout_seconds
                        + settings.armoriq_request_timeout_seconds,
                    ),
                )
                elapsed_ms = (time.monotonic() - start) * 1000
                log_mcp_call(slug, tool.name, elapsed_ms, success=True)
                cb.record_success()
                await record_activity_from_context(
                    "armoriq_allowed",
                    f"ArmorIQ allowed {slug}.{action}",
                    status="succeeded",
                    metadata={
                        "mcp": slug,
                        "action": action,
                        "plan_hash": token.plan_hash,
                    },
                )
                return result.result
            except (PolicyBlockedException, PolicyHoldException) as exc:
                elapsed_ms = (time.monotonic() - start) * 1000
                event_type = (
                    "armoriq_held"
                    if isinstance(exc, PolicyHoldException)
                    else "armoriq_blocked"
                )
                status = "pending" if isinstance(exc, PolicyHoldException) else "blocked"
                log_mcp_call(slug, tool.name, elapsed_ms, success=False, error=str(exc))
                await record_activity_from_context(
                    event_type,
                    f"ArmorIQ {status} {slug}.{action}",
                    status=status,
                    metadata={
                        "mcp": slug,
                        "action": action,
                        "reason": str(exc)[:300],
                        "plan_hash": token.plan_hash,
                    },
                )
                # Policy failures are not MCP availability failures and must not
                # open the connector circuit breaker.
                raise
            except MCPInvocationException as exc:
                elapsed_ms = (time.monotonic() - start) * 1000
                log_mcp_call(slug, tool.name, elapsed_ms, success=False, error=str(exc))
                cb.record_failure()
                raise
            except ArmorIQException as exc:
                elapsed_ms = (time.monotonic() - start) * 1000
                log_mcp_call(slug, tool.name, elapsed_ms, success=False, error=str(exc))
                await record_activity_from_context(
                    "armoriq_blocked",
                    f"ArmorIQ blocked {slug}.{action}",
                    status="blocked",
                    metadata={
                        "mcp": slug,
                        "action": action,
                        "reason": str(exc)[:300],
                        "plan_hash": token.plan_hash,
                    },
                )
                raise
            except TimeoutError:
                elapsed_ms = (time.monotonic() - start) * 1000
                log_mcp_call(
                    slug,
                    tool.name,
                    elapsed_ms,
                    success=False,
                    error="ArmorIQ approval/invocation timeout",
                )
                await record_activity_from_context(
                    "armoriq_blocked",
                    f"ArmorIQ timed out {slug}.{action}",
                    status="blocked",
                    metadata={"mcp": slug, "action": action},
                )
                raise
            except Exception as exc:
                elapsed_ms = (time.monotonic() - start) * 1000
                log_mcp_call(
                    slug,
                    tool.name,
                    elapsed_ms,
                    success=False,
                    error=str(exc),
                )
                # The proxy reached the MCP and reported a tool failure only via
                # MCPInvocationException. Other failures remain fail-closed but
                # do not poison the connector circuit.
                raise

        # Replace the ainvoke method with our guarded version.
        # Use ``object.__setattr__`` to bypass Pydantic's strict setattr
        # validation on ``StructuredTool`` / ``BaseTool`` instances.
        object.__setattr__(tool, "ainvoke", guarded_ainvoke)
        return tool

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_server_reachable(self, conn: ResolvedConnection) -> bool:
        """Best-effort hostname resolution check before adapter startup.

        This avoids noisy adapter-level exception groups when a community-hosted
        MCP endpoint has disappeared or its DNS entry no longer resolves.
        """
        if conn.connector.transport == "stdio":
            command = conn.connector.command
            if not command:
                return False
            return shutil.which(command) is not None

        if conn.connector.transport not in {"streamable_http", "sse"}:
            return True

        target_url = conn.server_url or conn.connector.base_url
        if not target_url:
            return False

        host = urlparse(target_url).hostname
        if not host:
            return False

        try:
            socket.getaddrinfo(host, None)
        except OSError:
            return False
        return True

    def _build_server_config(self, conn: ResolvedConnection) -> dict[str, Any]:
        """Translate a ``ConnectorSpec`` + credentials into the dict that
        ``MultiServerMCPClient`` expects for one server."""
        spec = conn.connector

        if spec.transport == "stdio":
            if not spec.command:
                raise ValueError(f"Connector '{spec.slug}' is missing a stdio command")

            # NOTE: no "timeout" key here — langchain-mcp-adapters'
            # ``_create_stdio_session`` does not accept a ``timeout`` kwarg
            # (only http/sse sessions do) and passing one raises
            # ``TypeError: _create_stdio_session() got an unexpected keyword
            # argument 'timeout'``. Per-call timeouts are already enforced
            # above via ``asyncio.wait_for``.
            return {
                "transport": "stdio",
                "command": spec.command,
                "args": spec.args,
            }

        # langchain-mcp-adapters 0.3.x expects HTTP-based MCP servers to use
        # the transport key "http", even when our internal connector registry
        # stores the more explicit "streamable_http" label.
        transport = "http" if spec.transport == "streamable_http" else spec.transport

        # ── streamable_http / sse ────────────────────────────────────
        target_url = conn.server_url or spec.base_url
        if not target_url:
            raise ValueError(f"Connector '{spec.slug}' requires a server URL but none was provided")

        config: dict[str, Any] = {
            "url": target_url,
            "transport": transport,
            "timeout": spec.request_timeout_seconds,
        }

        # Headers / auth
        headers: dict[str, str] = {}
        auth_type = conn.auth_type or spec.auth_type
        if auth_type in ("pat_bearer", "oauth2") and conn.credentials:
            headers["Authorization"] = f"Bearer {conn.credentials}"
        elif auth_type == "api_key_header":
            if conn.credentials:
                headers["X-API-Key"] = conn.credentials

        if headers:
            config["headers"] = headers

        return config
