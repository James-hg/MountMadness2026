from __future__ import annotations

import os
import sys
import types
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

# pydantic v1 local compatibility for modules using v2 serializer decorator.
import pydantic

if not hasattr(pydantic, "field_serializer"):
    def _field_serializer(*args, **kwargs):
        def _decorator(fn):
            return fn
        return _decorator

    pydantic.field_serializer = _field_serializer

# Keep tests importable in lightweight local envs without full deps.
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

if "psycopg.errors" not in sys.modules:
    errors_stub = types.ModuleType("psycopg.errors")

    class _UniqueViolation(Exception):
        pass

    errors_stub.UniqueViolation = _UniqueViolation
    sys.modules["psycopg.errors"] = errors_stub

if "psycopg.rows" not in sys.modules:
    rows_stub = types.ModuleType("psycopg.rows")
    rows_stub.dict_row = object()
    sys.modules["psycopg.rows"] = rows_stub

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

import app.goals as goals_router


def _sample_goal(user_id):
    return {
        "id": uuid4(),
        "user_id": user_id,
        "name": "Trip",
        "target_amount": Decimal("1000.00"),
        "saved_amount": Decimal("250.00"),
        "deadline_date": date(2026, 8, 1),
        "status": "active",
        "created_at": datetime(2026, 1, 1, 10, 0, 0),
        "updated_at": datetime(2026, 1, 1, 10, 0, 0),
        "remaining_amount": Decimal("750.00"),
        "months_left": 5,
        "recommended_monthly_save_amount": Decimal("150.00"),
        "progress_pct": 25,
        "on_track": True,
        "shortfall_amount": Decimal("0.00"),
    }


def _money_string(value):
    return f"{float(value):.2f}"


def _app_with_overrides():
    app = FastAPI()
    app.include_router(goals_router.router)
    return app


def test_goals_auth_required() -> None:
    app = _app_with_overrides()

    async def override_db():
        yield object()

    app.dependency_overrides[goals_router.get_db_connection] = override_db
    with TestClient(app) as client:
        response = client.get("/goals")
    assert response.status_code == 401


def test_create_goal_endpoint_success(monkeypatch) -> None:
    app = _app_with_overrides()
    user_id = uuid4()

    async def override_db():
        yield object()

    app.dependency_overrides[goals_router.get_db_connection] = override_db
    app.dependency_overrides[goals_router.get_current_user_id] = lambda: user_id

    async def fake_create(connection, uid, data):
        assert uid == user_id
        return _sample_goal(uid)

    monkeypatch.setattr(goals_router, "create_goal", fake_create)

    with TestClient(app) as client:
        response = client.post(
            "/goals",
            json={
                "name": "Trip",
                "target_amount": "1000.00",
                "saved_amount": "250.00",
                "deadline_date": "2026-08-01",
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Trip"
    assert _money_string(payload["target_amount"]) == "1000.00"
    assert _money_string(payload["recommended_monthly_save_amount"]) == "150.00"


def test_get_goal_returns_404_for_user_scoped_miss(monkeypatch) -> None:
    app = _app_with_overrides()
    user_id = uuid4()
    goal_id = uuid4()

    async def override_db():
        yield object()

    app.dependency_overrides[goals_router.get_db_connection] = override_db
    app.dependency_overrides[goals_router.get_current_user_id] = lambda: user_id

    async def fake_get(connection, uid, gid):
        assert gid == goal_id
        raise LookupError("Goal not found")

    monkeypatch.setattr(goals_router, "get_goal", fake_get)

    with TestClient(app) as client:
        response = client.get(f"/goals/{goal_id}")

    assert response.status_code == 404


def test_patch_goal_validation_error(monkeypatch) -> None:
    app = _app_with_overrides()
    user_id = uuid4()
    goal_id = uuid4()

    async def override_db():
        yield object()

    app.dependency_overrides[goals_router.get_db_connection] = override_db
    app.dependency_overrides[goals_router.get_current_user_id] = lambda: user_id

    async def fake_update(connection, uid, gid, patch):
        raise ValueError("Cannot set status to completed before reaching target_amount")

    monkeypatch.setattr(goals_router, "update_goal", fake_update)

    with TestClient(app) as client:
        response = client.patch(
            f"/goals/{goal_id}",
            json={"status": "completed"},
        )

    assert response.status_code == 422
    assert "completed" in response.json()["detail"]
