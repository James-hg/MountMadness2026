"""Stateless goals-focused chatbot endpoint (`POST /goals/chat`)."""

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
from app.ai.goals_prompt import GOALS_SYSTEM_PROMPT
from app.ai.goals_tools import (
    GOALS_WRITE_TOOL_NAMES,
    GoalsToolArgumentError,
    dispatch_goals_tool,
    goals_tool_schemas,
)
from app.auth import get_current_user_id
from app.config import settings
from app.database import get_db_connection

router = APIRouter(prefix="/goals", tags=["goals-chat"])

MAX_TOOL_ROUNDS = 4
CONFIRM_TOKENS = {"yes", "y", "confirm", "confirmed", "apply", "proceed", "go ahead", "do it"}
DECLINE_TOKENS = {"no", "n", "cancel", "decline", "stop", "skip", "not now", "dont apply", "do not apply"}


class GoalsPendingAction(BaseModel):
    tool: str
    args: dict[str, Any]


class GoalsChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    pending_action: GoalsPendingAction | None = None


class GoalsChatActionItem(BaseModel):
    tool: str
    kind: str
    summary: str


class GoalsChatResponse(BaseModel):
    reply: str
    conversation_id: str
    actions: list[GoalsChatActionItem] = Field(default_factory=list)
    needs_confirmation: bool = False
    pending_action: GoalsPendingAction | None = None


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


def _normalized_user_reply(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _is_confirmation_message(text: str) -> bool:
    normalized = _normalized_user_reply(text)
    if normalized in CONFIRM_TOKENS:
        return True
    return normalized.startswith("yes ") or normalized.startswith("confirm ") or normalized.startswith("apply ")


def _is_decline_message(text: str) -> bool:
    normalized = _normalized_user_reply(text)
    if normalized in DECLINE_TOKENS:
        return True
    return normalized.startswith("no ") or normalized.startswith("cancel ") or normalized.startswith("dont ")


def _tool_call_fingerprint(tool_name: str, args: dict[str, Any]) -> str:
    canonical_args = json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{tool_name}:{canonical_args}".encode("utf-8")).hexdigest()


def _get_gemini_client() -> GeminiClient:
    return GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
    )


@router.post("/chat", response_model=GoalsChatResponse)
async def goals_chat(
    payload: GoalsChatRequest,
    user_id: UUID = Depends(get_current_user_id),
    connection: Any = Depends(get_db_connection),
) -> GoalsChatResponse:
    """
    Stateless goals assistant.

    - No server-side chat memory for this endpoint.
    - All writes require explicit confirmation.
    """
    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(status_code=422, detail="message must not be empty")

    # Confirmation phase: execute explicitly returned pending action.
    if payload.pending_action is not None:
        if _is_decline_message(message_text):
            return GoalsChatResponse(
                reply="Okay, I did not apply any changes to your goal.",
                conversation_id="stateless",
                actions=[],
                needs_confirmation=False,
                pending_action=None,
            )

        if not _is_confirmation_message(message_text):
            return GoalsChatResponse(
                reply="Please confirm the pending goal update with 'yes' or cancel with 'no'.",
                conversation_id="stateless",
                actions=[],
                needs_confirmation=True,
                pending_action=payload.pending_action,
            )

        try:
            apply_args = dict(payload.pending_action.args)
            apply_args["dry_run"] = False
            tool_result = await dispatch_goals_tool(
                connection,
                user_id,
                payload.pending_action.tool,
                apply_args,
            )
        except (GoalsToolArgumentError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        action = GoalsChatActionItem(
            tool=payload.pending_action.tool,
            kind=tool_result["kind"],
            summary=tool_result["summary"],
        )
        return GoalsChatResponse(
            reply=f"Confirmed. {tool_result['summary']}",
            conversation_id="stateless",
            actions=[action],
            needs_confirmation=False,
            pending_action=None,
        )

    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=503,
            detail="Goals assistant is unavailable because GEMINI_API_KEY is not configured.",
        )

    client = _get_gemini_client()
    schemas = goals_tool_schemas()
    conversation_messages = [{"role": "user", "content": message_text}]
    actions: list[dict[str, Any]] = []
    pending_action: GoalsPendingAction | None = None
    needs_confirmation = False
    seen_write_calls: set[str] = set()
    final_reply = ""

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            result = await client.generate_with_tools(
                system_prompt=GOALS_SYSTEM_PROMPT,
                conversation_messages=conversation_messages,
                tool_schemas=schemas,
            )

            if result.tool_calls:
                for call in result.tool_calls:
                    try:
                        if call.name in GOALS_WRITE_TOOL_NAMES:
                            fingerprint = _tool_call_fingerprint(call.name, call.arguments)
                            if fingerprint in seen_write_calls:
                                continue
                            seen_write_calls.add(fingerprint)

                            preview_args = dict(call.arguments)
                            preview_args["dry_run"] = True
                            tool_result = await dispatch_goals_tool(
                                connection,
                                user_id,
                                call.name,
                                preview_args,
                            )
                            actions.append(
                                {
                                    "tool": call.name,
                                    "kind": "preview",
                                    "summary": tool_result["summary"],
                                }
                            )
                            pending_action = GoalsPendingAction(
                                tool=call.name,
                                args={k: v for k, v in call.arguments.items() if k != "dry_run"},
                            )
                            needs_confirmation = True
                            kind = "preview"
                        else:
                            tool_result = await dispatch_goals_tool(
                                connection,
                                user_id,
                                call.name,
                                call.arguments,
                            )
                            actions.append(
                                {
                                    "tool": call.name,
                                    "kind": tool_result["kind"],
                                    "summary": tool_result["summary"],
                                }
                            )
                            kind = tool_result["kind"]
                    except (GoalsToolArgumentError, ValueError) as exc:
                        final_reply = f"I need a bit more detail before I can do that: {str(exc)}"
                        break

                    tool_payload = {
                        "tool": call.name,
                        "kind": kind,
                        "summary": tool_result["summary"],
                        "data": _to_jsonable(tool_result["data"]),
                    }
                    conversation_messages.append(
                        {
                            "role": "tool",
                            "content": json.dumps(tool_payload, separators=(",", ":")),
                        }
                    )

                if final_reply:
                    break
                continue

            if result.text_response:
                final_reply = result.text_response
                break

        if not final_reply:
            if needs_confirmation and pending_action is not None:
                final_reply = "I prepared a preview. Apply these goal changes now? (yes/no)"
            elif actions:
                final_reply = "Done."
            else:
                final_reply = "I could not complete that request. Please rephrase and try again."

        if needs_confirmation and "yes/no" not in final_reply.lower():
            final_reply = f"{final_reply.rstrip()}\n\nApply these goal changes now? (yes/no)"

    except GeminiRequestError as exc:
        if exc.status_code == 429:
            raise HTTPException(status_code=503, detail="Goals assistant is rate-limited right now. Try again shortly.") from exc
        raise HTTPException(status_code=502, detail="Goals assistant request failed. Please try again.") from exc
    except GeminiError as exc:
        raise HTTPException(status_code=502, detail="Goals assistant response could not be processed.") from exc

    return GoalsChatResponse(
        reply=final_reply,
        conversation_id="stateless",
        actions=[GoalsChatActionItem(**action) for action in actions],
        needs_confirmation=needs_confirmation,
        pending_action=pending_action,
    )
