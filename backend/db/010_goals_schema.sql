-- Goals schema (NUMERIC amount model)

BEGIN;

CREATE TABLE IF NOT EXISTS goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    target_amount NUMERIC(12,2) NOT NULL,
    saved_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    deadline_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_goals_target_positive CHECK (target_amount > 0),
    CONSTRAINT chk_goals_saved_non_negative CHECK (saved_amount >= 0),
    CONSTRAINT chk_goals_saved_within_target CHECK (saved_amount <= target_amount),
    CONSTRAINT chk_goals_status CHECK (status IN ('active', 'paused', 'completed', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS ix_goals_user_status
    ON goals (user_id, status);

CREATE INDEX IF NOT EXISTS ix_goals_user_deadline
    ON goals (user_id, deadline_date);

CREATE OR REPLACE FUNCTION set_goals_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_goals_updated_at ON goals;
CREATE TRIGGER trg_goals_updated_at
BEFORE UPDATE ON goals
FOR EACH ROW
EXECUTE FUNCTION set_goals_updated_at();

COMMIT;
