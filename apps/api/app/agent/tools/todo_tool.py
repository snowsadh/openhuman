"""Todo task management tool for AI employees.

In-memory task list per session for decomposing complex tasks,
tracking progress, and maintaining focus across conversations.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

VALID_STATUSES = {"pending", "in_progress", "completed", "cancelled"}
MAX_CONTENT_CHARS = 4000
MAX_ITEMS = 256


class TodoStore:
    """In-memory todo list. One instance per session.

    Items are ordered — list position is priority. Each item has:
      - id: unique string identifier
      - content: task description
      - status: pending | in_progress | completed | cancelled
    """

    def __init__(self) -> None:
        self._items: list[dict[str, str]] = []

    def write(self, todos: list[dict[str, Any]], merge: bool = False) -> list[dict[str, str]]:
        if not merge:
            self._items = [self._validate(t) for t in self._dedupe(todos)]
        else:
            existing = {item["id"]: item for item in self._items}
            for t in self._dedupe(todos):
                item_id = str(t.get("id", "")).strip()
                if not item_id:
                    continue
                if item_id in existing:
                    if "content" in t and t["content"]:
                        existing[item_id]["content"] = str(t["content"]).strip()[:MAX_CONTENT_CHARS]
                    if "status" in t and t["status"]:
                        s = str(t["status"]).strip().lower()
                        if s in VALID_STATUSES:
                            existing[item_id]["status"] = s
                else:
                    v = self._validate(t)
                    existing[v["id"]] = v
                    self._items.append(v)
            seen: set[str] = set()
            rebuilt: list[dict[str, str]] = []
            for item in self._items:
                cur = existing.get(item["id"], item)
                if cur["id"] not in seen:
                    rebuilt.append(cur)
                    seen.add(cur["id"])
            self._items = rebuilt
        if len(self._items) > MAX_ITEMS:
            self._items = self._items[:MAX_ITEMS]
        return self.read()

    def read(self) -> list[dict[str, str]]:
        return [item.copy() for item in self._items]

    def has_items(self) -> bool:
        return bool(self._items)

    def format_for_injection(self) -> str | None:
        active = [i for i in self._items if i["status"] in {"pending", "in_progress"}]
        if not active:
            return None
        markers = {"completed": "[x]", "in_progress": "[>]", "pending": "[ ]", "cancelled": "[~]"}
        lines = ["[Your active task list was preserved across context compression]"]
        for item in active:
            m = markers.get(item["status"], "[?]")
            lines.append(f"- {m} {item['id']}. {item['content']} ({item['status']})")
        return "\n".join(lines)

    @staticmethod
    def _validate(item: dict[str, Any]) -> dict[str, str]:
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            import uuid
            item_id = uuid.uuid4().hex[:8]
        content = str(item.get("content", "")).strip()[:MAX_CONTENT_CHARS]
        status = str(item.get("status", "pending")).strip().lower()
        if status not in VALID_STATUSES:
            status = "pending"
        return {"id": item_id, "content": content, "status": status}

    @staticmethod
    def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item in items:
            iid = str(item.get("id", "")).strip()
            if iid and iid in seen:
                continue
            if iid:
                seen.add(iid)
            result.append(item)
        return result


# Module-level store keyed by a simple session id
_stores: dict[str, TodoStore] = {}


def _get_store(session_id: str = "default") -> TodoStore:
    if session_id not in _stores:
        _stores[session_id] = TodoStore()
    return _stores[session_id]


@tool
def todo(
    action: str = "read",
    todos: str | None = None,
    merge: bool = False,
    session_id: str = "default",
) -> str:
    """Manage a task list for planning and tracking work.

    Args:
        action: 'read' to view tasks, 'write' to set tasks, 'merge' to update existing.
        todos: JSON string of task list — each item has id, content, status.
        merge: If true, merge todos with existing list (update by id, append new).
        session_id: Session identifier for isolated task lists.
    """
    store = _get_store(session_id)

    if action == "read":
        items = store.read()
        if not items:
            return "Task list is empty."
        markers = {"completed": "[x]", "in_progress": "[>]", "pending": "[ ]", "cancelled": "[~]"}
        lines = ["Current task list:"]
        for item in items:
            m = markers.get(item["status"], "[?]")
            lines.append(f"  {m} {item['id']}. {item['content']} ({item['status']})")
        return "\n".join(lines)

    if action in ("write", "merge"):
        if not todos:
            return "No todos provided. Pass 'todos' as a JSON string."
        try:
            parsed = json.loads(todos)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"
        if not isinstance(parsed, list):
            return "todos must be a JSON array of objects."
        effective_merge = merge or (action == "merge")
        updated = store.write(parsed, merge=effective_merge)
        return f"Task list updated. {len(updated)} item(s) currently tracked."

    return f"Unknown action: {action}. Use 'read', 'write', or 'merge'."
