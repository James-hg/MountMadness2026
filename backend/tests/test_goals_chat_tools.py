from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.ai import goals_tools


def _run(coro):
    return asyncio.run(coro)


def test_dispatch_goals_list(monkeypatch) -> None:
    user_id = uuid4()

    async def fake_list(connection, user_id_arg, status="active"):
        assert user_id_arg == user_id
        assert status == "active"
        return {"items": [{"name": "Trip"}], "count": 1}

    monkeypatch.setattr(goals_tools, "goals_list_tool", fake_list)

    out = _run(
        goals_tools.dispatch_goals_tool(
            connection=object(),
            user_id=user_id,
            tool_name="goals_list",
            args={"status": "active"},
        )
    )

    assert out["kind"] == "read"
    assert out["data"]["count"] == 1


def test_dispatch_goal_create_preview(monkeypatch) -> None:
    user_id = uuid4()

    async def fake_create(connection, user_id_arg, **kwargs):
        assert kwargs["dry_run"] is True
        return {
            "dry_run": True,
            "goal": {"name": kwargs["name"]},
        }

    monkeypatch.setattr(goals_tools, "goal_create_tool", fake_create)

    out = _run(
        goals_tools.dispatch_goals_tool(
            connection=object(),
            user_id=user_id,
            tool_name="goal_create",
            args={
                "name": "Trip",
                "target_amount": "1000.00",
                "saved_amount": "100.00",
                "deadline_date": "2026-12-01",
                "dry_run": True,
            },
        )
    )

    assert out["kind"] == "write"
    assert "Previewed goal" in out["summary"]


def test_dispatch_goal_update_target(monkeypatch) -> None:
    user_id = uuid4()

    async def fake_update(connection, user_id_arg, **kwargs):
        assert kwargs["patch"]["target_amount"] == Decimal("1500.00")
        return {"dry_run": False, "goal": {"name": "Trip"}}

    monkeypatch.setattr(goals_tools, "goal_update_tool", fake_update)

    out = _run(
        goals_tools.dispatch_goals_tool(
            connection=object(),
            user_id=user_id,
            tool_name="goal_update_target",
            args={
                "goal_name": "Trip",
                "target_amount": "1500.00",
                "dry_run": False,
            },
        )
    )

    assert out["kind"] == "write"
    assert "Updated target" in out["summary"]


def test_dispatch_goal_plan(monkeypatch) -> None:
    user_id = uuid4()

    async def fake_goal_plan(connection, user_id_arg, **kwargs):
        return {
            "goal": {"name": "Tuition", "recommended_monthly_save_amount": Decimal("200.00")},
            "snapshot": {"month": "2026-03"},
            "suggestion": {},
        }

    monkeypatch.setattr(goals_tools, "goal_plan_tool", fake_goal_plan)

    out = _run(
        goals_tools.dispatch_goals_tool(
            connection=object(),
            user_id=user_id,
            tool_name="goal_plan",
            args={"goal_name": "Tuition", "month_start": date(2026, 3, 1).isoformat()},
        )
    )

    assert out["kind"] == "read"
    assert "Built plan for 'Tuition'" in out["summary"]

