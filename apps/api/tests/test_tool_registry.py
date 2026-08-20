"""Tests for app.agent.tools.registry — ToolRegistry + ToolRegistration."""

from langchain_core.tools import tool

from app.agent.tools.registry import ToolRegistration, ToolRegistry, registry


def _make_dummy_tool(name: str = "dummy"):
    @tool
    def dummy() -> str:
        """A dummy tool."""
        return "ok"
    dummy.name = name
    return dummy


# ---------------------------------------------------------------------------
# ToolRegistration
# ---------------------------------------------------------------------------

class TestToolRegistration:
    def test_is_available_no_check_fn(self):
        reg = ToolRegistration(tool=_make_dummy_tool())
        assert reg.is_available() is True

    def test_is_available_passing_check(self):
        reg = ToolRegistration(
            tool=_make_dummy_tool(),
            check_fn=lambda: True,
        )
        assert reg.is_available() is True

    def test_is_available_failing_check(self):
        reg = ToolRegistration(
            tool=_make_dummy_tool(),
            check_fn=lambda: False,
        )
        assert reg.is_available() is False

    def test_is_available_caches_result(self):
        calls = 0
        def check():
            nonlocal calls
            calls += 1
            return True
        reg = ToolRegistration(tool=_make_dummy_tool(), check_fn=check)
        reg.is_available()
        reg.is_available(ttl=999)  # still cached
        assert calls == 1

    def test_invalidate_cache(self):
        reg = ToolRegistration(
            tool=_make_dummy_tool(),
            check_fn=lambda: False,
        )
        assert reg.is_available() is False
        reg.check_fn = lambda: True
        reg.invalidate_cache()
        assert reg.is_available() is True

    def test_name_property(self):
        reg = ToolRegistration(tool=_make_dummy_tool(name="my_tool"))
        assert reg.name == "my_tool"


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------

class TestToolRegistry:
    def test_register_and_get(self):
        tr = ToolRegistry()
        t = _make_dummy_tool("test_reg_get")
        tr.register(t)
        assert tr.get("test_reg_get") is not None
        assert tr.get("nonexistent") is None

    def test_register_duplicate_raises(self):
        tr = ToolRegistry()
        t = _make_dummy_tool("dup")
        tr.register(t)
        import pytest
        with pytest.raises(ValueError, match="already registered"):
            tr.register(_make_dummy_tool("dup"))

    def test_register_safe_silent_dup(self):
        tr = ToolRegistry()
        t = _make_dummy_tool("safe_dup")
        tr.register_safe(t)
        tr.register_safe(_make_dummy_tool("safe_dup"))  # no error

    def test_deregister(self):
        tr = ToolRegistry()
        t = _make_dummy_tool("to_remove")
        tr.register(t)
        tr.deregister("to_remove")
        assert tr.get("to_remove") is None

    def test_get_tool(self):
        tr = ToolRegistry()
        t = _make_dummy_tool("get_tool_test")
        tr.register(t)
        assert tr.get_tool("get_tool_test") is t

    def test_get_all_tool_names(self):
        tr = ToolRegistry()
        tr.register(_make_dummy_tool("a"), toolset="x")
        tr.register(_make_dummy_tool("b"), toolset="y")
        names = tr.get_all_tool_names()
        assert "a" in names
        assert "b" in names

    def test_get_tools_for_toolset(self):
        tr = ToolRegistry()
        tr.register(_make_dummy_tool("t1"), toolset="alpha")
        tr.register(_make_dummy_tool("t2"), toolset="beta")
        tr.register(_make_dummy_tool("t3"), toolset="alpha")
        alpha_tools = tr.get_tools_for_toolset("alpha")
        assert len(alpha_tools) == 2
        assert {r.name for r in alpha_tools} == {"t1", "t3"}

    def test_get_tool_names_for_toolset(self):
        tr = ToolRegistry()
        tr.register(_make_dummy_tool("x"), toolset="foo")
        tr.register(_make_dummy_tool("y"), toolset="bar")
        assert tr.get_tool_names_for_toolset("foo") == ["x"]

    def test_get_toolset_for_tool(self):
        tr = ToolRegistry()
        tr.register(_make_dummy_tool("tk"), toolset="ts")
        assert tr.get_toolset_for_tool("tk") == "ts"
        assert tr.get_toolset_for_tool("nope") is None

    def test_get_tool_to_toolset_map(self):
        tr = ToolRegistry()
        tr.register(_make_dummy_tool("a"), toolset="x")
        tr.register(_make_dummy_tool("b"), toolset="y")
        assert tr.get_tool_to_toolset_map() == {"a": "x", "b": "y"}

    def test_get_toolsets(self):
        tr = ToolRegistry()
        tr.register(_make_dummy_tool("a"), toolset="core")
        tr.register(_make_dummy_tool("b"), toolset="vision")
        tr.register(_make_dummy_tool("c"), toolset="core")
        ts = tr.get_toolsets()
        assert set(ts.keys()) == {"core", "vision"}
        assert "a" in ts["core"]
        assert "c" in ts["core"]

    def test_get_available_tools(self):
        tr = ToolRegistry()
        tr.register(_make_dummy_tool("ok"), check_fn=lambda: True)
        tr.register(_make_dummy_tool("ko"), check_fn=lambda: False)
        available = tr.get_available_tools()
        assert len(available) == 1
        assert available[0].name == "ok"

    def test_has_toolset_true(self):
        tr = ToolRegistry()
        tr.register(_make_dummy_tool("a"), toolset="core")
        assert tr.has_toolset("core") is True

    def test_has_toolset_false(self):
        tr = ToolRegistry()
        tr.register(_make_dummy_tool("a"), toolset="core", check_fn=lambda: False)
        assert tr.has_toolset("core") is False

    def test_invalidate_cache_all(self):
        tr = ToolRegistry()
        tr.register(_make_dummy_tool("a"), check_fn=lambda: False)
        tr.register(_make_dummy_tool("b"), check_fn=lambda: False)
        tr.invalidate_cache()
        for reg in tr._tools.values():
            assert reg._check_cache is None

    def test_invalidate_cache_single(self):
        tr = ToolRegistry()
        tr.register(_make_dummy_tool("a"), check_fn=lambda: False)
        tr.register(_make_dummy_tool("b"), check_fn=lambda: True)
        tr.get("a").is_available()
        tr.get("b").is_available()
        tr.invalidate_cache("a")
        a_reg = tr.get("a")
        b_reg = tr.get("b")
        assert a_reg._check_cache is None
        assert b_reg._check_cache is not None

    def test_check_fn_exception_treated_as_unavailable(self):
        tr = ToolRegistry()
        tr.register(_make_dummy_tool("crash"), check_fn=lambda: 1 / 0)
        assert tr.get_available_tools() == []


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

class TestSingletonRegistry:
    def test_registry_has_expected_toolsets(self):
        """The module-level ``registry`` singleton should contain toolsets
        registered by ``register_built_in_tools()``."""
        toolsets = registry.get_toolsets()
        assert "core" in toolsets
        assert "delegation" in toolsets
        assert "cronjob" in toolsets
        assert "vision" in toolsets

    def test_registry_contains_new_tools(self):
        names = set(registry.get_all_tool_names())
        assert "delegate_task" in names
        assert "cronjob" in names
        assert "vision_analyze" in names
