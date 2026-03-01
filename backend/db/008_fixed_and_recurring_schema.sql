BEGIN;

-- Which categories a user considers "fixed" (rent, insurance, etc.)
-- Per-user setting, not per-month.
CREATE TABLE IF NOT EXISTS user_fixed_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_user_fixed_categories UNIQUE (user_id, category_id)
);

CREATE INDEX IF NOT EXISTS ix_user_fixed_categories_user
    ON user_fixed_categories (user_id);

-- Recurring transaction templates.
CREATE TABLE IF NOT EXISTS recurring_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES categories(id),
    type VARCHAR(20) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    merchant VARCHAR(160),
    note TEXT,
    frequency VARCHAR(20) NOT NULL,
    anchor_date DATE NOT NULL,
    next_due_date DATE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_recurring_rules_type CHECK (type IN ('expense', 'income')),
    CONSTRAINT chk_recurring_rules_amount CHECK (amount > 0),
    CONSTRAINT chk_recurring_rules_frequency CHECK (frequency IN ('monthly', 'biweekly', 'weekly'))
);

CREATE INDEX IF NOT EXISTS ix_recurring_rules_user
    ON recurring_rules (user_id)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS ix_recurring_rules_next_due
    ON recurring_rules (next_due_date, is_active)
    WHERE is_active = TRUE;

-- Link generated transactions back to their recurring rule.
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS recurring_rule_id UUID REFERENCES recurring_rules(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_transactions_recurring_rule
    ON transactions (recurring_rule_id)
    WHERE recurring_rule_id IS NOT NULL;

-- Auto-update updated_at on recurring_rules.
CREATE OR REPLACE FUNCTION set_recurring_rules_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_recurring_rules_updated_at ON recurring_rules;
CREATE TRIGGER trg_recurring_rules_updated_at
BEFORE UPDATE ON recurring_rules
FOR EACH ROW
EXECUTE FUNCTION set_recurring_rules_updated_at();

COMMIT;
