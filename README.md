# Mount Madness 2026

## Stack
- Backend: FastAPI
- Frontend: Dockerized static web app
- AI: Gemini API
- Database: PostgreSQL
- Runtime: Docker Compose

## Quick Start
1. Copy environment files:
   - `cp backend/.env.example backend/.env`
2. Set required values in `backend/.env`:
   - `GEMINI_API_KEY`
   - `DATABASE_URL`
   - `JWT_SECRET_KEY`
3. Start services:
   - `docker compose up --build`
4. Run DB migrations:
   - Recommended (all at once): `backend/db/000_run_all.sql`
   - Or manually in order:
     - `backend/db/001_auth_schema.sql`
     - `backend/db/002_categories_schema.sql`
     - `backend/db/003_transactions_schema.sql`
     - `backend/db/004_seed_dev_admin.sql`

## URLs
- Frontend: http://localhost:5173
- Backend health: http://localhost:8000/health
- FastAPI docs: http://localhost:8000/docs

## Notes
- Backend reads `GEMINI_API_KEY`, `DATABASE_URL`, and JWT settings from `backend/.env`.
- Transactions API endpoints:
  - `POST /transactions`
  - `GET /transactions`
  - `GET /transactions/{id}`
  - `PATCH /transactions/{id}`
  - `DELETE /transactions/{id}`
  - `GET /transactions/summary`
