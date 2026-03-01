-- Budget limits schema

BEGIN;

CREATE TABLE IF NOT EXISTS budget_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- id
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, -- foreign id
    category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE, -- foreign id
    monthly_limit NUMERIC(12,2) NOT NULL, -- limit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_budget_limits_user_category UNIQUE (user_id, category_id),
    CONSTRAINT chk_budget_limits_monthly_limit_positive CHECK (monthly_limit > 0)
);

CREATE INDEX IF NOT EXISTS ix_budget_limits_user_id
    ON budget_limits (user_id);

CREATE OR REPLACE FUNCTION set_budget_limits_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_budget_limits_updated_at ON budget_limits;
CREATE TRIGGER trg_budget_limits_updated_at
BEFORE UPDATE ON budget_limits
FOR EACH ROW
EXECUTE FUNCTION set_budget_limits_updated_at();

COMMIT;
