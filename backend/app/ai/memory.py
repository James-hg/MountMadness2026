"""Persistent conversation memory for `/ai/chat`.

This module stores lightweight conversation state in Postgres:
- one conversation row per thread
- short rolling message history
- deterministic summary compression for older messages
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from psycopg import AsyncConnection
else:
    AsyncConnection = Any

_ALLOWED_ROLES = {"user", "assistant", "tool"}


def _clip_text(value: str, max_len: int = 180) -> str:
    normalized = " ".join(value.strip().split())
    if len(normalized) <= max_len:
        return normalized
    return f"{normalized[: max_len - 1]}…"


def _tool_line_from_meta(content: str, meta: dict[str, Any]) -> str:
    tool_name = str(meta.get("tool_name") or "tool")
    summary = str(meta.get("summary") or "")
    if summary:
        return f"{tool_name}: {_clip_text(summary, max_len=140)}"

    # Fallback if meta is missing; keeps summary deterministic.
    return f"{tool_name}: {_clip_text(content, max_len=140)}"


def _summarize_messages(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []

    for row in rows:
        role = str(row["role"])
        content = str(row["content"])
        meta = row.get("meta") or {}

        if role == "tool":
            line = _tool_line_from_meta(content, meta)
            lines.append(f"- tool {line}")
            continue

        label = "user" if role == "user" else "assistant"
        lines.append(f"- {label}: {_clip_text(content)}")

    # Keep summary compact for token efficiency.
    if len(lines) > 14:
        lines = lines[-14:]

    return "\n".join(lines)


async def get_or_create_conversation(
    connection: AsyncConnection,
    user_id: UUID,
    conversation_id: str | UUID | None,
) -> UUID:
    """Resolve an existing conversation owned by user, or create a new one."""
    parsed_id: UUID | None = None

    if conversation_id:
        try:
            parsed_id = UUID(str(conversation_id))
        except (TypeError, ValueError):
            parsed_id = None

    if parsed_id is not None:
        async with connection.cursor() as cursor:
            await cursor.execute(
                """
                SELECT id
                FROM ai_conversations
                WHERE id = %s
                  AND user_id = %s
                """,
                (parsed_id, user_id),
            )
            row = await cursor.fetchone()

        if row is not None:
            return row["id"]

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            INSERT INTO ai_conversations (user_id)
            VALUES (%s)
            RETURNING id
            """,
            (user_id,),
        )
        row = await cursor.fetchone()

    return row["id"]


async def append_message(
    connection: AsyncConnection,
    conversation_id: UUID,
    user_id: UUID,
    role: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> None:
    """Append one user/assistant/tool message and touch parent conversation."""
    if role not in _ALLOWED_ROLES:
        raise ValueError(f"Unsupported message role: {role}")

    payload = content.strip()
    if not payload:
        raise ValueError("Message content cannot be empty")

    meta_obj = meta or {}

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            INSERT INTO ai_messages (conversation_id, user_id, role, content, meta)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (conversation_id, user_id, role, payload, json.dumps(meta_obj)),
        )

        # Trigger updates `updated_at`; this no-op update keeps recency accurate.
        await cursor.execute(
            """
            UPDATE ai_conversations
            SET updated_at = NOW()
            WHERE id = %s
              AND user_id = %s
            """,
            (conversation_id, user_id),
        )


async def load_recent_messages(
    connection: AsyncConnection,
    conversation_id: UUID,
    user_id: UUID,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Load recent messages in chronological order."""
    if limit < 1:
        return []

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, role, content, meta, created_at
            FROM ai_messages
            WHERE conversation_id = %s
              AND user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (conversation_id, user_id, limit),
        )
        rows = await cursor.fetchall()

    ordered = list(reversed(rows))
    return [
        {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "meta": row.get("meta") or {},
            "created_at": row.get("created_at"),
        }
        for row in ordered
    ]


async def summarize_if_needed(
    connection: AsyncConnection,
    conversation_id: UUID,
    user_id: UUID,
    hard_limit: int = 20,
) -> None:
    """Compress older messages into conversation summary when thread grows too long."""
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT summary
            FROM ai_conversations
            WHERE id = %s
              AND user_id = %s
            """,
            (conversation_id, user_id),
        )
        conv_row = await cursor.fetchone()

    if conv_row is None:
        return

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, role, content, meta, created_at
            FROM ai_messages
            WHERE conversation_id = %s
              AND user_id = %s
            ORDER BY created_at ASC
            """,
            (conversation_id, user_id),
        )
        rows = await cursor.fetchall()

    if len(rows) <= hard_limit:
        return

    older_rows = rows[:-6]
    keep_rows = rows[-6:]

    chunk = _summarize_messages(older_rows)
    if not chunk:
        return

    old_summary = str(conv_row.get("summary") or "").strip()
    if old_summary:
        new_summary = f"{old_summary}\n{chunk}"
    else:
        new_summary = chunk

    # Keep summary bounded for predictable prompt size.
    if len(new_summary) > 4000:
        new_summary = new_summary[-4000:]

    keep_ids = [row["id"] for row in keep_rows]

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            UPDATE ai_conversations
            SET summary = %s,
                updated_at = NOW()
            WHERE id = %s
              AND user_id = %s
            """,
            (new_summary, conversation_id, user_id),
        )
        await cursor.execute(
            """
            DELETE FROM ai_messages
            WHERE conversation_id = %s
              AND user_id = %s
              AND id <> ALL(%s)
            """,
            (conversation_id, user_id, keep_ids),
        )


async def build_context(
    connection: AsyncConnection,
    conversation_id: UUID,
    user_id: UUID,
) -> dict[str, Any]:
    """Return compact context (summary + last 6 messages) for model calls."""
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT summary
            FROM ai_conversations
            WHERE id = %s
              AND user_id = %s
            """,
            (conversation_id, user_id),
        )
        row = await cursor.fetchone()

    summary = ""
    if row is not None:
        summary = str(row.get("summary") or "").strip()

    messages = await load_recent_messages(
        connection,
        conversation_id,
        user_id,
        limit=6,
    )

    return {
        "summary": summary,
        "messages": messages,
    }
