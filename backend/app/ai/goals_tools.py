"""Goals-only tool schemas and dispatcher for `/goals/chat`."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, root_validator, validator

from app.services.goals_ai_service import (
    goal_add_saved_tool,
    goal_create_tool,
    goal_delete_tool,
    goal_plan_tool,
    goal_update_tool,
    goals_list_tool,
    get_goal_by_id_or_name,
)


class GoalsToolArgumentError(Exception):
    """Raised when goals tool args are invalid."""


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _validate_month_start(value: date) -> date:
    if value.day != 1:
        raise ValueError("month_start must be YYYY-MM-01")
    return value


class GoalSelectorArgs(BaseModel):
    goal_id: UUID | None = None
    goal_name: str | None = Field(default=None, max_length=120)

    @root_validator(skip_on_failure=True)
    def ensure_selector(cls, values):
        if values.get("goal_id") is None and not values.get("goal_name"):
            raise ValueError("Provide goal_id or goal_name")
        return values


class GoalsListArgs(BaseModel):
    status: Literal["active", "paused", "completed", "cancelled", "all"] = "active"


class GoalPlanArgs(GoalSelectorArgs):
    month_start: date | None = None

    @validator("month_start")
    def validate_month_start(cls, value: date | None) -> date | None:
        if value is None:
            return None
        return _validate_month_start(value)


class GoalCreateArgs(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    deadline_date: date
    saved_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"), max_digits=12, decimal_places=2)
    dry_run: bool = False


class GoalAddSavedArgs(GoalSelectorArgs):
    add_amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    dry_run: bool = False


class GoalUpdateTargetArgs(GoalSelectorArgs):
    target_amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    dry_run: bool = False


class GoalUpdateDeadlineArgs(GoalSelectorArgs):
    deadline_date: date
    dry_run: bool = False


class GoalUpdateStatusArgs(GoalSelectorArgs):
    status: Literal["active", "paused", "completed", "cancelled"]
    dry_run: bool = False


class GoalDeleteArgs(GoalSelectorArgs):
    dry_run: bool = False


_GOALS_TOOL_SPECS: dict[str, tuple[type[BaseModel], str]] = {
    "goals_list": (GoalsListArgs, "List goals for the current user."),
    "goal_get": (GoalSelectorArgs, "Get one goal by id or name."),
    "goal_plan": (GoalPlanArgs, "Build goal funding plan + compact affordability suggestion."),
    "goal_budget_suggestions": (GoalPlanArgs, "Return compact monthly goal budgeting suggestions."),
    "goal_create": (GoalCreateArgs, "Create one goal."),
    "goal_add_saved": (GoalAddSavedArgs, "Add money toward one goal."),
    "goal_update_target": (GoalUpdateTargetArgs, "Update goal target amount."),
    "goal_update_deadline": (GoalUpdateDeadlineArgs, "Update goal deadline date."),
    "goal_update_status": (GoalUpdateStatusArgs, "Update goal status."),
    "goal_delete": (GoalDeleteArgs, "Delete one goal."),
}

GOALS_WRITE_TOOL_NAMES = {
    "goal_create",
    "goal_add_saved",
    "goal_update_target",
    "goal_update_deadline",
    "goal_update_status",
    "goal_delete",
}


def goals_tool_schemas() -> list[dict[str, Any]]:
    """Gemini function declaration schemas for goals chat tools only."""
    return [
        {
            "name": "goals_list",
            "description": _GOALS_TOOL_SPECS["goals_list"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {"status": {"type": "STRING", "enum": ["active", "paused", "completed", "cancelled", "all"]}},
            },
        },
        {
            "name": "goal_get",
            "description": _GOALS_TOOL_SPECS["goal_get"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {"goal_id": {"type": "STRING"}, "goal_name": {"type": "STRING"}},
            },
        },
        {
            "name": "goal_plan",
            "description": _GOALS_TOOL_SPECS["goal_plan"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "goal_id": {"type": "STRING"},
                    "goal_name": {"type": "STRING"},
                    "month_start": {"type": "STRING", "description": "YYYY-MM-01"},
                },
            },
        },
        {
            "name": "goal_budget_suggestions",
            "description": _GOALS_TOOL_SPECS["goal_budget_suggestions"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "goal_id": {"type": "STRING"},
                    "goal_name": {"type": "STRING"},
                    "month_start": {"type": "STRING", "description": "YYYY-MM-01"},
                },
            },
        },
        {
            "name": "goal_create",
            "description": _GOALS_TOOL_SPECS["goal_create"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "target_amount": {"type": "NUMBER"},
                    "saved_amount": {"type": "NUMBER"},
                    "deadline_date": {"type": "STRING", "description": "YYYY-MM-DD"},
                    "dry_run": {"type": "BOOLEAN"},
                },
                "required": ["name", "target_amount", "deadline_date"],
            },
        },
        {
            "name": "goal_add_saved",
            "description": _GOALS_TOOL_SPECS["goal_add_saved"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "goal_id": {"type": "STRING"},
                    "goal_name": {"type": "STRING"},
                    "add_amount": {"type": "NUMBER"},
                    "dry_run": {"type": "BOOLEAN"},
                },
                "required": ["add_amount"],
            },
        },
        {
            "name": "goal_update_target",
            "description": _GOALS_TOOL_SPECS["goal_update_target"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "goal_id": {"type": "STRING"},
                    "goal_name": {"type": "STRING"},
                    "target_amount": {"type": "NUMBER"},
                    "dry_run": {"type": "BOOLEAN"},
                },
                "required": ["target_amount"],
            },
        },
        {
            "name": "goal_update_deadline",
            "description": _GOALS_TOOL_SPECS["goal_update_deadline"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "goal_id": {"type": "STRING"},
                    "goal_name": {"type": "STRING"},
                    "deadline_date": {"type": "STRING", "description": "YYYY-MM-DD"},
                    "dry_run": {"type": "BOOLEAN"},
                },
                "required": ["deadline_date"],
            },
        },
        {
            "name": "goal_update_status",
            "description": _GOALS_TOOL_SPECS["goal_update_status"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "goal_id": {"type": "STRING"},
                    "goal_name": {"type": "STRING"},
                    "status": {"type": "STRING", "enum": ["active", "paused", "completed", "cancelled"]},
                    "dry_run": {"type": "BOOLEAN"},
                },
                "required": ["status"],
            },
        },
        {
            "name": "goal_delete",
            "description": _GOALS_TOOL_SPECS["goal_delete"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "goal_id": {"type": "STRING"},
                    "goal_name": {"type": "STRING"},
                    "dry_run": {"type": "BOOLEAN"},
                },
            },
        },
    ]


def _validate_args(tool_name: str, args: dict[str, Any]) -> BaseModel:
    spec = _GOALS_TOOL_SPECS.get(tool_name)
    if spec is None:
        raise GoalsToolArgumentError(f"Unknown tool: {tool_name}")
    model_cls = spec[0]
    try:
        if hasattr(model_cls, "model_validate"):
            return model_cls.model_validate(args)
        return model_cls.parse_obj(args)
    except ValidationError as exc:
        raise GoalsToolArgumentError(str(exc)) from exc


async def dispatch_goals_tool(
    connection: Any,
    user_id: UUID,
    tool_name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    payload = _validate_args(tool_name, args)

    if tool_name == "goals_list":
        result = await goals_list_tool(connection, user_id, status=payload.status)
        return {"kind": "read", "summary": f"Loaded {result['count']} goals.", "data": result}

    if tool_name == "goal_get":
        result = await get_goal_by_id_or_name(connection, user_id, goal_id=payload.goal_id, goal_name=payload.goal_name)
        return {"kind": "read", "summary": f"Loaded goal '{result['name']}'.", "data": result}

    if tool_name in {"goal_plan", "goal_budget_suggestions"}:
        result = await goal_plan_tool(
            connection,
            user_id,
            goal_id=payload.goal_id,
            goal_name=payload.goal_name,
            month_start=getattr(payload, "month_start", None),
        )
        required = _money(result["goal"]["recommended_monthly_save_amount"])
        return {
            "kind": "read",
            "summary": f"Built plan for '{result['goal']['name']}' (monthly save {required}).",
            "data": result,
        }

    if tool_name == "goal_create":
        result = await goal_create_tool(
            connection,
            user_id,
            name=payload.name,
            target_amount=payload.target_amount,
            deadline_date=payload.deadline_date,
            saved_amount=payload.saved_amount,
            dry_run=payload.dry_run,
        )
        status = "Previewed" if payload.dry_run else "Created"
        return {"kind": "write", "summary": f"{status} goal '{result['goal']['name']}'.", "data": result}

    if tool_name == "goal_add_saved":
        result = await goal_add_saved_tool(
            connection,
            user_id,
            goal_id=payload.goal_id,
            goal_name=payload.goal_name,
            add_amount=payload.add_amount,
            dry_run=payload.dry_run,
        )
        status = "Previewed" if payload.dry_run else "Updated"
        return {
            "kind": "write",
            "summary": f"{status} saved amount for '{result['goal']['name']}'.",
            "data": result,
        }

    if tool_name == "goal_update_target":
        result = await goal_update_tool(
            connection,
            user_id,
            goal_id=payload.goal_id,
            goal_name=payload.goal_name,
            patch={"target_amount": payload.target_amount},
            dry_run=payload.dry_run,
        )
        status = "Previewed" if payload.dry_run else "Updated"
        return {"kind": "write", "summary": f"{status} target for '{result['goal']['name']}'.", "data": result}

    if tool_name == "goal_update_deadline":
        result = await goal_update_tool(
            connection,
            user_id,
            goal_id=payload.goal_id,
            goal_name=payload.goal_name,
            patch={"deadline_date": payload.deadline_date},
            dry_run=payload.dry_run,
        )
        status = "Previewed" if payload.dry_run else "Updated"
        return {"kind": "write", "summary": f"{status} deadline for '{result['goal']['name']}'.", "data": result}

    if tool_name == "goal_update_status":
        result = await goal_update_tool(
            connection,
            user_id,
            goal_id=payload.goal_id,
            goal_name=payload.goal_name,
            patch={"status": payload.status},
            dry_run=payload.dry_run,
        )
        status = "Previewed" if payload.dry_run else "Updated"
        return {"kind": "write", "summary": f"{status} status for '{result['goal']['name']}'.", "data": result}

    if tool_name == "goal_delete":
        result = await goal_delete_tool(
            connection,
            user_id,
            goal_id=payload.goal_id,
            goal_name=payload.goal_name,
            dry_run=payload.dry_run,
        )
        status = "Previewed" if payload.dry_run else "Deleted"
        return {"kind": "write", "summary": f"{status} goal '{result['goal']['name']}'.", "data": result}

    raise GoalsToolArgumentError(f"Unsupported tool: {tool_name}")

