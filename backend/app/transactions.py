from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg import AsyncConnection
from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from .auth import get_current_user_id
from .database import get_db_connection

router = APIRouter(tags=["transactions"])

TransactionType = Literal["expense", "income"]
Amount = Annotated[Decimal, Field(gt=Decimal("0"), max_digits=12, decimal_places=2)]


class TransactionCreate(BaseModel):
    type: TransactionType
    amount: Amount
    occurred_on: date
    category_id: UUID
    merchant: str | None = Field(default=None, max_length=160)
    note: str | None = None

    @field_validator("merchant", "note", mode="before")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None

        return value


class TransactionUpdate(BaseModel):
    type: TransactionType | None = None
    amount: Amount | None = None
    occurred_on: date | None = None
    category_id: UUID | None = None
    merchant: str | None = Field(default=None, max_length=160)
    note: str | None = None

    @field_validator("merchant", "note", mode="before")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None

        return value

    @model_validator(mode="after")
    def check_not_empty(self) -> "TransactionUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        return self


class TransactionResponse(BaseModel):
    id: UUID
    user_id: UUID
    category_id: UUID
    type: TransactionType
    amount: Decimal
    occurred_on: date
    merchant: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("amount")
    def serialize_amount(self, value: Decimal) -> str:
        return _money(value)


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    limit: int
    offset: int
    total: int


class TransactionSummaryResponse(BaseModel):
    period_start: date
    period_end: date
    days_in_period: int
    total_income: Decimal
    total_expense: Decimal
    balance: Decimal
    period_expense: Decimal
    daily_burn_rate: Decimal
    monthly_burn_rate: Decimal
    runway_months: Decimal | None

    @field_serializer(
        "total_income",
        "total_expense",
        "balance",
        "period_expense",
        "daily_burn_rate",
        "monthly_burn_rate",
        "runway_months",
        when_used="always",
    )
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        if value is None:
            return None

        return _money(value)


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


async def _fetch_category(
    connection: AsyncConnection,
    *,
    category_id: UUID,
    user_id: UUID,
    expected_type: TransactionType,
) -> None:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, user_id, kind, is_system
            FROM categories
            WHERE id = %s
            """,
            (category_id,),
        )
        category = await cursor.fetchone()

    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    if not category["is_system"] and category["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden category access")

    if category["kind"] != expected_type:
        raise HTTPException(status_code=409, detail="Category kind and transaction type mismatch")


async def _ensure_transaction_access(
    connection: AsyncConnection,
    *,
    transaction_id: UUID,
    user_id: UUID,
) -> None:
    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT user_id, deleted_at
            FROM transactions
            WHERE id = %s
            """,
            (transaction_id,),
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if row["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden transaction access")

    if row["deleted_at"] is not None:
        raise HTTPException(status_code=404, detail="Transaction not found")


def _validate_date_range(date_from: date | None, date_to: date | None) -> tuple[date | None, date | None]:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")

    return date_from, date_to


def _build_list_filters(
    *,
    user_id: UUID,
    date_from: date | None,
    date_to: date | None,
    type_filter: TransactionType | None,
    category_id: UUID | None,
    q: str | None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
) -> tuple[str, list[object]]:
    filters = ["user_id = %s", "deleted_at IS NULL"]
    params: list[object] = [user_id]

    if date_from is not None:
        filters.append("occurred_on >= %s")
        params.append(date_from)

    if date_to is not None:
        filters.append("occurred_on <= %s")
        params.append(date_to)

    if type_filter is not None:
        filters.append("type = %s")
        params.append(type_filter)

    if category_id is not None:
        filters.append("category_id = %s")
        params.append(category_id)

    search = q.strip() if q else ""
    if search:
        pattern = f"%{search}%"
        filters.append("(merchant ILIKE %s OR note ILIKE %s)")
        params.extend([pattern, pattern])

    if amount_min is not None:
        filters.append("amount >= %s")
        params.append(amount_min)

    if amount_max is not None:
        filters.append("amount <= %s")
        params.append(amount_max)

    return " AND ".join(filters), params


@router.post("/transactions", response_model=TransactionResponse, status_code=201)
async def create_transaction(
    payload: TransactionCreate,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> TransactionResponse:
    await _fetch_category(
        connection,
        category_id=payload.category_id,
        user_id=user_id,
        expected_type=payload.type,
    )

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            INSERT INTO transactions (user_id, category_id, type, amount, occurred_on, merchant, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, user_id, category_id, type, amount, occurred_on, merchant, note, created_at, updated_at
            """,
            (
                user_id,
                payload.category_id,
                payload.type,
                payload.amount,
                payload.occurred_on,
                payload.merchant,
                payload.note,
            ),
        )
        row = await cursor.fetchone()

    return TransactionResponse.model_validate(row)


ALLOWED_SORTS = {
    "date_asc": "occurred_on ASC",
    "date_desc": "occurred_on DESC",
    "amount_asc": "amount ASC",
    "amount_desc": "amount DESC",
    "merchant_asc": "LOWER(merchant) ASC NULLS LAST",
    "merchant_desc": "LOWER(merchant) DESC NULLS LAST",
}


def _build_order_clause(sort_by: str | None) -> str:
    if not sort_by:
        return "occurred_on DESC, created_at DESC"

    clauses = []
    for key in sort_by.split(","):
        key = key.strip()
        if key in ALLOWED_SORTS:
            clauses.append(ALLOWED_SORTS[key])

    if not clauses:
        return "occurred_on DESC, created_at DESC"

    return ", ".join(clauses)


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    type_filter: TransactionType | None = Query(default=None, alias="type"),
    category_id: UUID | None = Query(default=None),
    q: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    amount_min: Decimal | None = Query(default=None, ge=Decimal("0")),
    amount_max: Decimal | None = Query(default=None, ge=Decimal("0")),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> TransactionListResponse:
    _validate_date_range(date_from, date_to)

    where_clause, params = _build_list_filters(
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        type_filter=type_filter,
        category_id=category_id,
        q=q,
        amount_min=amount_min,
        amount_max=amount_max,
    )

    order_clause = _build_order_clause(sort_by)

    async with connection.cursor() as cursor:
        await cursor.execute(
            f"SELECT COUNT(*) AS total FROM transactions WHERE {where_clause}",
            params,
        )
        count_row = await cursor.fetchone()

        await cursor.execute(
            f"""
            SELECT id, user_id, category_id, type, amount, occurred_on, merchant, note, created_at, updated_at
            FROM transactions
            WHERE {where_clause}
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
            """,
            [*params, limit, offset],
        )
        rows = await cursor.fetchall()

    return TransactionListResponse(
        items=[TransactionResponse.model_validate(row) for row in rows],
        limit=limit,
        offset=offset,
        total=count_row["total"],
    )


@router.get("/transactions/summary", response_model=TransactionSummaryResponse)
async def transactions_summary(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> TransactionSummaryResponse:
    _validate_date_range(date_from, date_to)

    period_end = date_to or date.today()
    period_start = date_from or (period_end - timedelta(days=29))

    if period_start > period_end:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) AS total_income,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) AS total_expense
            FROM transactions
            WHERE user_id = %s
              AND deleted_at IS NULL
            """,
            (user_id,),
        )
        totals_row = await cursor.fetchone()

        await cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS period_expense
            FROM transactions
            WHERE user_id = %s
              AND type = 'expense'
              AND occurred_on BETWEEN %s AND %s
              AND deleted_at IS NULL
            """,
            (user_id, period_start, period_end),
        )
        period_row = await cursor.fetchone()

    total_income = totals_row["total_income"]
    total_expense = totals_row["total_expense"]
    balance = total_income - total_expense

    period_expense = period_row["period_expense"]
    days_in_period = (period_end - period_start).days + 1

    daily_burn_rate = period_expense / Decimal(days_in_period)
    monthly_burn_rate = daily_burn_rate * Decimal("30")

    runway_months: Decimal | None = None
    if monthly_burn_rate > 0:
        runway_months = balance / monthly_burn_rate
        if runway_months < 0:
            runway_months = Decimal("0")

    return TransactionSummaryResponse(
        period_start=period_start,
        period_end=period_end,
        days_in_period=days_in_period,
        total_income=total_income,
        total_expense=total_expense,
        balance=balance,
        period_expense=period_expense,
        daily_burn_rate=daily_burn_rate,
        monthly_burn_rate=monthly_burn_rate,
        runway_months=runway_months,
    )


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> TransactionResponse:
    await _ensure_transaction_access(connection, transaction_id=transaction_id, user_id=user_id)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, user_id, category_id, type, amount, occurred_on, merchant, note, created_at, updated_at
            FROM transactions
            WHERE id = %s
              AND user_id = %s
              AND deleted_at IS NULL
            """,
            (transaction_id, user_id),
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return TransactionResponse.model_validate(row)


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: UUID,
    payload: TransactionUpdate,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> TransactionResponse:
    await _ensure_transaction_access(connection, transaction_id=transaction_id, user_id=user_id)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            SELECT id, user_id, category_id, type, amount, occurred_on, merchant, note, created_at, updated_at
            FROM transactions
            WHERE id = %s
              AND user_id = %s
              AND deleted_at IS NULL
            """,
            (transaction_id, user_id),
        )
        current = await cursor.fetchone()

    if current is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    updates = payload.model_dump(exclude_unset=True)

    next_type = updates.get("type", current["type"])
    next_category_id = updates.get("category_id", current["category_id"])

    await _fetch_category(
        connection,
        category_id=next_category_id,
        user_id=user_id,
        expected_type=next_type,
    )

    set_parts: list[str] = []
    params: list[object] = []

    for field in ["type", "amount", "occurred_on", "category_id", "merchant", "note"]:
        if field in updates:
            set_parts.append(f"{field} = %s")
            params.append(updates[field])

    if not set_parts:
        return TransactionResponse.model_validate(current)

    async with connection.cursor() as cursor:
        await cursor.execute(
            f"""
            UPDATE transactions
            SET {", ".join(set_parts)}
            WHERE id = %s
              AND user_id = %s
              AND deleted_at IS NULL
            RETURNING id, user_id, category_id, type, amount, occurred_on, merchant, note, created_at, updated_at
            """,
            [*params, transaction_id, user_id],
        )
        row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return TransactionResponse.model_validate(row)


@router.delete("/transactions/{transaction_id}", status_code=204)
async def delete_transaction(
    transaction_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    connection: AsyncConnection = Depends(get_db_connection),
) -> Response:
    await _ensure_transaction_access(connection, transaction_id=transaction_id, user_id=user_id)

    async with connection.cursor() as cursor:
        await cursor.execute(
            """
            UPDATE transactions
            SET deleted_at = NOW()
            WHERE id = %s
              AND user_id = %s
              AND deleted_at IS NULL
            """,
            (transaction_id, user_id),
        )

    return Response(status_code=204)
