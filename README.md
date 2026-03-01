<p align="center">
  <img src="Webpage_image/MountainFinance.PNG" alt="Mountain Finance Logo" width="200"/>
</p>

<h1 align="center">Mountain Finance</h1>

<p align="center">
  A smart personal finance tracker built for international students — track spending, set budgets, import receipts with AI, and see how long your money will last.
</p>

---

## Screenshots

| Login | Sign Up | Dashboard |
|:---:|:---:|:---:|
| ![Login](Webpage_image/Login.png) | ![Sign Up](Webpage_image/Signin.png) | ![Dashboard](Webpage_image/Mainpage.png) |

---

## Features

- **Dashboard** — Income vs. expense line charts (1W / 1M / 3M / 6M / 12M), budget health progress bars, and AI-generated insight cards (info, warning, danger severity)
- **Transactions** — Full CRUD with filtering by category, date range, amount range, and type; sorting and pagination
- **AI Receipt & Statement Import** — Upload a receipt photo or bank statement PDF/image; Gemini extracts transactions automatically for review before saving
- **Smart Budgeting** — Set a monthly total and auto-allocate across categories; override per-category limits; toggle between $ and % views
- **Savings Goals** — Create goals with target amounts and deadlines; track progress %, recommended monthly savings, and on-track status
- **Monthly Reports** — Doughnut chart (top spending categories), line chart (multi-month trends), bar chart (daily breakdown)
- **AI Financial Assistant** — Floating chatbot on every page with 11 tools: create transactions, suggest/apply budgets, detect spending anomalies, project future balances, estimate runway, and more
- **Goals Chatbot** — Dedicated savings-focused AI assistant with confirmation flow for write actions
- **Calendar View** — Monthly calendar with per-day cashflow indicators
- **Recurring Transactions** — Define weekly, biweekly, or monthly rules and auto-generate entries
- **Secure Auth** — JWT with 15-min access tokens, 7-day refresh tokens (rotation + revocation), bcrypt password hashing

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, React Router v6, Chart.js 4 + react-chartjs-2 |
| Backend | FastAPI 0.116.1, Python 3.12, Uvicorn |
| Database | PostgreSQL with pgcrypto extension |
| AI | Google Gemini 2.5 Pro (REST via httpx) |
| Auth | PyJWT (HS256), bcrypt via pgcrypto |
| Infrastructure | Docker Compose, Nginx (Alpine) |

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- A PostgreSQL instance (external — not included in compose)
- A [Google Gemini API key](https://ai.google.dev/)

### Setup

1. **Clone and configure environment:**
   ```bash
   git clone <repo-url>
   cd MountMadness2026
   cp backend/.env.example backend/.env
   ```

2. **Edit `backend/.env`** with your values:
   ```env
   GEMINI_API_KEY=your-gemini-key
   DATABASE_URL=postgresql://user:pass@host:5432/dbname
   JWT_SECRET_KEY=your-secret-key
   ```

3. **Start services:**
   ```bash
   docker compose up --build
   ```

4. **Run database migrations** (against your PostgreSQL instance):
   ```bash
   # All at once (recommended):
   psql $DATABASE_URL -f backend/db/000_run_all.sql

   # Or manually in order:
   psql $DATABASE_URL -f backend/db/001_auth_schema.sql
   psql $DATABASE_URL -f backend/db/002_categories_schema.sql
   psql $DATABASE_URL -f backend/db/003_transactions_schema.sql
   psql $DATABASE_URL -f backend/db/004_seed_dev_admin.sql
   psql $DATABASE_URL -f backend/db/005_budget_limits_schema.sql
   psql $DATABASE_URL -f backend/db/006_smart_budget_allocation.sql
   psql $DATABASE_URL -f backend/db/007_reports_indexes.sql
   psql $DATABASE_URL -f backend/db/008_fixed_and_recurring_schema.sql
   psql $DATABASE_URL -f backend/db/009_ai_conversation_memory.sql
   psql $DATABASE_URL -f backend/db/010_goals_schema.sql
   ```

### Access

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Interactive API Docs | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |

---

## Mobile Access

To access from your phone on the same Wi-Fi network:

1. Find your computer's local IP:
   - **macOS:** `ifconfig en0 | grep inet`
   - **Windows (WSL2):** `ipconfig.exe` → look for Wi-Fi adapter IPv4 address

2. Open `http://<your-ip>:5173` on your phone's browser.

---

## API Overview

### Auth (`/auth`)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Sign up (returns access + refresh tokens) |
| POST | `/auth/login` | Log in |
| POST | `/auth/refresh` | Rotate refresh token |
| POST | `/auth/logout` | Revoke refresh token |
| GET | `/auth/me` | Get current user |
| PATCH | `/auth/me` | Update name/email |
| POST | `/auth/change-password` | Change password |

### Transactions (`/transactions`)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/transactions` | Create transaction |
| POST | `/transactions/bulk` | Bulk create (statement import) |
| POST | `/transactions/upload` | Upload receipt → AI extraction |
| POST | `/transactions/upload-statement` | Upload bank statement → AI extraction |
| GET | `/transactions` | List with filters, sorting, pagination |
| GET | `/transactions/summary` | Burn rate, runway, totals |
| GET | `/transactions/{id}` | Get single transaction |
| PATCH | `/transactions/{id}` | Update transaction |
| DELETE | `/transactions/{id}` | Soft-delete transaction |

### Budget (`/budget`)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/budget/total` | Set monthly total + auto-allocate |
| GET | `/budget?month_start=YYYY-MM-01` | Get budget with spent/remaining per category |
| PUT | `/budget/category` | Override a single category limit |

### Categories (`/categories`)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/categories` | List all (system + user); optional `?kind=income\|expense` |
| POST | `/categories` | Create user category |
| PUT | `/categories/{id}` | Update user category |
| DELETE | `/categories/{id}` | Delete user category |

### Reports (`/reports`)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/reports/summary?month=YYYY-MM` | Monthly balance, spend, burn rate, runway |
| GET | `/reports/top-categories?month=YYYY-MM&limit=5` | Top N spending categories |
| GET | `/reports/trends?months=6` | N-month income/expense trends |
| GET | `/reports/monthly-breakdown?month=YYYY-MM` | Daily expense breakdown |

### Dashboard (`/dashboard`)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/dashboard/insights` | Budget health + smart insight cards |

### Goals (`/goals`)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/goals` | Create savings goal |
| GET | `/goals` | List goals (filter by status) |
| GET | `/goals/{id}` | Get goal with computed fields |
| PATCH | `/goals/{id}` | Update goal |
| DELETE | `/goals/{id}` | Delete goal |
| POST | `/goals/chat` | Goals-focused chatbot |

### Recurring Rules (`/recurring-rules`)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/recurring-rules` | Create rule (weekly/biweekly/monthly) |
| GET | `/recurring-rules` | List rules |
| GET | `/recurring-rules/{id}` | Get single rule |
| PATCH | `/recurring-rules/{id}` | Update rule |
| DELETE | `/recurring-rules/{id}` | Deactivate rule |
| POST | `/recurring-rules/generate` | Generate overdue transactions |

### AI (`/ai`)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/ai/chat` | Financial assistant with multi-round tool calling |

---

## Project Structure

```
MountMadness2026/
├── frontend/
│   ├── src/
│   │   ├── App.js                 # Routing & AuthProvider
│   │   ├── api.js                 # API client with JWT auth
│   │   ├── context/AuthContext.js # Auth state management
│   │   ├── components/
│   │   │   ├── Dashboard.js       # Main dashboard
│   │   │   ├── FinancialChart.js  # Charts & insight cards
│   │   │   ├── TransactionsPage.js
│   │   │   ├── BudgetPage.js
│   │   │   ├── ReportsPage.js
│   │   │   ├── GoalsPage.js
│   │   │   ├── StatementUploadPage.js
│   │   │   ├── CategoriesPage.js
│   │   │   ├── SettingsPage.js
│   │   │   ├── CalendarPage.js
│   │   │   ├── ChatWidget.js      # Floating AI chatbot
│   │   │   ├── NavBar.js
│   │   │   └── ...
│   │   └── services/              # API clients for chat & goals
│   ├── public/
│   ├── nginx.conf
│   └── Dockerfile
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app & lifespan
│   │   ├── config.py              # Settings from .env
│   │   ├── database.py            # Async connection pool
│   │   ├── auth.py                # JWT auth endpoints
│   │   ├── transactions.py
│   │   ├── budget.py
│   │   ├── categories.py
│   │   ├── reports.py
│   │   ├── dashboard.py
│   │   ├── goals.py
│   │   ├── recurring.py
│   │   ├── ai/
│   │   │   ├── router.py          # /ai/chat endpoint
│   │   │   ├── gemini_client.py   # Gemini API client
│   │   │   ├── tools.py           # 11 AI tool definitions
│   │   │   ├── prompt.py          # System prompt builder
│   │   │   └── memory.py          # Conversation memory
│   │   └── services/              # Business logic layer
│   ├── db/                        # SQL migrations (001–010)
│   ├── docs/                      # Design documentation
│   ├── requirements.txt
│   └── Dockerfile
├── Webpage_image/                 # Screenshots & logo
├── docs/                          # Business requirements & MVP spec
├── docker-compose.yml
└── README.md
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes | — | Google Gemini API key |
| `GEMINI_MODEL` | No | `gemini-2.5-pro` | Gemini model to use |
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Yes | — | Secret for signing JWTs |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |

---

## Team

| Member | Areas |
|---|---|
| **James** | Dashboard |
| **Jeehoon** | Transactions, Budget |
| **Mason** | Reports, Settings |
| **Haki** | Import, AI Receipt/PDF Extraction |
