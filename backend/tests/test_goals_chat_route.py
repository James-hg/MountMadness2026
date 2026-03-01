from __future__ import annotations

import os
import sys
import types
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Lightweight import compatibility for local test env.
if "jwt" not in sys.modules:
    jwt_stub = types.ModuleType("jwt")

    class _InvalidTokenError(Exception):
        pass

    jwt_stub.InvalidTokenError = _InvalidTokenError
    jwt_stub.decode = lambda *args, **kwargs: {}
    jwt_stub.encode = lambda *args, **kwargs: "token"
    sys.modules["jwt"] = jwt_stub

if "psycopg" not in sys.modules:
    psycopg_stub = types.ModuleType("psycopg")
    psycopg_stub.AsyncConnection = object
    sys.modules["psycopg"] = psycopg_stub

if "psycopg.rows" not in sys.modules:
    rows_stub = types.ModuleType("psycopg.rows")
    rows_stub.dict_row = object()
    sys.modules["psycopg.rows"] = rows_stub

if "psycopg.errors" not in sys.modules:
    errors_stub = types.ModuleType("psycopg.errors")

    class _UniqueViolation(Exception):
        pass

    errors_stub.UniqueViolation = _UniqueViolation
    sys.modules["psycopg.errors"] = errors_stub

if "psycopg_pool" not in sys.modules:
    pool_stub = types.ModuleType("psycopg_pool")

    class _AsyncConnectionPool:
        def __init__(self, *args, **kwargs):
            pass

        async def open(self):
            return None

        async def close(self):
            return None

    pool_stub.AsyncConnectionPool = _AsyncConnectionPool
    sys.modules["psycopg_pool"] = pool_stub

if "pydantic_settings" not in sys.modules:
    from pydantic import BaseSettings as _PydanticBaseSettings

    settings_stub = types.ModuleType("pydantic_settings")
    settings_stub.BaseSettings = _PydanticBaseSettings
    settings_stub.SettingsConfigDict = dict
    sys.modules["pydantic_settings"] = settings_stub

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("JWT_ALGORITHM", "HS256")

from app.ai.gemini_client import GeminiResult, GeminiToolCall
import app.goals_chat as goals_chat_router


class StubGeminiClient:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    async def generate_with_tools(self, system_prompt, conversation_messages, tool_schemas):
        result = self.results[self.calls]
        self.calls += 1
        return result


def _app_with_overrides():
    app = FastAPI()
    app.include_router(goals_chat_router.router)
    return app


def test_goals_chat_requires_auth() -> None:
    app = _app_with_overrides()

    async def override_db():
        yield object()

    app.dependency_overrides[goals_chat_router.get_db_connection] = override_db
    with TestClient(app) as client:
        response = client.post("/goals/chat", json={"message": "hello"})
    assert response.status_code == 401


def test_goals_chat_returns_503_when_key_missing(monkeypatch) -> None:
    app = _app_with_overrides()
    user_id = uuid4()

    async def override_db():
        yield object()

    app.dependency_overrides[goals_chat_router.get_db_connection] = override_db
    app.dependency_overrides[goals_chat_router.get_current_user_id] = lambda: user_id
    monkeypatch.setattr(goals_chat_router.settings, "gemini_api_key", "")

    with TestClient(app) as client:
        response = client.post("/goals/chat", json={"message": "hello"})

    assert response.status_code == 503


def test_goals_chat_write_preview_needs_confirmation(monkeypatch) -> None:
    app = _app_with_overrides()
    user_id = uuid4()

    async def override_db():
        yield object()

    app.dependency_overrides[goals_chat_router.get_db_connection] = override_db
    app.dependency_overrides[goals_chat_router.get_current_user_id] = lambda: user_id
    monkeypatch.setattr(goals_chat_router.settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(
        goals_chat_router,
        "_get_gemini_client",
        lambda: StubGeminiClient(
            [
                GeminiResult(
                    text_response="",
                    tool_calls=[GeminiToolCall(name="goal_add_saved", arguments={"goal_name": "Trip", "add_amount": "100.00"})],
                ),
                GeminiResult(text_response="I prepared an update preview.", tool_calls=[]),
            ]
        ),
    )

    async def fake_dispatch(connection, user_id_arg, tool_name, args):
        assert tool_name == "goal_add_saved"
        assert args["dry_run"] is True
        return {
            "kind": "write",
            "summary": "Previewed saved amount for 'Trip'.",
            "data": {"dry_run": True},
        }

    monkeypatch.setattr(goals_chat_router, "dispatch_goals_tool", fake_dispatch)

    with TestClient(app) as client:
        response = client.post("/goals/chat", json={"message": "Add $100 to my trip goal"})

    assert response.status_code == 200
    data = response.json()
    assert data["needs_confirmation"] is True
    assert data["pending_action"]["tool"] == "goal_add_saved"
    assert data["conversation_id"] == "stateless"


def test_goals_chat_confirm_applies_pending_action(monkeypatch) -> None:
    app = _app_with_overrides()
    user_id = uuid4()

    async def override_db():
        yield object()

    app.dependency_overrides[goals_chat_router.get_db_connection] = override_db
    app.dependency_overrides[goals_chat_router.get_current_user_id] = lambda: user_id
    monkeypatch.setattr(goals_chat_router.settings, "gemini_api_key", "test-key")

    calls = {"count": 0}

    async def fake_dispatch(connection, user_id_arg, tool_name, args):
        calls["count"] += 1
        assert args["dry_run"] is False
        return {"kind": "write", "summary": "Updated saved amount for 'Trip'.", "data": {"ok": True}}

    monkeypatch.setattr(goals_chat_router, "dispatch_goals_tool", fake_dispatch)

    with TestClient(app) as client:
        response = client.post(
            "/goals/chat",
            json={
                "message": "yes",
                "pending_action": {"tool": "goal_add_saved", "args": {"goal_name": "Trip", "add_amount": "100.00"}},
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert calls["count"] == 1
    assert data["needs_confirmation"] is False
    assert data["pending_action"] is None


def test_goals_chat_decline_pending_action() -> None:
    app = _app_with_overrides()
    user_id = uuid4()

    async def override_db():
        yield object()

    app.dependency_overrides[goals_chat_router.get_db_connection] = override_db
    app.dependency_overrides[goals_chat_router.get_current_user_id] = lambda: user_id

    with TestClient(app) as client:
        response = client.post(
            "/goals/chat",
            json={
                "message": "no",
                "pending_action": {"tool": "goal_delete", "args": {"goal_name": "Trip"}},
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "did not apply" in data["reply"].lower()
    assert data["needs_confirmation"] is False

