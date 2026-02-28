# Categories DB Design -- 002

## Key Clarification

The list you gave (`food`, `housing/rent`, etc.) are **category values**, not database fields.

Use this model:

- one table `categories`
- one row per category
- transactions reference categories by `category_id`

## Recommended Columns (`categories`)

- `id` (UUID PK)
- `user_id` (nullable FK to `users.id`)
- `name` (display label)
- `slug` (stable identifier like `housing_rent`)
- `kind` (`expense` or `income`)
- `is_system` (true for default categories)
- `created_at`

Optional now, useful later:

- `icon`
- `color`

## Why This Design

- Supports your default categories immediately.
- Allows custom user categories later (set `user_id` to that user).
- Keeps API and analytics stable with `slug`.
- Works for both expenses and income categories.

## Your Default Expense Categories

- Food
- Housing / Rent
- Transport
- Insurance
- Tuition
- Bills / Utilities
- Shopping
- Entertainment
- Health
- Other

## Recommended Additions

- Add income categories too (at minimum):
  - Allowance / Transfer
  - Part-time Job
  - Scholarship
  - Refund
  - Other Income

## Notes for Transactions Table (next step)

When you design `transactions`, include:

- `category_id UUID NOT NULL REFERENCES categories(id)`
- `type` (`expense` / `income`) and enforce consistency with category `kind` in service logic.

## Files in Repo

- SQL schema: `backend/db/002_categories_schema.sql`
