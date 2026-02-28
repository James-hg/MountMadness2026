# Transactions DB Design (MVP)

## Scope

Core transaction storage for the personal finance tracker:

- create/list/update/delete (soft delete)
- category-based expense/income tracking
- dashboard summary metrics

## Table: `transactions`

- `id` UUID PK
- `user_id` UUID FK -> `users(id)`
- `category_id` UUID FK -> `categories(id)`
- `type` (`expense` or `income`)
- `amount` `NUMERIC(12,2)` and must be `> 0`
- `occurred_on` date transaction happened
- `merchant` optional text (`VARCHAR(160)`)
- `note` optional text
- `created_at` timestamp
- `updated_at` timestamp (auto-update trigger)
- `deleted_at` timestamp (soft delete marker)

## Ownership and Visibility Rules

- Users can only CRUD their own transactions.
- Category is required for every transaction.
- Category visibility for create/update:
  - system category (`is_system = true`) is allowed
  - user category is allowed only when `category.user_id = auth_user`
- Category kind must match transaction type:
  - `category.kind = transaction.type`

## Soft Delete Policy

- Delete endpoint sets `deleted_at = NOW()`.
- List and summary always filter with `deleted_at IS NULL`.
- Deleted rows remain in DB for audit/history.

## Indexing

- `(user_id, occurred_on DESC)` partial on active rows
- `(user_id, category_id, occurred_on DESC)` partial on active rows
- `(user_id, type, occurred_on DESC)` partial on active rows
- `(user_id, created_at DESC)`

## Summary Calculations

- `balance = total_income - total_expense`
- `burn_rate = period_expense / days_in_period`
- `monthly_burn_rate = burn_rate * 30`
- `runway_months = balance / monthly_burn_rate` (null if burn rate is 0)

## API Endpoints

- `POST /transactions`
- `GET /transactions`
- `GET /transactions/{id}`
- `PATCH /transactions/{id}`
- `DELETE /transactions/{id}`
- `GET /transactions/summary`

## Query Filters

`GET /transactions` supports:

- `date_from`
- `date_to`
- `type`
- `category_id`
- `q` (merchant/note text search)
- `limit`
- `offset`

## Error Behavior

- `401` unauthenticated / invalid JWT
- `403` cross-user resource access
- `404` resource not found
- `409` category-type mismatch
- `422` validation failures
