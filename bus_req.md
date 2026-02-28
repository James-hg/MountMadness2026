# Business Requirements (BRD-lite)

## Problem Statement

International students often receive money in large transfers (monthly or termly). They need a simple way to track spending, decide how much to save, and optionally invest without using complex budgeting apps.

## Target Users

- International students in Canada, the US, or Australia (location-flexible).
- Students who receive money in chunks (for example, monthly or per semester).
- Users who want quick tracking and a clear runway view ("how long will my money last?").

## Business Goals

- Users can quickly input income transfers and expenses.
- App displays current balance, monthly burn rate, and projected runway.
- Basic categorization works (manual and AI/rule-based).
- Receipt photo import reduces manual entry.

## Scope (Hackathon-Friendly)

### In Scope

- Track transfers (income), expenses, and categories.
- Budgets as optional.
- Insights: monthly summary, category breakdown, and runway.
- Receipt upload with best-effort parsing for amount, date, and merchant.

### Out of Scope (for MVP)

- Advanced investment planning.
- Enterprise-grade compliance and auditing.

## Non-Functional Requirements

- Works on laptop and mobile browser.
- Fast entry flow: add an expense in under 20 seconds.
- Auth: simple email/password (or magic link).
- Security: hashed passwords and no raw API keys in frontend code.
- Reliability: partial receipt parsing is allowed; user can edit before saving.
