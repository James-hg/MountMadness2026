-- Transactions schema

BEGIN;

-- main transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- id
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, -- foreign user id
    category_id UUID NOT NULL REFERENCES categories(id), -- foreign category id
    type VARCHAR(20) NOT NULL, -- expense | income
    amount NUMERIC(12,2) NOT NULL, -- actual transaction amount (fixed currency)
    occurred_on DATE NOT NULL, -- actual transaction date
    merchant VARCHAR(160), -- company name/payee
    note TEXT, -- optional note
    -- dates of this instance
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,

    CONSTRAINT chk_transactions_type CHECK (type IN ('expense', 'income')),
    CONSTRAINT chk_transactions_amount_positive CHECK (amount > 0)
);

CREATE INDEX IF NOT EXISTS ix_transactions_user_date
    ON transactions (user_id, occurred_on DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_transactions_user_category_date
    ON transactions (user_id, category_id, occurred_on DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_transactions_user_type_date
    ON transactions (user_id, type, occurred_on DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_transactions_user_created
    ON transactions (user_id, created_at DESC);

CREATE OR REPLACE FUNCTION set_transactions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_transactions_updated_at ON transactions;
CREATE TRIGGER trg_transactions_updated_at
BEFORE UPDATE ON transactions
FOR EACH ROW
EXECUTE FUNCTION set_transactions_updated_at();

COMMIT;
