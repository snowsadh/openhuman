from __future__ import annotations

import threading
import time
from collections.abc import Callable

from langchain_core.tools import BaseTool


class ToolRegistration:
    """Metadata for a single registered tool.

    Wraps a LangChain ``BaseTool`` with Hermes-style metadata: toolset
    membership, availability gate, risk level, and emoji.
    """

    __slots__ = (
        "tool", "toolset", "risk_level", "check_fn",
        "_check_cache", "_check_cache_ts",
    )

    def __init__(
        self,
        tool: BaseTool,
        toolset: str = "core",
        risk_level: str = "low",
        check_fn: Callable[[], bool] | None = None,
    ) -> None:
        self.tool = tool
        self.toolset = toolset
        self.risk_level = risk_level
        self.check_fn = check_fn
        self._check_cache: bool | None = None
        self._check_cache_ts: float = 0.0

    @property
    def name(self) -> str:
        return self.tool.name

    def is_available(self, ttl: float = 30.0) -> bool:
        if self.check_fn is None:
            return True
        now = time.monotonic()
        if self._check_cache is not None and (now - self._check_cache_ts) < ttl:
            return self._check_cache
        try:
            self._check_cache = self.check_fn()
        except Exception:
            self._check_cache = False
        self._check_cache_ts = now
        return self._check_cache

    def invalidate_cache(self) -> None:
        self._check_cache = None
        self._check_cache_ts = 0.0


class ToolRegistry:
    """Singleton registry collecting tool metadata.

    * Stores ``ToolRegistration`` entries keyed by tool name.
    * Supports Hermes-style toolset queries and availability gating.
    * Thread-safe for concurrent register / get operations.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolRegistration] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        tool: BaseTool,
        toolset: str = "core",
        risk_level: str = "low",
        check_fn: Callable[[], bool] | None = None,
    ) -> None:
        """Register a LangChain tool with metadata.

        Raises ``ValueError`` if a tool with the same ``tool.name`` is
        already registered (use ``deregister`` first for explicit overrides).
        """
        with self._lock:
            if tool.name in self._tools:
                raise ValueError(
                    f"Tool '{tool.name}' is already registered. "
                    f"Use deregister() first if you intend to override it."
                )
            self._tools[tool.name] = ToolRegistration(
                tool=tool,
                toolset=toolset,
                risk_level=risk_level,
                check_fn=check_fn,
            )

    def register_safe(
        self,
        tool: BaseTool,
        toolset: str = "core",
        risk_level: str = "low",
        check_fn: Callable[[], bool] | None = None,
    ) -> None:
        """Register a tool, silently ignoring duplicates."""
        with self._lock:
            if tool.name not in self._tools:
                self._tools[tool.name] = ToolRegistration(
                    tool=tool,
                    toolset=toolset,
                    risk_level=risk_level,
                    check_fn=check_fn,
                )

    def deregister(self, name: str) -> None:
        """Remove a registered tool by name."""
        with self._lock:
            self._tools.pop(name, None)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get(self, name: str) -> ToolRegistration | None:
        return self._tools.get(name)

    def get_tool(self, name: str) -> BaseTool | None:
        reg = self._tools.get(name)
        return reg.tool if reg else None

    def get_all_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_tools_for_toolset(self, toolset: str) -> list[ToolRegistration]:
        return [r for r in self._tools.values() if r.toolset == toolset]

    def get_tool_names_for_toolset(self, toolset: str) -> list[str]:
        return [r.name for r in self._tools.values() if r.toolset == toolset]

    def get_toolset_for_tool(self, name: str) -> str | None:
        reg = self._tools.get(name)
        return reg.toolset if reg else None

    def get_tool_to_toolset_map(self) -> dict[str, str]:
        return {name: reg.toolset for name, reg in self._tools.items()}

    def get_toolsets(self) -> dict[str, list[str]]:
        """Return ``{toolset_name: [tool_name, ...]}``."""
        result: dict[str, list[str]] = {}
        for name, reg in self._tools.items():
            result.setdefault(reg.toolset, []).append(name)
        return result

    # ------------------------------------------------------------------
    # Availability-aware getters
    # ------------------------------------------------------------------

    def get_available_tools(self, check_ttl: float = 30.0) -> list[BaseTool]:
        """Return all **BaseTool** instances whose ``check_fn`` passes."""
        result: list[BaseTool] = []
        for reg in self._tools.values():
            if reg.is_available(ttl=check_ttl):
                result.append(reg.tool)
        return result

    def get_available_registrations(
        self, check_ttl: float = 30.0,
    ) -> list[ToolRegistration]:
        """Return registrations whose ``check_fn`` passes."""
        return [
            r for r in self._tools.values()
            if r.is_available(ttl=check_ttl)
        ]

    def has_toolset(self, toolset: str, check_ttl: float = 30.0) -> bool:
        """Return True if *toolset* has at least one available tool."""
        return any(
            reg.is_available(ttl=check_ttl)
            for reg in self._tools.values()
            if reg.toolset == toolset
        )

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def invalidate_cache(self, name: str | None = None) -> None:
        if name:
            reg = self._tools.get(name)
            if reg:
                reg.invalidate_cache()
        else:
            for reg in self._tools.values():
                reg.invalidate_cache()


# Module-level singleton — mirrors Hermes ``tools.registry.registry``.
registry = ToolRegistry()
