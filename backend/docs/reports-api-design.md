# Reports API Design (MVP)

## Purpose

Expose report endpoints that power dashboard insights from `transactions.amount NUMERIC(12,2)` data.

All report amounts are returned as decimal strings with 2 decimals.

## Authentication and Tenant Scope

- All routes require JWT auth.
- All queries are scoped to `user_id = get_current_user_id()`.
- Currency is filtered to `users.base_currency`.

## Endpoints

### `GET /reports/summary?month=YYYY-MM`

Returns summary cards for the selected month (or current month when omitted).

Fields:

- `currency`
- `month`
- `month_start`
- `month_end`
- `balance_amount`
- `monthly_spend_amount`
- `burn_rate_amount_per_month`
- `runway_days` (`null` when burn is effectively zero)

Rules:

- `balance_amount = sum(income) - sum(expense)` across all time.
- `monthly_spend_amount = expense sum in selected month`.
- Burn rate:
  1. Preferred: average of previous 3 complete months, only if all 3 have expense rows.
  2. Fallback: last 30-day expense average, anchored to selected month context.
  3. Else `0.00`.
- `runway_days = floor(balance / (burn_rate/30))`, minimum `0`, nullable for very small burn.

### `GET /reports/top-categories?month=YYYY-MM&limit=5`

Returns top expense categories for the selected month.

Fields:

- `currency`
- `month`
- `items[]`: `category`, `spent_amount`, `percentage`

Rules:

- Groups by category name.
- Null category is reported as `Uncategorized`.
- Ordered by `spent_amount DESC`, then `category ASC`.

### `GET /reports/trends?months=6`

Returns monthly series (oldest -> newest) including the current month.

Fields:

- `currency`
- `items[]`: `month`, `expense_amount`, `income_amount`

Rules:

- Missing months are zero-filled.
- Amounts are quantized to 2 decimals.

### `GET /reports/monthly-breakdown?month=YYYY-MM`

Returns day-level expense totals for one month.

Fields:

- `currency`
- `month`
- `items[]`: `date`, `expense_amount`

Rules:

- Every day in month is returned.
- Missing days are zero-filled.

## Performance Notes

Report queries rely on partial indexes from `backend/db/007_reports_indexes.sql`:

- `(user_id, currency, occurred_on DESC) WHERE deleted_at IS NULL`
- `(user_id, currency, type, occurred_on DESC) WHERE deleted_at IS NULL`
- `(user_id, currency, type, category_id, occurred_on DESC) WHERE deleted_at IS NULL`
