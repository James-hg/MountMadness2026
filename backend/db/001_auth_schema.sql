-- Auth schema

BEGIN;

-- Needed for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Main users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- ID
    name VARCHAR(120) NOT NULL, -- name
    email VARCHAR(255) NOT NULL, -- email
    password_hash TEXT NOT NULL, -- pass
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW() -- time created
);

-- Case-insensitive unique email
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email_lower ON users ((LOWER(email)));

-- Refresh token/session storage
-- Store only token hash (never raw refresh JWT), plus jti for rotation/revocation.
CREATE TABLE IF NOT EXISTS auth_refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    jti UUID NOT NULL,
    token_hash TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    replaced_by_jti UUID,
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_auth_refresh_tokens_jti UNIQUE (jti)
);

CREATE INDEX IF NOT EXISTS ix_auth_refresh_tokens_user_id
    ON auth_refresh_tokens (user_id);

CREATE INDEX IF NOT EXISTS ix_auth_refresh_tokens_expires_at
    ON auth_refresh_tokens (expires_at);

CREATE INDEX IF NOT EXISTS ix_auth_refresh_tokens_user_active
    ON auth_refresh_tokens (user_id, revoked_at, expires_at);

-- Optional but strongly recommended for "forgot password"
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id
    ON password_reset_tokens (user_id);

COMMIT;
