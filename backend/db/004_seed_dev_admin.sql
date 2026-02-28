-- Seed one dev admin account for local/dev environments.
-- Do not use these credentials in production.

BEGIN;

-- Ensure pgcrypto is available for crypt()/gen_salt().
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF to_regclass('public.users') IS NULL THEN
        RAISE EXCEPTION 'users table does not exist. Run 001_auth_schema.sql first.';
    END IF;
END;
$$;

INSERT INTO users (name, email, password_hash, created_at)
SELECT
    'Dev Admin',
    'devadmin@mountmadness.local',
    crypt('DevAdmin123!', gen_salt('bf', 12)),
    NOW()
WHERE NOT EXISTS (
    SELECT 1
    FROM users
    WHERE LOWER(email) = LOWER('devadmin@mountmadness.local')
);

COMMIT;
