from __future__ import annotations

import sys
import types
import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Keep route tests importable in lightweight local envs without PyJWT installed.
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
from app.ai.tools import ToolArgumentError
import app.ai.router as ai_router


class StubGeminiClient:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    async def generate_with_tools(self, system_prompt, conversation_messages, tool_schemas):
        result = self.results[self.calls]
        self.calls += 1
        return result


@pytest.fixture
def client_with_overrides(monkeypatch):
    async def override_db_connection():
        yield object()

    user_id = uuid4()
    monkeypatch.setattr(ai_router.settings, "gemini_api_key", "test-key")
    test_app = FastAPI()
    test_app.include_router(ai_router.router)
    test_app.dependency_overrides[ai_router.get_current_user_id] = lambda: user_id
    test_app.dependency_overrides[ai_router.get_db_connection] = override_db_connection

    with TestClient(test_app) as client:
        yield client, user_id

    test_app.dependency_overrides.clear()


def _install_memory_stubs(monkeypatch, conversation_id: str = "00000000-0000-0000-0000-000000000001"):
    async def fake_get_or_create(connection, user_id, conversation_id_in):
        return conversation_id

    async def fake_append(connection, conversation_id_in, user_id, role, content, meta=None):
        return None

    async def fake_build_context(connection, conversation_id_in, user_id):
        return {"summary": "", "messages": [{"role": "user", "content": "hello"}]}

    async def fake_summarize(connection, conversation_id_in, user_id, hard_limit=20):
        return None

    monkeypatch.setattr(ai_router, "get_or_create_conversation", fake_get_or_create)
    monkeypatch.setattr(ai_router, "append_message", fake_append)
    monkeypatch.setattr(ai_router, "build_context", fake_build_context)
    monkeypatch.setattr(ai_router, "summarize_if_needed", fake_summarize)


def test_ai_chat_direct_text_path(client_with_overrides, monkeypatch) -> None:
    client, _user_id = client_with_overrides
    _install_memory_stubs(monkeypatch)

    monkeypatch.setattr(
        ai_router,
        "_get_gemini_client",
        lambda: StubGeminiClient([GeminiResult(text_response="Here is your summary.", tool_calls=[])]),
    )

    response = client.post("/ai/chat", json={"message": "hello"})

    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "Here is your summary."
    assert data["actions"] == []
    assert data["conversation_id"]


def test_ai_chat_tool_call_path(client_with_overrides, monkeypatch) -> None:
    client, _user_id = client_with_overrides
    _install_memory_stubs(monkeypatch)

    client_stub = StubGeminiClient(
        [
            GeminiResult(
                text_response="",
                tool_calls=[GeminiToolCall(name="get_summary", arguments={"start_date": "2026-02-01", "end_date": "2026-02-10", "group_by": "none"})],
            ),
            GeminiResult(text_response="You spent 120.00 in that range.", tool_calls=[]),
        ]
    )

    async def fake_dispatch(connection, user_id, tool_name, args):
        assert tool_name == "get_summary"
        return {
            "kind": "read",
            "summary": "Range summary 2026-02-01 to 2026-02-10.",
            "data": {"income_total": "0.00", "expense_total": "120.00"},
        }

    monkeypatch.setattr(ai_router, "_get_gemini_client", lambda: client_stub)
    monkeypatch.setattr(ai_router, "dispatch_tool", fake_dispatch)

    response = client.post("/ai/chat", json={"message": "Summarize my spending"})

    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "You spent 120.00 in that range."
    assert len(data["actions"]) == 1
    assert data["actions"][0]["tool"] == "get_summary"


def test_ai_chat_invalid_tool_args_returns_clarification(client_with_overrides, monkeypatch) -> None:
    client, _user_id = client_with_overrides
    _install_memory_stubs(monkeypatch)

    client_stub = StubGeminiClient(
        [
            GeminiResult(
                text_response="",
                tool_calls=[GeminiToolCall(name="create_transaction", arguments={})],
            )
        ]
    )

    async def fake_dispatch(connection, user_id, tool_name, args):
        raise ToolArgumentError("amount is required")

    monkeypatch.setattr(ai_router, "_get_gemini_client", lambda: client_stub)
    monkeypatch.setattr(ai_router, "dispatch_tool", fake_dispatch)

    response = client.post("/ai/chat", json={"message": "add transaction"})

    assert response.status_code == 200
    data = response.json()
    assert "I need a bit more detail" in data["reply"]


<<<<<<< HEAD
def test_ai_chat_dedupes_duplicate_write_tool_calls(client_with_overrides, monkeypatch) -> None:
    client, _user_id = client_with_overrides
    _install_memory_stubs(monkeypatch)

    duplicate_args = {
        "occurred_on": "2026-03-01",
        "type": "expense",
        "amount": 12.5,
        "category_name": "Food",
        "merchant": "Cafe",
    }

    client_stub = StubGeminiClient(
        [
            GeminiResult(
                text_response="",
                tool_calls=[GeminiToolCall(name="create_transaction", arguments=duplicate_args)],
            ),
            GeminiResult(
                text_response="",
                tool_calls=[GeminiToolCall(name="create_transaction", arguments=duplicate_args)],
            ),
            GeminiResult(text_response="Done. Added your expense.", tool_calls=[]),
        ]
    )

    calls = {"count": 0}

    async def fake_dispatch(connection, user_id, tool_name, args):
        calls["count"] += 1
        return {
            "kind": "write",
            "summary": "Created expense transaction 12.50 for Food on 2026-03-01.",
            "data": {
                "created": True,
                "dry_run": False,
                "transaction": {
                    "id": "00000000-0000-0000-0000-000000000001",
                    "type": "expense",
                    "amount": "12.50",
                    "occurred_on": "2026-03-01",
                    "category_name": "Food",
                },
            },
        }

    monkeypatch.setattr(ai_router, "_get_gemini_client", lambda: client_stub)
    monkeypatch.setattr(ai_router, "dispatch_tool", fake_dispatch)

    response = client.post("/ai/chat", json={"message": "Add $12.50 coffee yesterday"})

    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "Done. Added your expense."
    assert calls["count"] == 1
    assert len(data["actions"]) == 1
    assert data["actions"][0]["tool"] == "create_transaction"


=======
>>>>>>> master
def test_ai_chat_requires_auth(monkeypatch) -> None:
    monkeypatch.setattr(ai_router.settings, "gemini_api_key", "test-key")
    test_app = FastAPI()
    test_app.include_router(ai_router.router)

    async def override_db_connection():
        yield object()

    test_app.dependency_overrides[ai_router.get_db_connection] = override_db_connection

    with TestClient(test_app) as client:
        response = client.post("/ai/chat", json={"message": "hello"})

    assert response.status_code == 401


def test_ai_chat_returns_503_when_gemini_key_missing(client_with_overrides, monkeypatch) -> None:
    client, _user_id = client_with_overrides
    _install_memory_stubs(monkeypatch)

    monkeypatch.setattr(ai_router.settings, "gemini_api_key", "")

    response = client.post("/ai/chat", json={"message": "hello"})

    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]
