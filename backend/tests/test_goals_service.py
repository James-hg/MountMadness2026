from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.services import goals_service


def _run(coro):
    return asyncio.run(coro)


class FakeGoalsCursor:
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

        if normalized.startswith("INSERT INTO goals"):
            user_id, name, target_amount, saved_amount, deadline_date, status = params
            goal_id = uuid4()
            now = self.connection._next_timestamp()
            row = {
                "id": goal_id,
                "user_id": user_id,
                "name": name,
                "target_amount": Decimal(str(target_amount)),
                "saved_amount": Decimal(str(saved_amount)),
                "deadline_date": deadline_date,
                "status": status,
                "created_at": now,
                "updated_at": now,
            }
            self.connection.goals[goal_id] = row
            self._rows = [row]
            return

        if "SELECT id, user_id, name, target_amount, saved_amount, deadline_date, status, created_at, updated_at FROM goals WHERE id = %s AND user_id = %s" in normalized:
            goal_id, user_id = params
            row = self.connection.goals.get(goal_id)
            if row and row["user_id"] == user_id:
                self._rows = [row]
            return

        if "SELECT id, user_id, name, target_amount, saved_amount, deadline_date, status, created_at, updated_at FROM goals WHERE user_id = %s" in normalized:
            user_id = params[0]
            status = params[1] if len(params) > 1 else None
            rows = [
                row
                for row in self.connection.goals.values()
                if row["user_id"] == user_id and (status is None or row["status"] == status)
            ]
            rows.sort(key=lambda row: (row["deadline_date"], row["created_at"]), reverse=False)
            self._rows = rows
            return

        if normalized.startswith("UPDATE goals SET name = %s"):
            name, target_amount, saved_amount, deadline_date, status, goal_id, user_id = params
            row = self.connection.goals.get(goal_id)
            if row is None or row["user_id"] != user_id:
                return
            row.update(
                {
                    "name": name,
                    "target_amount": Decimal(str(target_amount)),
                    "saved_amount": Decimal(str(saved_amount)),
                    "deadline_date": deadline_date,
                    "status": status,
                    "updated_at": self.connection._next_timestamp(),
                }
            )
            self._rows = [row]
            return

        if normalized.startswith("DELETE FROM goals"):
            goal_id, user_id = params
            row = self.connection.goals.get(goal_id)
            if row and row["user_id"] == user_id:
                del self.connection.goals[goal_id]
                self._rows = [{"id": goal_id}]
            return

        raise AssertionError(f"Unhandled query: {normalized}")

    async def fetchone(self):
        if not self._rows:
            return None
        return self._rows[0]

    async def fetchall(self):
        return list(self._rows)


class FakeGoalsConnection:
    def __init__(self):
        self.goals: dict[UUID, dict] = {}
        self._tick = 0

    def _next_timestamp(self):
        self._tick += 1
        return datetime(2026, 1, 1, 12, 0, self._tick)

    def cursor(self):
        return FakeGoalsCursor(self)


def test_create_goal_success(monkeypatch) -> None:
    connection = FakeGoalsConnection()
    user_id = uuid4()

    monkeypatch.setattr(goals_service, "_today", lambda: date(2026, 3, 1))

    row = _run(
        goals_service.create_goal(
            connection,
            user_id,
            {
                "name": "Japan Trip",
                "target_amount": Decimal("1200.00"),
                "saved_amount": Decimal("200.00"),
                "deadline_date": date(2026, 7, 1),
            },
        )
    )

    assert row["name"] == "Japan Trip"
    assert row["status"] == "active"
    assert row["remaining_amount"] == Decimal("1000.00")


def test_computed_fields_months_left_and_recommended(monkeypatch) -> None:
    monkeypatch.setattr(goals_service, "_today", lambda: date(2026, 3, 1))
    goal = {
        "id": uuid4(),
        "user_id": uuid4(),
        "name": "Emergency Fund",
        "target_amount": Decimal("1000.00"),
        "saved_amount": Decimal("250.00"),
        "deadline_date": date(2026, 4, 15),  # 45 days => ceil(45/30)=2
        "status": "active",
        "created_at": datetime(2026, 2, 1, 10, 0, 0),
        "updated_at": datetime(2026, 2, 1, 10, 0, 0),
    }

    out = goals_service._compute_goal_metrics(goal, date(2026, 3, 1))

    assert out["months_left"] == 2
    assert out["recommended_monthly_save_amount"] == Decimal("375.00")
    assert out["progress_pct"] == 25


def test_on_track_true_false(monkeypatch) -> None:
    monkeypatch.setattr(goals_service, "_today", lambda: date(2026, 3, 1))
    base = {
        "id": uuid4(),
        "user_id": uuid4(),
        "name": "Laptop",
        "target_amount": Decimal("600.00"),
        "deadline_date": date(2026, 5, 1),
        "status": "active",
        "created_at": datetime(2026, 1, 1, 10, 0, 0),
        "updated_at": datetime(2026, 1, 1, 10, 0, 0),
    }

    on_track_row = goals_service._compute_goal_metrics(
        {**base, "saved_amount": Decimal("350.00")},
        date(2026, 3, 1),
    )
    behind_row = goals_service._compute_goal_metrics(
        {**base, "saved_amount": Decimal("100.00")},
        date(2026, 3, 1),
    )

    assert on_track_row["on_track"] is True
    assert on_track_row["shortfall_amount"] == Decimal("0.00")
    assert behind_row["on_track"] is False
    assert behind_row["shortfall_amount"] > Decimal("0.00")


def test_update_saved_to_target_sets_completed(monkeypatch) -> None:
    connection = FakeGoalsConnection()
    user_id = uuid4()
    monkeypatch.setattr(goals_service, "_today", lambda: date(2026, 3, 1))

    created = _run(
        goals_service.create_goal(
            connection,
            user_id,
            {
                "name": "Tuition",
                "target_amount": Decimal("1000.00"),
                "saved_amount": Decimal("100.00"),
                "deadline_date": date(2026, 8, 1),
            },
        )
    )

    updated = _run(
        goals_service.update_goal(
            connection,
            user_id,
            created["id"],
            {"saved_amount": Decimal("1000.00")},
        )
    )

    assert updated["status"] == "completed"
    assert updated["remaining_amount"] == Decimal("0.00")


def test_validation_rejects_completed_without_target(monkeypatch) -> None:
    monkeypatch.setattr(goals_service, "_today", lambda: date(2026, 3, 1))
    with pytest.raises(ValueError):
        goals_service._validate_goal_state(
            {
                "name": "Trip",
                "target_amount": Decimal("1000.00"),
                "saved_amount": Decimal("100.00"),
                "deadline_date": date(2026, 10, 1),
                "status": "completed",
            },
            date(2026, 3, 1),
        )
