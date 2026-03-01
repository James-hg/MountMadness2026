from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Iterable
from uuid import UUID

CENT = Decimal("0.01")

KNOWN_WEIGHTS: dict[str, Decimal] = {
    "housing_rent": Decimal("0.45"),
    "food": Decimal("0.20"),
    "transport": Decimal("0.10"),
    "bills_utilities": Decimal("0.10"),
    "entertainment": Decimal("0.05"),
    "shopping": Decimal("0.05"),
    "health": Decimal("0.03"),
    "other": Decimal("0.02"),
}

DEFAULT_UNKNOWN_WEIGHT = Decimal("0.02")

FLOOR_RATIOS: dict[str, Decimal] = {
    "food": Decimal("0.10"),
    "transport": Decimal("0.05"),
    "bills_utilities": Decimal("0.05"),
}

CAP_RATIOS: dict[str, Decimal] = {
    "housing_rent": Decimal("0.60"),
    "food": Decimal("0.30"),
    "entertainment": Decimal("0.12"),
    "shopping": Decimal("0.12"),
    "other": Decimal("0.10"),
}


@dataclass(frozen=True)
class AllocationCategory:
    category_id: UUID
    slug: str


@dataclass(frozen=True)
class ExistingBudget:
    category_id: UUID
    limit_amount: Decimal
    is_user_modified: bool


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(CENT)


def _weight_for_slug(slug: str) -> Decimal:
    return KNOWN_WEIGHTS.get(slug, DEFAULT_UNKNOWN_WEIGHT)


def _fractional_part(value: Decimal) -> Decimal:
    return value - value.quantize(CENT, rounding=ROUND_DOWN)


def _rank_for_distribution(categories: Iterable[AllocationCategory]) -> list[AllocationCategory]:
    return sorted(categories, key=lambda c: (-_weight_for_slug(c.slug), str(c.category_id)))


def _rebalance_remainder(
    total: Decimal,
    raw_allocations: dict[UUID, Decimal],
    categories_by_id: dict[UUID, AllocationCategory],
) -> dict[UUID, Decimal]:
    rounded_down: dict[UUID, Decimal] = {
        category_id: amount.quantize(CENT, rounding=ROUND_DOWN)
        for category_id, amount in raw_allocations.items()
    }

    diff = total - sum(rounded_down.values(), Decimal("0.00"))
    if diff == Decimal("0.00"):
        return rounded_down

    steps = int((diff / CENT).to_integral_value())

    if steps > 0:
        order = sorted(
            raw_allocations.items(),
            key=lambda item: (-_fractional_part(item[1]), str(item[0])),
        )
        for i in range(steps):
            category_id = order[i % len(order)][0]
            rounded_down[category_id] += CENT

    elif steps < 0:
        order = sorted(
            raw_allocations.items(),
            key=lambda item: (_fractional_part(item[1]), str(item[0])),
        )
        for i in range(abs(steps)):
            category_id = order[i % len(order)][0]
            if rounded_down[category_id] >= CENT:
                rounded_down[category_id] -= CENT

    # Final safety pass to guarantee exact sum.
    current_sum = sum(rounded_down.values(), Decimal("0.00"))
    if current_sum != total and rounded_down:
        adjustment = total - current_sum
        first_id = sorted(categories_by_id.keys(), key=str)[0]
        rounded_down[first_id] += adjustment

    return {key: quantize_money(value) for key, value in rounded_down.items()}


def allocate_default_weights_v1(
    total_budget_amount: Decimal,
    categories: list[AllocationCategory],
) -> dict[UUID, Decimal]:
    total = quantize_money(total_budget_amount)

    if total < Decimal("0.00"):
        raise ValueError("total_budget_amount cannot be negative")

    if not categories:
        return {}

    categories_by_id = {category.category_id: category for category in categories}

    if len(categories) == 1:
        only = categories[0]
        return {only.category_id: total}

    if total == Decimal("0.00"):
        return {category.category_id: Decimal("0.00") for category in categories}

    min_per_category = CENT
    if total < min_per_category * Decimal(len(categories)):
        slots = int((total / min_per_category).to_integral_value(rounding=ROUND_DOWN))
        ranked = _rank_for_distribution(categories)
        allocated_ids = {c.category_id for c in ranked[:slots]}
        return {
            category.category_id: (CENT if category.category_id in allocated_ids else Decimal("0.00"))
            for category in categories
        }

    weights: dict[UUID, Decimal] = {
        category.category_id: _weight_for_slug(category.slug)
        for category in categories
    }

    floors: dict[UUID, Decimal] = {
        category.category_id: total * FLOOR_RATIOS.get(category.slug, Decimal("0.00"))
        for category in categories
    }

    floor_total = sum(floors.values(), Decimal("0.00"))

    allocations: dict[UUID, Decimal] = {category.category_id: Decimal("0.00") for category in categories}

    if floor_total > total and floor_total > Decimal("0.00"):
        scale = total / floor_total
        for category_id, floor_amount in floors.items():
            allocations[category_id] = floor_amount * scale
    else:
        remaining = total - floor_total
        weight_sum = sum(weights.values(), Decimal("0.00"))

        for category_id in allocations:
            floor_amount = floors[category_id]
            share = Decimal("0.00")
            if weight_sum > Decimal("0.00"):
                share = remaining * (weights[category_id] / weight_sum)
            allocations[category_id] = floor_amount + share

    caps: dict[UUID, Decimal | None] = {
        category.category_id: (
            total * CAP_RATIOS[category.slug]
            if category.slug in CAP_RATIOS
            else None
        )
        for category in categories
    }

    for _ in range(10):
        overflow = Decimal("0.00")
        clamped_ids: set[UUID] = set()

        for category_id, amount in allocations.items():
            cap = caps[category_id]
            if cap is not None and amount > cap:
                overflow += amount - cap
                allocations[category_id] = cap
                clamped_ids.add(category_id)

        if overflow <= Decimal("0.0000001"):
            break

        recipients = [
            category_id
            for category_id in allocations
            if category_id not in clamped_ids
            and (caps[category_id] is None or allocations[category_id] < caps[category_id])
        ]

        if not recipients:
            # Soft fallback when hard caps cannot satisfy total with selected scope.
            recipients = list(allocations.keys())

        recipient_weight_sum = sum(weights[category_id] for category_id in recipients)
        if recipient_weight_sum <= Decimal("0.00"):
            equal_share = overflow / Decimal(len(recipients))
            for category_id in recipients:
                allocations[category_id] += equal_share
        else:
            for category_id in recipients:
                allocations[category_id] += overflow * (weights[category_id] / recipient_weight_sum)

    return _rebalance_remainder(total, allocations, categories_by_id)


def compute_regenerated_allocations(
    *,
    total_budget_amount: Decimal,
    in_scope_categories: list[AllocationCategory],
    existing_budgets: list[ExistingBudget],
) -> dict[UUID, Decimal]:
    existing_by_id = {row.category_id: row for row in existing_budgets}

    locked_total = sum(
        (row.limit_amount for row in existing_budgets if row.is_user_modified),
        Decimal("0.00"),
    )

    regenerable_categories = [
        category
        for category in in_scope_categories
        if not existing_by_id.get(category.category_id, ExistingBudget(category.category_id, Decimal("0.00"), False)).is_user_modified
    ]

    if not regenerable_categories:
        return {}

    remaining_total = quantize_money(total_budget_amount - locked_total)

    if remaining_total <= Decimal("0.00"):
        return {category.category_id: Decimal("0.00") for category in regenerable_categories}

    return allocate_default_weights_v1(remaining_total, regenerable_categories)
