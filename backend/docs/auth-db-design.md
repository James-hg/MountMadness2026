# Auth DB Design

## Scope

Simple auth foundation with:

- email/password login
- JWT access + refresh token flow
- minimal profile fields (`name`, `email`, `created_at`)

## Tables

### `users`

Required columns:

- `id` (UUID PK)
- `name`
- `email` (case-insensitive unique)
- `password_hash`
- `created_at`

### `auth_refresh_tokens`

Stores refresh session state for rotation/revocation.

Required columns:

- `id` (UUID PK)
- `user_id` (FK to users)
- `jti` (JWT ID, unique)
- `token_hash` (hash of raw refresh token)
- `expires_at`

Recommended columns:

- `revoked_at`
- `replaced_by_jti`
- `user_agent`
- `ip_address`
- `issued_at`

Why:

- Access tokens are stateless and usually not persisted.
- Refresh tokens must be revocable and rotatable, so they need DB state.

### `password_reset_tokens` (optional, recommended)

Supports secure password reset flow.

## JWT Strategy

### Access token (short-lived, e.g. 15 min)

Claims:

- `sub`: user UUID
- `type`: `access`
- `exp`, `iat`
- `jti`

### Refresh token (longer-lived, e.g. 7-30 days)

Claims:

- `sub`: user UUID
- `type`: `refresh`
- `exp`, `iat`
- `jti`

DB handling:

1. On login, issue both tokens.
2. Hash refresh token and store row in `auth_refresh_tokens`.
3. On refresh, verify JWT + lookup `jti` + compare hash.
4. Rotate: revoke old row, insert new row with new `jti`.
5. On logout, set `revoked_at`.

## Minimal API Contract (Auth)

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`

## Practical Defaults

- Password hashing: Argon2id (or Bcrypt).
- Lowercase email before save.
- Unique index on `LOWER(email)`.
- Use UTC (`TIMESTAMPTZ`).
- Cleanup job for expired refresh/reset tokens.

## Files in Repo

- SQL schema: `backend/db/001_auth_schema.sql`
