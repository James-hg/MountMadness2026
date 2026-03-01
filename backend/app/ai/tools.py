"""Tool schemas, argument validation, and safe tool dispatcher for `/ai/chat`."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, root_validator, validator

from app.services.budget_service import (
    apply_budget_plan_tool,
    suggest_budget_tool,
    simulate_budget_change_tool,
)
from app.services.insights_service import (
    compare_category_trend_tool,
    detect_anomalies_tool,
    get_financial_health_snapshot_tool,
    get_fixed_variable_breakdown_tool,
    plan_savings_goal_tool,
    project_future_tool,
)
from app.services.transactions_service import create_transaction_tool, get_summary_tool


class ToolArgumentError(Exception):
    """Raised when tool name or arguments fail validation."""


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _validate_month_start(value: date) -> date:
    if value.day != 1:
        raise ValueError("month_start must be YYYY-MM-01")
    return value


class CreateTransactionArgs(BaseModel):
    occurred_on: date
    type: Literal["income", "expense"]
    amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    category_id: UUID | None = None
    category_name: str | None = Field(default=None, max_length=80)
    merchant: str | None = Field(default=None, max_length=160)
    note: str | None = None
    dry_run: bool = False

    @root_validator(skip_on_failure=True)
    def ensure_category_selector(cls, values):
        if values.get("category_id") is None and not values.get("category_name"):
            raise ValueError("Provide category_id or category_name")
        return values


class DateRangeSummaryArgs(BaseModel):
    start_date: date
    end_date: date
    group_by: Literal["none", "category", "day"] = "none"

    @root_validator(skip_on_failure=True)
    def ensure_valid_range(cls, values):
        start_date = values.get("start_date")
        end_date = values.get("end_date")
        if start_date and end_date and end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        return values


class SuggestBudgetOverrideItem(BaseModel):
    category_id: UUID | None = None
    category_name: str | None = Field(default=None, max_length=80)
    limit_amount: Decimal = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)

    @root_validator(skip_on_failure=True)
    def ensure_category_selector(cls, values):
        if values.get("category_id") is None and not values.get("category_name"):
            raise ValueError("Provide category_id or category_name")
        return values


class SuggestBudgetArgs(BaseModel):
    month_start: date
    total_budget_amount: Decimal | None = Field(default=None, gt=Decimal("0"), max_digits=12, decimal_places=2)
    fixed_overrides: list[SuggestBudgetOverrideItem] | None = None

    @validator("month_start")
    def validate_month_start(cls, value: date) -> date:
        return _validate_month_start(value)


class ApplyBudgetPlanItem(BaseModel):
    category_id: UUID | None = None
    category_name: str | None = Field(default=None, max_length=80)
    limit_amount: Decimal = Field(ge=Decimal("0"), max_digits=12, decimal_places=2)

    @root_validator(skip_on_failure=True)
    def ensure_category_selector(cls, values):
        if values.get("category_id") is None and not values.get("category_name"):
            raise ValueError("Provide category_id or category_name")
        return values


class ApplyBudgetPlanArgs(BaseModel):
    month_start: date
    allocations: list[ApplyBudgetPlanItem] = Field(default_factory=list)
    dry_run: bool = False

    @validator("month_start")
    def validate_month_start(cls, value: date) -> date:
        return _validate_month_start(value)

    @root_validator(skip_on_failure=True)
    def ensure_allocations_not_empty(cls, values):
        allocations = values.get("allocations") or []
        if not allocations:
            raise ValueError("allocations must include at least one category")
        return values


class CompareCategoryTrendArgs(BaseModel):
    month_start: date
    lookback_months: int = Field(default=3, ge=1, le=12)

    @validator("month_start")
    def validate_month_start(cls, value: date) -> date:
        return _validate_month_start(value)


class SimulateBudgetChangeArgs(BaseModel):
    month_start: date
    category_id: UUID
    delta_amount: Decimal = Field(max_digits=12, decimal_places=2)

    @validator("month_start")
    def validate_month_start(cls, value: date) -> date:
        return _validate_month_start(value)


class FinancialHealthSnapshotArgs(BaseModel):
    month_start: date

    @validator("month_start")
    def validate_month_start(cls, value: date) -> date:
        return _validate_month_start(value)


class ProjectFutureArgs(BaseModel):
    months_ahead: int = Field(default=3, ge=1, le=24)


class FixedVariableBreakdownArgs(BaseModel):
    month_start: date
    fixed_categories: list[str] = Field(
        default_factory=lambda: ["housing_rent", "transport", "bills_utilities"]
    )

    @validator("month_start")
    def validate_month_start(cls, value: date) -> date:
        return _validate_month_start(value)


class DetectAnomaliesArgs(BaseModel):
    month_start: date
    compare_to: Literal["last_month", "avg_3m"] = "avg_3m"

    @validator("month_start")
    def validate_month_start(cls, value: date) -> date:
        return _validate_month_start(value)


class PlanSavingsGoalArgs(BaseModel):
    target_amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    months: int = Field(ge=1, le=36)
    month_start: date | None = None

    @validator("month_start")
    def validate_month_start(cls, value: date | None) -> date | None:
        if value is None:
            return None
        return _validate_month_start(value)


_TOOL_SPECS: dict[str, tuple[type[BaseModel], str]] = {
    "create_transaction": (
        CreateTransactionArgs,
        "Create one income or expense transaction for the authenticated user.",
    ),
    "apply_budget_plan": (
        ApplyBudgetPlanArgs,
        "Apply monthly category budgets for one month (upsert total + categories).",
    ),
    "get_summary": (
        DateRangeSummaryArgs,
        "Summarize income/expense/net and top categories for a date range.",
    ),
    "suggest_budget": (
        SuggestBudgetArgs,
        "Suggest a monthly category budget allocation without writing to DB.",
    ),
    "compare_category_trend": (
        CompareCategoryTrendArgs,
        "Compare current-month category spend to average spend from prior months.",
    ),
    "simulate_budget_change": (
        SimulateBudgetChangeArgs,
        "Simulate impact of changing one category budget amount.",
    ),
    "get_financial_health_snapshot": (
        FinancialHealthSnapshotArgs,
        "Get balance, spend, burn, runway, budget usage, and top category for a month.",
    ),
    "project_future": (
        ProjectFutureArgs,
        "Project ending balance and runway assuming current burn rate continues.",
    ),
    "get_fixed_variable_breakdown": (
        FixedVariableBreakdownArgs,
        "Split monthly expenses into fixed vs variable groups by category slug list.",
    ),
    "detect_anomalies": (
        DetectAnomaliesArgs,
        "Detect unusual spending spikes by category for a month.",
    ),
    "plan_savings_goal": (
        PlanSavingsGoalArgs,
        "Plan monthly savings toward a target using simple category-cut heuristics.",
    ),
}


def tool_schemas() -> list[dict[str, Any]]:
    """Return Gemini function declaration schema list."""
    return [
        {
            "name": "create_transaction",
            "description": _TOOL_SPECS["create_transaction"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "occurred_on": {"type": "STRING", "description": "Transaction date in YYYY-MM-DD"},
                    "type": {"type": "STRING", "enum": ["income", "expense"]},
                    "amount": {"type": "NUMBER", "description": "Amount as decimal number with 2 decimals"},
                    "category_id": {"type": "STRING", "description": "Category UUID"},
                    "category_name": {"type": "STRING"},
                    "merchant": {"type": "STRING"},
                    "note": {"type": "STRING"},
                    "dry_run": {"type": "BOOLEAN"},
                },
                "required": ["occurred_on", "type", "amount"],
            },
        },
        {
            "name": "apply_budget_plan",
            "description": _TOOL_SPECS["apply_budget_plan"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "month_start": {"type": "STRING", "description": "YYYY-MM-01"},
                    "allocations": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "category_id": {"type": "STRING"},
                                "category_name": {"type": "STRING"},
                                "limit_amount": {"type": "NUMBER"},
                            },
                            "required": ["limit_amount"],
                        },
                    },
                    "dry_run": {"type": "BOOLEAN"},
                },
                "required": ["month_start", "allocations"],
            },
        },
        {
            "name": "get_summary",
            "description": _TOOL_SPECS["get_summary"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "start_date": {"type": "STRING", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "STRING", "description": "YYYY-MM-DD"},
                    "group_by": {"type": "STRING", "enum": ["none", "category", "day"]},
                },
                "required": ["start_date", "end_date"],
            },
        },
        {
            "name": "suggest_budget",
            "description": _TOOL_SPECS["suggest_budget"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "month_start": {"type": "STRING", "description": "YYYY-MM-01"},
                    "total_budget_amount": {"type": "NUMBER"},
                    "fixed_overrides": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "category_id": {"type": "STRING"},
                                "category_name": {"type": "STRING"},
                                "limit_amount": {"type": "NUMBER"},
                            },
                            "required": ["limit_amount"],
                        },
                    },
                },
                "required": ["month_start"],
            },
        },
        {
            "name": "compare_category_trend",
            "description": _TOOL_SPECS["compare_category_trend"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "month_start": {"type": "STRING", "description": "YYYY-MM-01"},
                    "lookback_months": {"type": "INTEGER"},
                },
                "required": ["month_start"],
            },
        },
        {
            "name": "simulate_budget_change",
            "description": _TOOL_SPECS["simulate_budget_change"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "month_start": {"type": "STRING", "description": "YYYY-MM-01"},
                    "category_id": {"type": "STRING"},
                    "delta_amount": {"type": "NUMBER"},
                },
                "required": ["month_start", "category_id", "delta_amount"],
            },
        },
        {
            "name": "get_financial_health_snapshot",
            "description": _TOOL_SPECS["get_financial_health_snapshot"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "month_start": {"type": "STRING", "description": "YYYY-MM-01"},
                },
                "required": ["month_start"],
            },
        },
        {
            "name": "project_future",
            "description": _TOOL_SPECS["project_future"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "months_ahead": {"type": "INTEGER"},
                },
                "required": ["months_ahead"],
            },
        },
        {
            "name": "get_fixed_variable_breakdown",
            "description": _TOOL_SPECS["get_fixed_variable_breakdown"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "month_start": {"type": "STRING", "description": "YYYY-MM-01"},
                    "fixed_categories": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["month_start"],
            },
        },
        {
            "name": "detect_anomalies",
            "description": _TOOL_SPECS["detect_anomalies"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "month_start": {"type": "STRING", "description": "YYYY-MM-01"},
                    "compare_to": {"type": "STRING", "enum": ["last_month", "avg_3m"]},
                },
                "required": ["month_start"],
            },
        },
        {
            "name": "plan_savings_goal",
            "description": _TOOL_SPECS["plan_savings_goal"][1],
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "target_amount": {"type": "NUMBER"},
                    "months": {"type": "INTEGER"},
                    "month_start": {"type": "STRING", "description": "YYYY-MM-01"},
                },
                "required": ["target_amount", "months"],
            },
        },
    ]


def _validate_tool_args(tool_name: str, args: dict[str, Any]) -> BaseModel:
    spec = _TOOL_SPECS.get(tool_name)
    if spec is None:
        raise ToolArgumentError(f"Unknown tool: {tool_name}")

    model_cls = spec[0]
    try:
        if hasattr(model_cls, "model_validate"):
            return model_cls.model_validate(args)
        return model_cls.parse_obj(args)
    except ValidationError as exc:
        raise ToolArgumentError(str(exc)) from exc


def _dump_model(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


async def dispatch_tool(
    connection: Any,
    user_id: UUID,
    tool_name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Validate args and dispatch one tool call to safe backend services."""
    payload = _validate_tool_args(tool_name, args)

    if tool_name == "create_transaction":
        parsed = payload
        result = await create_transaction_tool(
            connection,
            user_id,
            occurred_on=parsed.occurred_on,
            transaction_type=parsed.type,
            amount=parsed.amount,
            category_id=parsed.category_id,
            category_name=parsed.category_name,
            merchant=parsed.merchant,
            note=parsed.note,
            dry_run=parsed.dry_run,
        )
        transaction = result["transaction"]
        status = "Previewed" if parsed.dry_run else "Created"
        summary = (
            f"{status} {transaction['type']} transaction {_money(transaction['amount'])} "
            f"for {transaction['category_name']} on {transaction['occurred_on']}."
        )
        return {"kind": "write", "summary": summary, "data": result}

    if tool_name == "apply_budget_plan":
        parsed = payload
        result = await apply_budget_plan_tool(
            connection,
            user_id,
            month_start=parsed.month_start,
            allocations=[_dump_model(item) for item in parsed.allocations],
            dry_run=parsed.dry_run,
        )
        summary = (
            f"{'Previewed' if parsed.dry_run else 'Applied'} budget plan for {parsed.month_start}: "
            f"{len(result['applied'])} categories, total {_money(result['total_budget_amount'])}."
        )
        return {"kind": "write", "summary": summary, "data": result}

    if tool_name == "get_summary":
        parsed = payload
        result = await get_summary_tool(
            connection,
            user_id,
            start_date=parsed.start_date,
            end_date=parsed.end_date,
            group_by=parsed.group_by,
        )
        summary = (
            f"Range summary {result['start_date']} to {result['end_date']}: "
            f"income {_money(result['income_total'])}, expense {_money(result['expense_total'])}, "
            f"net {_money(result['net_amount'])}."
        )
        return {"kind": "read", "summary": summary, "data": result}

    if tool_name == "suggest_budget":
        parsed = payload
        result = await suggest_budget_tool(
            connection,
            user_id,
            month_start=parsed.month_start,
            total_budget_amount=parsed.total_budget_amount,
            fixed_overrides=[_dump_model(item) for item in parsed.fixed_overrides] if parsed.fixed_overrides else None,
        )
        summary = (
            f"Suggested budget for {parsed.month_start} with total "
            f"{_money(result['total_budget_amount'])} across {len(result['allocations'])} categories."
        )
        return {"kind": "read", "summary": summary, "data": result}

    if tool_name == "compare_category_trend":
        parsed = payload
        result = await compare_category_trend_tool(
            connection,
            user_id,
            month_start=parsed.month_start,
            lookback_months=parsed.lookback_months,
        )
        summary = f"Compared category trend for {result['month']} vs prior {result['lookback_months']} months."
        return {"kind": "read", "summary": summary, "data": result}

    if tool_name == "simulate_budget_change":
        parsed = payload
        result = await simulate_budget_change_tool(
            connection,
            user_id,
            month_start=parsed.month_start,
            category_id=parsed.category_id,
            delta_amount=parsed.delta_amount,
        )
        summary = (
            f"Simulated {result['category_name']} budget delta {_money(result['delta_amount'])}; "
            f"projected burn {_money(result['projected_burn_amount_per_month'])}/month."
        )
        return {"kind": "read", "summary": summary, "data": result}

    if tool_name == "get_financial_health_snapshot":
        parsed = payload
        result = await get_financial_health_snapshot_tool(
            connection,
            user_id,
            month_start=parsed.month_start,
        )
        summary = (
            f"Health snapshot {result['month']}: spend {_money(result['monthly_spend_amount'])}, "
            f"burn {_money(result['burn_rate_amount_per_month'])}/month."
        )
        return {"kind": "read", "summary": summary, "data": result}

    if tool_name == "project_future":
        parsed = payload
        result = await project_future_tool(
            connection,
            user_id,
            months_ahead=parsed.months_ahead,
        )
        summary = (
            f"Projected {result['months_ahead']} months ahead: "
            f"ending balance {_money(result['projected_balance_amount'])}."
        )
        return {"kind": "read", "summary": summary, "data": result}

    if tool_name == "get_fixed_variable_breakdown":
        parsed = payload
        result = await get_fixed_variable_breakdown_tool(
            connection,
            user_id,
            month_start=parsed.month_start,
            fixed_categories=parsed.fixed_categories,
        )
        summary = (
            f"Fixed/variable for {result['month']}: fixed {_money(result['fixed_total_amount'])}, "
            f"variable {_money(result['variable_total_amount'])}."
        )
        return {"kind": "read", "summary": summary, "data": result}

    if tool_name == "detect_anomalies":
        parsed = payload
        result = await detect_anomalies_tool(
            connection,
            user_id,
            month_start=parsed.month_start,
            compare_to=parsed.compare_to,
        )
        summary = f"Detected {len(result['items'])} spending anomalies for {result['month']}."
        return {"kind": "read", "summary": summary, "data": result}

    if tool_name == "plan_savings_goal":
        parsed = payload
        result = await plan_savings_goal_tool(
            connection,
            user_id,
            target_amount=parsed.target_amount,
            months=parsed.months,
            month_start=parsed.month_start,
        )
        summary = (
            f"Built savings plan for {_money(result['target_amount'])} over {result['months']} months; "
            f"need {_money(result['required_monthly_savings_amount'])}/month."
        )
        return {"kind": "read", "summary": summary, "data": result}

    raise ToolArgumentError(f"Unsupported tool: {tool_name}")
