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
     - `backend/db/009_ai_conversation_memory.sql`

## URLs
- Frontend: http://localhost:5173
- Backend health: http://localhost:8000/health
- FastAPI docs: http://localhost:8000/docs

## Mobile Access
To access the app from your phone (same Wi-Fi network):
1.  Find your computer's local IP address.
    *   **On macOS:** Run `ifconfig en0 | grep inet` and find the `inet` value.
    *   **On Windows (with WSL2):** Run `ipconfig.exe` in your WSL terminal. Look for the "Wireless LAN adapter Wi-Fi" section and find the `IPv4 Address`.

    Example for Windows/WSL2:
    ```
    Wireless LAN adapter Wi-Fi:
       ...
       IPv4 Address. . . . . . . . . . . : 192.168.1.42  <-- This is the IP to use
    ```
2.  Open Safari on your phone and go to `http://<your-ip>:5173` (e.g., `http://192.168.1.42:5173`).

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
- AI Assistant API endpoint:
  - `POST /ai/chat` (body: `message`, optional `conversation_id`)
- Reports amount outputs are decimal amount strings (`NUMERIC(12,2)` style).
- Reports design docs: `backend/docs/reports-api-design.md`
- AI assistant docs: `backend/docs/ai-assistant-agent.md`
