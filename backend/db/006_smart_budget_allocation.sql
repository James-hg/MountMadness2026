-- Smart budget allocation schema (numeric amounts)

BEGIN;

ALTER TABLE users
ADD COLUMN IF NOT EXISTS base_currency VARCHAR(3) NOT NULL DEFAULT 'CAD';

CREATE TABLE IF NOT EXISTS monthly_budget_totals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    month_start DATE NOT NULL,
    total_budget_amount NUMERIC(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    allocation_strategy VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_monthly_budget_totals_user_month UNIQUE (user_id, month_start),
    CONSTRAINT chk_monthly_budget_totals_positive CHECK (total_budget_amount > 0),
    CONSTRAINT chk_monthly_budget_totals_month_start CHECK (
        month_start = date_trunc('month', month_start)::DATE
    )
);

CREATE TABLE IF NOT EXISTS budgets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    month_start DATE NOT NULL,
    limit_amount NUMERIC(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    is_user_modified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_budgets_user_category_month UNIQUE (user_id, category_id, month_start),
    CONSTRAINT chk_budgets_limit_non_negative CHECK (limit_amount >= 0),
    CONSTRAINT chk_budgets_month_start CHECK (
        month_start = date_trunc('month', month_start)::DATE
    )
);

CREATE INDEX IF NOT EXISTS ix_monthly_budget_totals_user_month
    ON monthly_budget_totals (user_id, month_start);

CREATE INDEX IF NOT EXISTS ix_budgets_user_month
    ON budgets (user_id, month_start);

CREATE INDEX IF NOT EXISTS ix_budgets_user_month_category
    ON budgets (user_id, month_start, category_id);

CREATE OR REPLACE FUNCTION set_monthly_budget_totals_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_monthly_budget_totals_updated_at ON monthly_budget_totals;
CREATE TRIGGER trg_monthly_budget_totals_updated_at
BEFORE UPDATE ON monthly_budget_totals
FOR EACH ROW
EXECUTE FUNCTION set_monthly_budget_totals_updated_at();

CREATE OR REPLACE FUNCTION set_budgets_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_budgets_updated_at ON budgets;
CREATE TRIGGER trg_budgets_updated_at
BEFORE UPDATE ON budgets
FOR EACH ROW
EXECUTE FUNCTION set_budgets_updated_at();

COMMIT;
