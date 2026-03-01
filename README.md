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
     - `backend/db/005_budget_limits_schema.sql`
     - `backend/db/006_smart_budget_allocation.sql`
     - `backend/db/007_reports_indexes.sql`

## URLs
- Frontend: http://localhost:5173
- Backend health: http://localhost:8000/health
- FastAPI docs: http://localhost:8000/docs

## Mobile Access
To access the app from your phone (same Wi-Fi network):
1. Find your local IP:
   ```
   ifconfig en0 | grep inet
   ```
   Look for the `inet` value (e.g. `192.168.1.42`)
2. Open on your phone: `http://<your-ip>:5173`

## Notes
- Backend reads `GEMINI_API_KEY`, `DATABASE_URL`, and JWT settings from `backend/.env`.
- Categories API endpoints:
  - `GET /api/categories` (optional query: `kind=income|expense`)
  - `POST /api/categories` (body: name, kind, optional icon/color)
  - `PUT /api/categories/{category_id}` (body: name?, icon?, color?)
  - `DELETE /api/categories/{category_id}`
- Transactions API endpoints:
  - `POST /transactions`
  - `GET /transactions`
  - `GET /transactions/{id}`
  - `PATCH /transactions/{id}`
  - `DELETE /transactions/{id}`
  - `GET /transactions/summary`
- Smart Budget API endpoints:
  - `POST /budget/total`
  - `GET /budget?month_start=YYYY-MM-01`
  - `PUT /budget/category`
- Reports API endpoints:
  - `GET /reports/summary?month=YYYY-MM`
  - `GET /reports/top-categories?month=YYYY-MM&limit=5`
  - `GET /reports/trends?months=6`
  - `GET /reports/monthly-breakdown?month=YYYY-MM`
- Reports amount outputs are decimal amount strings (`NUMERIC(12,2)` style).
- Reports design docs: `backend/docs/reports-api-design.md`
