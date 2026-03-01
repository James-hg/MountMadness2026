-- Categories schema

BEGIN;

CREATE TABLE IF NOT EXISTS categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- id
    user_id UUID REFERENCES users(id) ON DELETE CASCADE, -- foreign user id
    name VARCHAR(80) NOT NULL, -- category name
    slug VARCHAR(80) NOT NULL, -- category name (lowercase)
    kind VARCHAR(20) NOT NULL DEFAULT 'expense', -- expense | income
    icon VARCHAR(40), -- choose icon later
    color VARCHAR(20), -- for visualize
    is_system BOOLEAN NOT NULL DEFAULT FALSE, -- is default categories (food, rent, ...) | otherwise user-defined categories
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_categories_kind CHECK (kind IN ('expense', 'income')),
    CONSTRAINT chk_categories_slug CHECK (slug ~ '^[a-z0-9_]+$')
);

-- Uniqueness:
-- 1) System categories (user_id IS NULL) unique by (kind, slug)
-- 2) User categories unique by (user_id, kind, slug)
CREATE UNIQUE INDEX IF NOT EXISTS ux_categories_system_kind_slug
    ON categories (kind, slug)
    WHERE user_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_categories_user_kind_slug
    ON categories (user_id, kind, slug)
    WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_categories_user_id
    ON categories (user_id);

CREATE INDEX IF NOT EXISTS ix_categories_kind
    ON categories (kind);

-- Seed default expense categories (system-wide)
INSERT INTO categories (user_id, name, slug, kind, is_system)
VALUES
    (NULL, 'Food', 'food', 'expense', TRUE),
    (NULL, 'Housing / Rent', 'housing_rent', 'expense', TRUE),
    (NULL, 'Transport', 'transport', 'expense', TRUE),
    (NULL, 'Insurance', 'insurance', 'expense', TRUE),
    (NULL, 'Tuition', 'tuition', 'expense', TRUE),
    (NULL, 'Bills / Utilities', 'bills_utilities', 'expense', TRUE),
    (NULL, 'Shopping', 'shopping', 'expense', TRUE),
    (NULL, 'Entertainment', 'entertainment', 'expense', TRUE),
    (NULL, 'Health', 'health', 'expense', TRUE),
    (NULL, 'Other', 'other', 'expense', TRUE)
ON CONFLICT DO NOTHING;

-- Seed default income categories (recommended minimal set)
INSERT INTO categories (user_id, name, slug, kind, is_system)
VALUES
    (NULL, 'Allowance / Transfer', 'allowance_transfer', 'income', TRUE),
    (NULL, 'Part-time Job', 'part_time_job', 'income', TRUE),
    (NULL, 'Scholarship', 'scholarship', 'income', TRUE),
    (NULL, 'Refund', 'refund', 'income', TRUE),
    (NULL, 'Other Income', 'other_income', 'income', TRUE)
ON CONFLICT DO NOTHING;

COMMIT;
