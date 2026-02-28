# CRUD Operations and Endpoint Planning

## Users and Auth

- Create: sign up.
- Read: get profile/session.
- Update: change password (optional).
- Delete: delete account (not required for MVP).

## Categories

- Create: add custom category.
- Read: list categories.
- Update: rename category.
- Delete: remove category (or soft delete).

## Transactions (Core Resource)

- Create: add income/expense manually.
- Read: list transactions (filter by date range, category, type).
- Update: edit amount, date, category, merchant, notes.
- Delete: remove transaction.

## Receipt Import (Optional)

- Create: upload receipt image.
- Read: get extracted fields.
- Update: user confirms/edits extracted transaction, then saves.
- Delete: delete receipt record (optional).

## API Design Notes

- Prioritize Users/Auth, Categories, and Transactions for MVP.
- Keep receipt import behind a feature flag or mark as stretch goal.
- Define consistent response envelope and status codes across all resources.
