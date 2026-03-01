# Dashboard Insights API (MVP)

## Endpoint
- `GET /dashboard/insights?month=YYYY-MM`

If `month` is omitted, the server uses the current month.

## Purpose
Provide one dashboard payload that powers:
- Budget Health progress bars (top 3 categories)
- Smart Insights cards (deterministic, no LLM)

## Auth and Scope
- Requires bearer token.
- Data is strictly scoped to authenticated `user_id`.

## Money Contract
- Uses existing DB `NUMERIC(12,2)` fields.
- API returns money as decimal strings with two digits:
  - `total_budget_amount`
  - `total_spent_amount`
  - `budget_amount`
  - `spent_amount`
  - `remaining_amount`

## Response Shape
```json
{
  "budget_health": {
    "month": "2026-03",
    "currency": "CAD",
    "total_budget_amount": "2000.00",
    "total_spent_amount": "1432.40",
    "total_budget_used_pct": 71,
    "categories": [
      {
        "category_id": "uuid-or-null",
        "category_name": "Food",
        "budget_amount": "500.00",
        "spent_amount": "420.00",
        "remaining_amount": "80.00",
        "used_pct": 84,
        "status": "warning",
        "note": null
      }
    ]
  },
  "smart_insights": {
    "insights": [
      {
        "key": "budget_pace",
        "title": "Budget Pace",
        "message": "You've used 71% of your monthly budget.",
        "severity": "warning",
        "metric": {"used_pct": 71}
      }
    ]
  }
}
```

## Budget Health Rules
- Month window: `[month_start, next_month_start)`.
- Expense source:
  - `transactions.type = 'expense'`
  - `deleted_at IS NULL`
- Active categories:
  - categories with monthly spend
  - plus categories with month budget rows
- `used_pct`:
  - `floor(spent / budget * 100)` when budget exists and `> 0`
  - `null` when budget is missing/non-positive
- Status:
  - `ok`: `used_pct` is null or `< 70`
  - `warning`: `70..100`
  - `over`: `> 100`
- `note` only for over-budget rows:
  - `"Over by $X.XX"`
- Top rows:
  - max 3 categories, sorted by:
    1. has budget row first
    2. `used_pct` desc (`null` lowest)
    3. spent desc
    4. name asc
  - include `Uncategorized` if it has monthly spend.

## Smart Insight Priority
Insights are selected in this order (max 5):
1. No-data starter insight (single card).
2. Budget pace (if total budget exists).
3. Top category dominance.
4. Most over-budget category.
5. Trend vs last month.
6. Runway (only when computable from 3 complete prior months).

## Files
- Router: `backend/app/dashboard.py`
- Service: `backend/app/services/dashboard_insights.py`
- Tests:
  - `backend/tests/test_dashboard_insights_service.py`
  - `backend/tests/test_dashboard_dates_contract.py`
