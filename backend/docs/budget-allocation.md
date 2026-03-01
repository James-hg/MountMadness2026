# Budget Allocation (Smart Monthly)

## Fixed Vancouver defaults (auto-allocation)

- `housing_rent`: `900.00` (UI suggested range: `800.00` to `1300.00`)
- `transport`: `140.00` (student-friendly midpoint between transit-only and occasional ride-share)
- `bills_utilities`: `120.00` (suggested range: `120` to `150`)

Only these fixed categories receive allocation. All other categories are set to `0.00`.
The monthly total is distributed across the fixed set proportionally to baseline amounts.

## Base weights (fallback only)

- `food`: `0.20`
- `entertainment`: `0.05`
- `shopping`: `0.05`
- `health`: `0.03`
- `other`: `0.02`
- unknown categories: `0.02` each

## Floors (fallback only)

Applied when category exists in scope:

- `food >= 10%`
- `transport >= 5%`
- `bills_utilities >= 5%`

Note: floors are applied only for non-fixed categories after fixed baselines are reserved.

## Caps (fallback only)

- `housing_rent <= 60%`
- `food <= 30%`
- `entertainment <= 12%`
- `shopping <= 12%`
- `other <= 10%`

Note: caps are applied only for non-fixed categories. Fixed defaults are intentionally stable and not cap-clamped.

## Deterministic algorithm

1. Build in-scope category set.
2. Single-category scope -> assign 100% to that category.
3. If any fixed categories are present in scope, distribute the full monthly total across only that fixed set.
4. Set all non-fixed categories to `0.00`.
5. Quantize to cents (`0.01`).
6. Ensure exact sum equality to total:
   - distribute +/- `0.01` remainder deterministically (fractional remainder + category id tie-break).
7. Tiny-budget handling:
   - if total is smaller than number of categories * `0.01`, include fewer categories by highest weight.

## Spent / Remaining Calculation

For month window `[month_start, month_end]`:

- `spent_amount` = sum of user expense transactions per category
- excludes soft-deleted transactions (`deleted_at IS NULL`)
- `remaining_amount = limit_amount - spent_amount` (can be negative)

## Validation and Error Semantics

- `401`: missing/invalid bearer token
- `403`: user does not own non-system category
- `404`: category not found
- `409`: category is not expense kind
- `422`: invalid `month_start` or payload

`month_start` must be first day of month only.

## Key Backend Files

- Route layer: `backend/app/budget.py`
- Allocation logic: `backend/app/services/budget_allocation.py`
- Date helpers: `backend/app/services/budget_dates.py`
- Migration: `backend/db/006_smart_budget_allocation.sql`
- Tests:
  - `backend/tests/test_budget_allocation_math.py`
  - `backend/tests/test_budget_total_regeneration.py`
  - `backend/tests/test_budget_get_and_category_update.py`
