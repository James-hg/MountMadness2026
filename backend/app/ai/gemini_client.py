"""Minimal Gemini API wrapper with tool-calling support and retry handling."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx


class GeminiError(Exception):
    """Base exception for Gemini client errors."""


class GeminiRequestError(GeminiError):
    """Raised when Gemini API request fails."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class GeminiResponseError(GeminiError):
    """Raised when Gemini response shape cannot be parsed."""


@dataclass
class GeminiToolCall:
    """One function/tool call emitted by the model."""

    name: str
    arguments: dict[str, Any]


@dataclass
class GeminiResult:
    """Parsed model response payload."""

    text_response: str
    tool_calls: list[GeminiToolCall]


class GeminiClient:
    """Thin client for Gemini `generateContent` with function-calling payloads."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int = 25,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    async def generate_with_tools(
        self,
        system_prompt: str,
        conversation_messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]],
    ) -> GeminiResult:
        """Call Gemini with compact conversation context and tool schemas."""
        body = {
            "system_instruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": self._build_contents(conversation_messages),
            "generationConfig": {
                "temperature": 0.2,
            },
        }

        if tool_schemas:
            body["tools"] = [{"functionDeclarations": tool_schemas}]

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        params = {"key": self.api_key}

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(url, params=params, json=body)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise GeminiRequestError(503, "Gemini request failed") from exc

            if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                await asyncio.sleep(0.5 * (2**attempt))
                continue

            if response.status_code >= 400:
                raise GeminiRequestError(response.status_code, response.text)

            try:
                payload = response.json()
            except ValueError as exc:
                raise GeminiResponseError("Invalid JSON from Gemini") from exc

            return self._parse_response(payload)

        # Defensive fallback if loop exits unexpectedly.
        raise GeminiRequestError(503, f"Gemini request failed: {last_error or 'unknown error'}")

    def _build_contents(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []

        for message in messages:
            role = str(message.get("role") or "user")
            content = str(message.get("content") or "").strip()
            if not content:
                continue

            if role == "assistant":
                gemini_role = "model"
                text = content
            elif role == "tool":
                gemini_role = "user"
                text = f"Tool result: {content}"
            else:
                gemini_role = "user"
                text = content

            contents.append({
                "role": gemini_role,
                "parts": [{"text": text}],
            })

        if not contents:
            contents.append(
                {
                    "role": "user",
                    "parts": [{"text": "Hello."}],
                }
            )

        return contents

    def _parse_response(self, payload: dict[str, Any]) -> GeminiResult:
        candidates = payload.get("candidates") or []
        if not candidates:
            raise GeminiResponseError("Gemini response missing candidates")

        candidate = candidates[0] or {}
        parts = ((candidate.get("content") or {}).get("parts")) or []

        text_parts: list[str] = []
        tool_calls: list[GeminiToolCall] = []

        for part in parts:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())

            raw_function_call = part.get("functionCall") or part.get("function_call")
            if not raw_function_call:
                continue

            name = str(raw_function_call.get("name") or "").strip()
            args_raw = raw_function_call.get("args", {})

            if isinstance(args_raw, str):
                try:
                    parsed_args = json.loads(args_raw)
                except ValueError:
                    parsed_args = {}
            elif isinstance(args_raw, dict):
                parsed_args = args_raw
            else:
                parsed_args = {}

            if name:
                tool_calls.append(
                    GeminiToolCall(
                        name=name,
                        arguments=parsed_args,
                    )
                )

        return GeminiResult(
            text_response="\n".join(text_parts).strip(),
            tool_calls=tool_calls,
        )
