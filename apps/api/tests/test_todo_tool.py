"""Tests for todo_tool module."""

from __future__ import annotations


class TestTodoStore:
    def test_write_and_read(self):
        from app.agent.tools.todo_tool import TodoStore

        store = TodoStore()
        store.write([{"id": "1", "content": "Task one", "status": "pending"}])
        items = store.read()
        assert len(items) == 1
        assert items[0]["content"] == "Task one"

    def test_merge_updates_existing(self):
        from app.agent.tools.todo_tool import TodoStore

        store = TodoStore()
        store.write([{"id": "1", "content": "Task one", "status": "pending"}])
        store.write(
            [{"id": "1", "content": "Task one updated", "status": "in_progress"}],
            merge=True,
        )
        items = store.read()
        assert len(items) == 1
        assert items[0]["content"] == "Task one updated"
        assert items[0]["status"] == "in_progress"

    def test_merge_appends_new(self):
        from app.agent.tools.todo_tool import TodoStore

        store = TodoStore()
        store.write([{"id": "1", "content": "Task one", "status": "pending"}])
        store.write([{"id": "2", "content": "Task two", "status": "pending"}], merge=True)
        assert len(store.read()) == 2

    def test_dedupe_by_id(self):
        from app.agent.tools.todo_tool import TodoStore

        store = TodoStore()
        store.write([
            {"id": "1", "content": "A", "status": "pending"},
            {"id": "1", "content": "A dup", "status": "pending"},
        ])
        assert len(store.read()) == 1

    def test_invalid_status_defaults_to_pending(self):
        from app.agent.tools.todo_tool import TodoStore

        store = TodoStore()
        store.write([{"id": "1", "content": "Test", "status": "invalid_status"}])
        assert store.read()[0]["status"] == "pending"

    def test_has_items(self):
        from app.agent.tools.todo_tool import TodoStore

        store = TodoStore()
        assert not store.has_items()
        store.write([{"id": "1", "content": "Test", "status": "pending"}])
        assert store.has_items()

    def test_format_for_injection_excludes_completed(self):
        from app.agent.tools.todo_tool import TodoStore

        store = TodoStore()
        store.write([
            {"id": "1", "content": "Active", "status": "in_progress"},
            {"id": "2", "content": "Done", "status": "completed"},
        ])
        result = store.format_for_injection()
        assert result is not None
        assert "Active" in result
        assert "Done" not in result

    def test_empty_format_returns_none(self):
        from app.agent.tools.todo_tool import TodoStore

        store = TodoStore()
        assert store.format_for_injection() is None


class TestTodoTool:
    def test_read_empty(self):
        from app.agent.tools.todo_tool import todo

        result = todo.invoke({"action": "read", "session_id": "test-empty"})
        assert "empty" in result.lower()

    def test_write_and_read(self):
        from app.agent.tools.todo_tool import todo

        sid = "test-write-read"
        write_result = todo.invoke({
            "action": "write",
            "todos": '[{"id": "1", "content": "Test task", "status": "pending"}]',
            "session_id": sid,
        })
        assert "updated" in write_result.lower()

        read_result = todo.invoke({"action": "read", "session_id": sid})
        assert "Test task" in read_result

    def test_unknown_action(self):
        from app.agent.tools.todo_tool import todo

        result = todo.invoke({"action": "bogus"})
        assert "unknown" in result.lower()
