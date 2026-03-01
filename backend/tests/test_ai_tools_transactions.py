import asyncio
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.services import transactions_service


class InsertCursor:
    def __init__(self):
        self._row = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params=None):
        normalized = " ".join(query.split())
        if "INSERT INTO transactions" not in normalized:
            raise AssertionError(f"Unexpected query: {normalized}")

        user_id, category_id, tx_type, amount, occurred_on, merchant, note = params
        self._row = {
            "id": uuid4(),
            "user_id": user_id,
            "category_id": category_id,
            "type": tx_type,
            "amount": amount,
            "occurred_on": occurred_on,
            "merchant": merchant,
            "note": note,
            "created_at": datetime(2026, 3, 1, 12, 0, 0),
        }

    async def fetchone(self):
        return self._row


class InsertConnection:
    def cursor(self):
        return InsertCursor()


def _run(coro):
    return asyncio.run(coro)


def test_create_transaction_success(monkeypatch) -> None:
    user_id = uuid4()
    category_id = uuid4()

    async def fake_resolve(connection, user_id_arg, category_type, category_id_arg, category_name_arg):
        assert user_id_arg == user_id
        assert category_type == "expense"
        assert category_id_arg == category_id
        assert category_name_arg is None
        return {
            "id": category_id,
            "name": "Food",
            "slug": "food",
            "kind": "expense",
            "user_id": None,
            "is_system": True,
        }

    monkeypatch.setattr(transactions_service, "_resolve_visible_category", fake_resolve)

    result = _run(
        transactions_service.create_transaction_tool(
            InsertConnection(),
            user_id,
            occurred_on=date(2026, 2, 2),
            transaction_type="expense",
            amount=Decimal("12.50"),
            category_id=category_id,
            category_name=None,
            merchant="Cafe",
            note="Coffee",
            dry_run=False,
        )
    )

    assert result["created"] is True
    assert result["transaction"]["category_name"] == "Food"
    assert result["transaction"]["amount"] == Decimal("12.50")


def test_create_transaction_category_rejection(monkeypatch) -> None:
    user_id = uuid4()

    async def fake_resolve(*args, **kwargs):
        raise ValueError("Category kind does not match transaction type")

    monkeypatch.setattr(transactions_service, "_resolve_visible_category", fake_resolve)

    with pytest.raises(ValueError):
        _run(
            transactions_service.create_transaction_tool(
                InsertConnection(),
                user_id,
                occurred_on=date(2026, 2, 3),
                transaction_type="income",
                amount=Decimal("100.00"),
                category_id=None,
                category_name="Food",
                merchant=None,
                note=None,
                dry_run=False,
            )
        )


def test_create_transaction_dry_run_preview(monkeypatch) -> None:
    user_id = uuid4()
    category_id = uuid4()

    async def fake_resolve(*args, **kwargs):
        return {
            "id": category_id,
            "name": "Transport",
            "slug": "transport",
            "kind": "expense",
            "user_id": None,
            "is_system": True,
        }

    monkeypatch.setattr(transactions_service, "_resolve_visible_category", fake_resolve)

    result = _run(
        transactions_service.create_transaction_tool(
            InsertConnection(),
            user_id,
            occurred_on=date(2026, 2, 4),
            transaction_type="expense",
            amount=Decimal("40.00"),
            category_id=None,
            category_name="Transport",
            merchant="Compass",
            note=None,
            dry_run=True,
        )
    )

    assert result["created"] is False
    assert result["dry_run"] is True
    assert result["transaction"]["category_id"] == category_id
    assert result["transaction"]["merchant"] == "Compass"
