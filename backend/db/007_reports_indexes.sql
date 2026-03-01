-- Reports performance indexes for aggregate-heavy queries.
-- Recommended patterns:
--   transactions(user_id, occurred_on DESC)
--   transactions(user_id, type)
--   transactions(user_id, category_id)
-- Current schema has no `transactions.currency`, so indexes are scoped by user/type/category/date.

BEGIN;

CREATE INDEX IF NOT EXISTS ix_transactions_reports_user_date
    ON transactions (user_id, occurred_on DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_transactions_reports_user_type_date
    ON transactions (user_id, type, occurred_on DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_transactions_reports_user_type_category_date
    ON transactions (user_id, type, category_id, occurred_on DESC)
    WHERE deleted_at IS NULL;

COMMIT;
