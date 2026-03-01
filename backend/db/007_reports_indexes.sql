-- Reports performance indexes for aggregate-heavy queries.
-- Recommended patterns:
--   transactions(user_id, occurred_on DESC)
--   transactions(user_id, type)
--   transactions(user_id, category_id)
-- These index variants additionally include currency, which reports filter on.

BEGIN;

CREATE INDEX IF NOT EXISTS ix_transactions_reports_user_currency_date
    ON transactions (user_id, currency, occurred_on DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_transactions_reports_user_currency_type_date
    ON transactions (user_id, currency, type, occurred_on DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_transactions_reports_user_currency_type_category_date
    ON transactions (user_id, currency, type, category_id, occurred_on DESC)
    WHERE deleted_at IS NULL;

COMMIT;
