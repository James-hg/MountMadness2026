from decimal import Decimal
from uuid import UUID

from app.services.budget_allocation import (
    AllocationCategory,
    ExistingBudget,
    compute_regenerated_allocations,
)


def _cat(id_str: str, slug: str) -> AllocationCategory:
    return AllocationCategory(category_id=UUID(id_str), slug=slug)


def _existing(id_str: str, amount: str, modified: bool) -> ExistingBudget:
    return ExistingBudget(
        category_id=UUID(id_str),
        limit_amount=Decimal(amount),
        is_user_modified=modified,
    )


def test_modified_rows_are_not_regenerated() -> None:
    in_scope = [
        _cat("00000000-0000-0000-0000-000000000101", "food"),
        _cat("00000000-0000-0000-0000-000000000102", "transport"),
        _cat("00000000-0000-0000-0000-000000000103", "entertainment"),
    ]
    existing = [
        _existing("00000000-0000-0000-0000-000000000101", "300.00", True),
        _existing("00000000-0000-0000-0000-000000000102", "100.00", False),
    ]

    result = compute_regenerated_allocations(
        total_budget_amount=Decimal("1000.00"),
        in_scope_categories=in_scope,
        existing_budgets=existing,
    )

    assert UUID("00000000-0000-0000-0000-000000000101") not in result
    assert sum(result.values(), Decimal("0.00")) == Decimal("700.00")


def test_when_locked_budget_exceeds_total_regenerated_rows_are_zero() -> None:
    in_scope = [
        _cat("00000000-0000-0000-0000-000000000111", "food"),
        _cat("00000000-0000-0000-0000-000000000112", "transport"),
    ]
    existing = [
        _existing("00000000-0000-0000-0000-000000000999", "1200.00", True),
    ]

    result = compute_regenerated_allocations(
        total_budget_amount=Decimal("1000.00"),
        in_scope_categories=in_scope,
        existing_budgets=existing,
    )

    assert result[UUID("00000000-0000-0000-0000-000000000111")] == Decimal("0.00")
    assert result[UUID("00000000-0000-0000-0000-000000000112")] == Decimal("0.00")


def test_repeated_inputs_are_idempotent() -> None:
    in_scope = [
        _cat("00000000-0000-0000-0000-000000000121", "food"),
        _cat("00000000-0000-0000-0000-000000000122", "transport"),
        _cat("00000000-0000-0000-0000-000000000123", "shopping"),
    ]
    existing = [
        _existing("00000000-0000-0000-0000-000000000122", "50.00", False),
    ]

    first = compute_regenerated_allocations(
        total_budget_amount=Decimal("500.00"),
        in_scope_categories=in_scope,
        existing_budgets=existing,
    )
    second = compute_regenerated_allocations(
        total_budget_amount=Decimal("500.00"),
        in_scope_categories=in_scope,
        existing_budgets=existing,
    )

    assert first == second
