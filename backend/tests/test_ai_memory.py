import asyncio
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from app.ai.memory import (
    append_message,
    build_context,
    get_or_create_conversation,
    load_recent_messages,
    summarize_if_needed,
)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self._rows = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params=None):
        params = params or ()
        normalized = " ".join(query.split())
        self._rows = []

        if "SELECT id FROM ai_conversations" in normalized:
            conversation_id, user_id = params
            row = self.connection.conversations.get(conversation_id)
            if row and row["user_id"] == user_id:
                self._rows = [{"id": conversation_id}]
            return

        if "INSERT INTO ai_conversations" in normalized and "RETURNING id" in normalized:
            (user_id,) = params
            conversation_id = uuid4()
            now = self.connection._next_timestamp()
            self.connection.conversations[conversation_id] = {
                "id": conversation_id,
                "user_id": user_id,
                "summary": "",
                "created_at": now,
                "updated_at": now,
            }
            self._rows = [{"id": conversation_id}]
            return

        if "INSERT INTO ai_messages" in normalized:
            conversation_id, user_id, role, content, meta_json = params
            message_id = uuid4()
            created_at = self.connection._next_timestamp()
            meta = __import__("json").loads(meta_json)
            self.connection.messages.append(
                {
                    "id": message_id,
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "role": role,
                    "content": content,
                    "meta": meta,
                    "created_at": created_at,
                }
            )
            return

        if "UPDATE ai_conversations SET updated_at = NOW()" in normalized:
            conversation_id, user_id = params
            row = self.connection.conversations.get(conversation_id)
            if row and row["user_id"] == user_id:
                row["updated_at"] = self.connection._next_timestamp()
            return

        if "SELECT id, role, content, meta, created_at FROM ai_messages" in normalized and "ORDER BY created_at DESC" in normalized:
            conversation_id, user_id, limit = params
            rows = [
                row
                for row in self.connection.messages
                if row["conversation_id"] == conversation_id and row["user_id"] == user_id
            ]
            rows.sort(key=lambda item: item["created_at"], reverse=True)
            self._rows = rows[:limit]
            return

        if "SELECT summary FROM ai_conversations" in normalized:
            conversation_id, user_id = params
            row = self.connection.conversations.get(conversation_id)
            if row and row["user_id"] == user_id:
                self._rows = [{"summary": row["summary"]}]
            return

        if "SELECT id, role, content, meta, created_at FROM ai_messages" in normalized and "ORDER BY created_at ASC" in normalized:
            conversation_id, user_id = params
            rows = [
                row
                for row in self.connection.messages
                if row["conversation_id"] == conversation_id and row["user_id"] == user_id
            ]
            rows.sort(key=lambda item: item["created_at"])
            self._rows = rows
            return

        if "UPDATE ai_conversations SET summary = %s" in normalized:
            summary, conversation_id, user_id = params
            row = self.connection.conversations.get(conversation_id)
            if row and row["user_id"] == user_id:
                row["summary"] = summary
                row["updated_at"] = self.connection._next_timestamp()
            return

        if "DELETE FROM ai_messages" in normalized and "id <> ALL(%s)" in normalized:
            conversation_id, user_id, keep_ids = params
            keep = set(keep_ids)
            self.connection.messages = [
                row
                for row in self.connection.messages
                if not (
                    row["conversation_id"] == conversation_id
                    and row["user_id"] == user_id
                    and row["id"] not in keep
                )
            ]
            return

        raise AssertionError(f"Unhandled query: {normalized}")

    async def fetchone(self):
        if not self._rows:
            return None
        return self._rows[0]

    async def fetchall(self):
        return list(self._rows)


class FakeConnection:
    def __init__(self):
        self.conversations = {}
        self.messages = []
        self._tick = 0

    def _next_timestamp(self):
        self._tick += 1
        return datetime(2026, 1, 1) + timedelta(seconds=self._tick)

    def cursor(self):
        return FakeCursor(self)


def _run(coro):
    return asyncio.run(coro)


def test_get_or_create_conversation_reuses_existing() -> None:
    connection = FakeConnection()
    user_id = uuid4()

    conversation_id = _run(get_or_create_conversation(connection, user_id, None))
    same_id = _run(get_or_create_conversation(connection, user_id, str(conversation_id)))

    assert isinstance(conversation_id, UUID)
    assert same_id == conversation_id


def test_append_and_load_recent_messages() -> None:
    connection = FakeConnection()
    user_id = uuid4()
    conversation_id = _run(get_or_create_conversation(connection, user_id, None))

    _run(append_message(connection, conversation_id, user_id, "user", "hello"))
    _run(append_message(connection, conversation_id, user_id, "assistant", "hi there"))
    _run(append_message(connection, conversation_id, user_id, "tool", '{"ok":true}', meta={"tool_name": "get_summary"}))

    messages = _run(load_recent_messages(connection, conversation_id, user_id, limit=2))

    assert [item["role"] for item in messages] == ["assistant", "tool"]
    assert messages[0]["content"] == "hi there"


def test_summarize_if_needed_keeps_last_six_and_updates_summary() -> None:
    connection = FakeConnection()
    user_id = uuid4()
    conversation_id = _run(get_or_create_conversation(connection, user_id, None))

    for index in range(12):
        role = "user" if index % 2 == 0 else "assistant"
        _run(append_message(connection, conversation_id, user_id, role, f"message-{index}"))

    _run(summarize_if_needed(connection, conversation_id, user_id, hard_limit=10))

    context = _run(build_context(connection, conversation_id, user_id))

    assert len(context["messages"]) == 6
    assert context["messages"][0]["content"] == "message-6"
    assert "message-0" in context["summary"]
    assert "assistant" in context["summary"]
