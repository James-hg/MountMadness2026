"""FastAPI router for authenticated AI chat with safe tool execution."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.ai.gemini_client import GeminiClient, GeminiError, GeminiRequestError
from app.ai.memory import (
    append_message,
    build_context,
    get_or_create_conversation,
    summarize_if_needed,
)
from app.ai.prompt import build_system_prompt
from app.ai.tools import ToolArgumentError, dispatch_tool, tool_schemas
from app.auth import get_current_user_id
from app.config import settings
from app.database import get_db_connection

router = APIRouter(prefix="/ai", tags=["ai"])

MAX_TOOL_ROUNDS = 4
WRITE_TOOL_NAMES = {"create_transaction", "apply_budget_plan"}


class AIChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


class AIActionItem(BaseModel):
    tool: str
    kind: str
    summary: str


class AIChatResponse(BaseModel):
    reply: str
    conversation_id: str
    actions: list[AIActionItem] = Field(default_factory=list)
    needs_confirmation: bool = False


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


def _get_gemini_client() -> GeminiClient:
    return GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )


def _tool_call_fingerprint(tool_name: str, args: dict[str, Any]) -> str:
    """
    Build a stable fingerprint for one tool call.

    Used to prevent duplicate write execution when model emits the same tool call
    multiple times in a single `/ai/chat` request.
    """
    canonical_args = json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(f"{tool_name}:{canonical_args}".encode("utf-8")).hexdigest()
    return digest


@router.post("/chat", response_model=AIChatResponse)
async def ai_chat(
    payload: AIChatRequest,
    user_id: UUID = Depends(get_current_user_id),
    connection: Any = Depends(get_db_connection),
) -> AIChatResponse:
    """
    Chat endpoint that uses Gemini + validated tools.

    Example request:
    {
      "message": "Summarize my spending from 2026-02-01 to 2026-02-20",
      "conversation_id": null
    }

    Example response:
    {
      "reply": "Your expenses were ...",
      "conversation_id": "...",
      "actions": [
        {"tool": "get_summary", "kind": "read", "summary": "Range summary ..."}
      ],
      "needs_confirmation": false
    }
    """
    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(status_code=422, detail="message must not be empty")

    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI assistant is unavailable because GEMINI_API_KEY is not configured.",
        )

    conversation_id = await get_or_create_conversation(
        connection,
        user_id,
        payload.conversation_id,
    )

    await append_message(
        connection,
        conversation_id,
        user_id,
        "user",
        message_text,
        meta={},
    )

    context = await build_context(connection, conversation_id, user_id)
    system_prompt = build_system_prompt(context["summary"])

    conversation_messages = [
        {
            "role": item["role"],
            "content": item["content"],
        }
        for item in context["messages"]
    ]

    client = _get_gemini_client()
    schemas = tool_schemas()
    actions: list[dict[str, Any]] = []
    executed_write_calls: dict[str, dict[str, Any]] = {}

    final_reply = ""
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            result = await client.generate_with_tools(
                system_prompt=system_prompt,
                conversation_messages=conversation_messages,
                tool_schemas=schemas,
            )

            if result.tool_calls:
                for call in result.tool_calls:
                    call_fingerprint = _tool_call_fingerprint(call.name, call.arguments)
                    duplicate_write_call = False

                    # Idempotency guard: never run identical writes twice in one turn.
                    if call.name in WRITE_TOOL_NAMES and call_fingerprint in executed_write_calls:
                        duplicate_write_call = True
                        previous = executed_write_calls[call_fingerprint]
                        tool_result = {
                            "kind": previous["kind"],
                            "summary": f"Skipped duplicate {call.name} call in this request; write already applied once.",
                            "data": previous["data"],
                        }
                    else:
                        try:
                            tool_result = await dispatch_tool(
                                connection,
                                user_id,
                                call.name,
                                call.arguments,
                            )
                        except (ToolArgumentError, ValueError) as exc:
                            final_reply = (
                                "I need a bit more detail before I can do that: "
                                f"{str(exc)}"
                            )
                            break

                        if call.name in WRITE_TOOL_NAMES and tool_result["kind"] == "write":
                            executed_write_calls[call_fingerprint] = tool_result

                    action = {
                        "tool": call.name,
                        "kind": tool_result["kind"],
                        "summary": tool_result["summary"],
                    }
                    # Keep action list clean: only show one entry for deduped write calls.
                    if not duplicate_write_call:
                        actions.append(action)

                    tool_payload = {
                        "tool": call.name,
                        "kind": tool_result["kind"],
                        "summary": tool_result["summary"],
                        "data": _to_jsonable(tool_result["data"]),
                    }

                    tool_content = json.dumps(tool_payload, separators=(",", ":"))
                    await append_message(
                        connection,
                        conversation_id,
                        user_id,
                        "tool",
                        tool_content,
                        meta={
                            "tool_name": call.name,
                            "summary": tool_result["summary"],
                            "kind": tool_result["kind"],
                        },
                    )
                    conversation_messages.append({
                        "role": "tool",
                        "content": tool_content,
                    })

                if final_reply:
                    break

                # Ask model to produce user-facing response after tool results are appended.
                continue

            if result.text_response:
                final_reply = result.text_response
                break

        if not final_reply:
            if actions:
                final_reply = "Done. I applied the requested action(s)."
            else:
                final_reply = "I could not complete that request. Please rephrase and try again."

    except GeminiRequestError as exc:
        if exc.status_code == 429:
            raise HTTPException(status_code=503, detail="AI assistant is rate-limited right now. Try again shortly.") from exc
        raise HTTPException(status_code=502, detail="AI assistant request failed. Please try again.") from exc
    except GeminiError as exc:
        raise HTTPException(status_code=502, detail="AI assistant response could not be processed.") from exc

    await append_message(
        connection,
        conversation_id,
        user_id,
        "assistant",
        final_reply,
        meta={"actions": actions},
    )
    await summarize_if_needed(connection, conversation_id, user_id)

    return AIChatResponse(
        reply=final_reply,
        conversation_id=str(conversation_id),
        actions=[AIActionItem(**action) for action in actions],
        needs_confirmation=False,
    )
