import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import AsyncConnection
from pydantic import BaseModel, Field, field_serializer

from .database import get_db_connection
from .auth import get_current_user_id

router = APIRouter(prefix="/recurring-rules", tags=["recurring-rules"])

Frequency = Literal["monthly", "biweekly", "weekly"]


class RecurringRuleCreate(BaseModel):
    category_id: UUID
    type: Literal["expense", "income"] = "expense"
    amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    merchant: str | None = Field(default=None, max_length=160)
    note: str | None = None
    frequency: Frequency = "monthly"
    anchor_date: date


class RecurringRuleUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=Decimal("0"), max_digits=12, decimal_places=2)
    merchant: str | None = Field(default=None, max_length=160)
    note: str | None = None
    frequency: Frequency | None = None
    is_active: bool | None = None


class RecurringRuleOut(BaseModel):
    id: UUID
    user_id: UUID
    category_id: UUID
    category_name: str
    type: str
    amount: Decimal
    merchant: str | None
    note: str | None
    frequency: str
    anchor_date: date
    next_due_date: date
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("amount")
    def serialize_amount(self, value: Decimal) -> str:
        return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class GenerateResponse(BaseModel):
    generated_count: int


def _advance_date(current: date, frequency: str, anchor_date: date) -> date:
    if frequency == "weekly":
        return current + timedelta(days=7)
    elif frequency == "biweekly":
        return current + timedelta(days=14)
    else:  # monthly
        anchor_day = anchor_date.day
        next_month = current.month + 1
        next_year = current.year
        if next_month > 12:
            next_month = 1
            next_year += 1
        max_day = calendar.monthrange(next_year, next_month)[1]
        return date(next_year, next_month, min(anchor_day, max_day))


@router.post("", response_model=RecurringRuleOut, status_code=status.HTTP_201_CREATED)
async def create_recurring_rule(
    payload: RecurringRuleCreate,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
):
    async with connection.cursor() as cur:
        await cur.execute(
            "SELECT id, name FROM categories WHERE id = %s AND (is_system = TRUE OR user_id = %s)",
            (payload.category_id, user_id),
        )
        cat = await cur.fetchone()
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")

        await cur.execute(
            """
            INSERT INTO recurring_rules
                (user_id, category_id, type, amount, merchant, note, frequency, anchor_date, next_due_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, user_id, category_id, type, amount, merchant, note,
                      frequency, anchor_date, next_due_date, is_active, created_at, updated_at
            """,
            (
                user_id, payload.category_id, payload.type, payload.amount,
                payload.merchant, payload.note, payload.frequency,
                payload.anchor_date, payload.anchor_date,
            ),
        )
        row = await cur.fetchone()

    return RecurringRuleOut(**row, category_name=cat["name"])


@router.get("", response_model=list[RecurringRuleOut])
async def list_recurring_rules(
    is_active: bool | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
):
    sql = """
    SELECT r.id, r.user_id, r.category_id, c.name AS category_name,
           r.type, r.amount, r.merchant, r.note, r.frequency,
           r.anchor_date, r.next_due_date, r.is_active, r.created_at, r.updated_at
    FROM recurring_rules r
    JOIN categories c ON c.id = r.category_id
    WHERE r.user_id = %s
      AND (%s::boolean IS NULL OR r.is_active = %s)
    ORDER BY r.next_due_date ASC, c.name ASC;
    """
    async with connection.cursor() as cur:
        await cur.execute(sql, (user_id, is_active, is_active))
        return await cur.fetchall()


@router.get("/{rule_id}", response_model=RecurringRuleOut)
async def get_recurring_rule(
    rule_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
):
    sql = """
    SELECT r.id, r.user_id, r.category_id, c.name AS category_name,
           r.type, r.amount, r.merchant, r.note, r.frequency,
           r.anchor_date, r.next_due_date, r.is_active, r.created_at, r.updated_at
    FROM recurring_rules r
    JOIN categories c ON c.id = r.category_id
    WHERE r.id = %s AND r.user_id = %s;
    """
    async with connection.cursor() as cur:
        await cur.execute(sql, (rule_id, user_id))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Recurring rule not found")
        return row


@router.patch("/{rule_id}", response_model=RecurringRuleOut)
async def update_recurring_rule(
    rule_id: UUID,
    payload: RecurringRuleUpdate,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
):
    async with connection.cursor() as cur:
        # Fetch existing rule
        await cur.execute(
            "SELECT * FROM recurring_rules WHERE id = %s AND user_id = %s",
            (rule_id, user_id),
        )
        existing = await cur.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Recurring rule not found")

        # Build update fields
        new_amount = payload.amount if payload.amount is not None else existing["amount"]
        new_merchant = payload.merchant if payload.merchant is not None else existing["merchant"]
        new_note = payload.note if payload.note is not None else existing["note"]
        new_frequency = payload.frequency if payload.frequency is not None else existing["frequency"]
        new_is_active = payload.is_active if payload.is_active is not None else existing["is_active"]

        # If frequency changed, recalculate next_due_date from anchor_date
        new_next_due = existing["next_due_date"]
        if payload.frequency is not None and payload.frequency != existing["frequency"]:
            new_next_due = _advance_date(
                existing["anchor_date"], payload.frequency, existing["anchor_date"]
            )
            # Ensure next_due_date is in the future
            today = date.today()
            while new_next_due < today:
                new_next_due = _advance_date(new_next_due, payload.frequency, existing["anchor_date"])

        await cur.execute(
            """
            UPDATE recurring_rules
            SET amount = %s, merchant = %s, note = %s, frequency = %s,
                is_active = %s, next_due_date = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, user_id, category_id, type, amount, merchant, note,
                      frequency, anchor_date, next_due_date, is_active, created_at, updated_at
            """,
            (new_amount, new_merchant, new_note, new_frequency, new_is_active, new_next_due, rule_id, user_id),
        )
        row = await cur.fetchone()

        # Get category name
        await cur.execute("SELECT name FROM categories WHERE id = %s", (row["category_id"],))
        cat = await cur.fetchone()

    return RecurringRuleOut(**row, category_name=cat["name"])


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring_rule(
    rule_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
):
    async with connection.cursor() as cur:
        await cur.execute(
            "UPDATE recurring_rules SET is_active = FALSE WHERE id = %s AND user_id = %s RETURNING id",
            (rule_id, user_id),
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Recurring rule not found")
    return None


@router.post("/generate", response_model=GenerateResponse)
async def generate_due_transactions(
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
):
    today = date.today()
    generated = 0

    async with connection.cursor() as cur:
        await cur.execute(
            """
            SELECT id, user_id, category_id, type, amount, merchant, note,
                   frequency, anchor_date, next_due_date
            FROM recurring_rules
            WHERE user_id = %s AND is_active = TRUE AND next_due_date <= %s
            """,
            (user_id, today),
        )
        rules = await cur.fetchall()

    for rule in rules:
        next_due = rule["next_due_date"]
        while next_due <= today:
            async with connection.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO transactions
                        (user_id, category_id, type, amount, occurred_on, merchant, note, recurring_rule_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        rule["user_id"], rule["category_id"], rule["type"],
                        rule["amount"], next_due, rule["merchant"], rule["note"], rule["id"],
                    ),
                )
            generated += 1
            next_due = _advance_date(next_due, rule["frequency"], rule["anchor_date"])

        # Update next_due_date to the next future occurrence
        async with connection.cursor() as cur:
            await cur.execute(
                "UPDATE recurring_rules SET next_due_date = %s WHERE id = %s",
                (next_due, rule["id"]),
            )

    return GenerateResponse(generated_count=generated)
