from decimal import Decimal
from uuid import UUID

from app.services.budget_allocation import AllocationCategory, allocate_default_weights_v1


def _cat(id_str: str, slug: str) -> AllocationCategory:
    return AllocationCategory(category_id=UUID(id_str), slug=slug)


def test_allocation_sum_matches_total_exactly() -> None:
    categories = [
        _cat("00000000-0000-0000-0000-000000000001", "housing_rent"),
        _cat("00000000-0000-0000-0000-000000000002", "food"),
        _cat("00000000-0000-0000-0000-000000000003", "transport"),
        _cat("00000000-0000-0000-0000-000000000004", "bills_utilities"),
        _cat("00000000-0000-0000-0000-000000000005", "entertainment"),
    ]

    total = Decimal("2000.00")
    result = allocate_default_weights_v1(total, categories)

    assert sum(result.values(), Decimal("0.00")) == total


def test_fixed_defaults_receive_all_budget_and_others_zero() -> None:
    categories = [
        _cat("00000000-0000-0000-0000-000000000011", "housing_rent"),
        _cat("00000000-0000-0000-0000-000000000012", "food"),
        _cat("00000000-0000-0000-0000-000000000013", "transport"),
        _cat("00000000-0000-0000-0000-000000000014", "bills_utilities"),
        _cat("00000000-0000-0000-0000-000000000015", "entertainment"),
        _cat("00000000-0000-0000-0000-000000000016", "shopping"),
        _cat("00000000-0000-0000-0000-000000000017", "other"),
        _cat("00000000-0000-0000-0000-000000000018", "health"),
    ]

    total = Decimal("2500.00")
    result = allocate_default_weights_v1(total, categories)

    by_slug = {c.slug: result[c.category_id] for c in categories}

    # Vancouver fixed defaults receive the full total proportionally.
    assert by_slug["housing_rent"] > by_slug["transport"] > by_slug["bills_utilities"]

    assert by_slug["food"] == Decimal("0.00")
    assert by_slug["entertainment"] == Decimal("0.00")
    assert by_slug["shopping"] == Decimal("0.00")
    assert by_slug["other"] == Decimal("0.00")
    assert by_slug["health"] == Decimal("0.00")
    assert sum(result.values(), Decimal("0.00")) == total


def test_fixed_defaults_scale_when_total_is_small() -> None:
    categories = [
        _cat("00000000-0000-0000-0000-000000000061", "housing_rent"),
        _cat("00000000-0000-0000-0000-000000000062", "transport"),
        _cat("00000000-0000-0000-0000-000000000063", "bills_utilities"),
        _cat("00000000-0000-0000-0000-000000000064", "food"),
    ]
    total = Decimal("600.00")
    result = allocate_default_weights_v1(total, categories)

    by_slug = {c.slug: result[c.category_id] for c in categories}
    assert by_slug["food"] == Decimal("0.00")
    assert by_slug["housing_rent"] > by_slug["transport"] > by_slug["bills_utilities"]
    assert sum(result.values(), Decimal("0.00")) == total


def test_non_fixed_categories_remain_zero_when_fixed_category_exists() -> None:
    categories = [
        _cat("00000000-0000-0000-0000-000000000021", "food"),
        _cat("00000000-0000-0000-0000-000000000022", "gaming"),
        _cat("00000000-0000-0000-0000-000000000023", "transport"),
    ]

    total = Decimal("300.00")
    result = allocate_default_weights_v1(total, categories)

    assert result[UUID("00000000-0000-0000-0000-000000000022")] == Decimal("0.00")
    assert result[UUID("00000000-0000-0000-0000-000000000021")] == Decimal("0.00")
    assert result[UUID("00000000-0000-0000-0000-000000000023")] == total
    assert sum(result.values(), Decimal("0.00")) == total


def test_single_category_gets_full_budget() -> None:
    only = _cat("00000000-0000-0000-0000-000000000031", "food")
    total = Decimal("145.67")

    result = allocate_default_weights_v1(total, [only])

    assert result[only.category_id] == total


def test_very_small_budget_includes_fewer_categories() -> None:
    categories = [
        _cat("00000000-0000-0000-0000-000000000041", "food"),
        _cat("00000000-0000-0000-0000-000000000042", "transport"),
        _cat("00000000-0000-0000-0000-000000000043", "entertainment"),
    ]

    total = Decimal("0.02")
    result = allocate_default_weights_v1(total, categories)

    non_zero = [value for value in result.values() if value > Decimal("0.00")]
    assert len(non_zero) == 1
    assert non_zero[0] == Decimal("0.02")
    assert sum(result.values(), Decimal("0.00")) == total


def test_allocation_is_deterministic() -> None:
    categories = [
        _cat("00000000-0000-0000-0000-000000000051", "food"),
        _cat("00000000-0000-0000-0000-000000000052", "transport"),
        _cat("00000000-0000-0000-0000-000000000053", "shopping"),
        _cat("00000000-0000-0000-0000-000000000054", "other"),
    ]

    total = Decimal("1234.56")
    first = allocate_default_weights_v1(total, categories)
    second = allocate_default_weights_v1(total, categories)

    assert first == second
