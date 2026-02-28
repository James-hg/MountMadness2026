# MVP Definition (Must Ship in 24 Hours)

## MVP Features (Priority Order)

### 1. Auth and Onboarding

- Sign up and login.
- Select currency (or default to CAD).

### 2. Manual Transaction Logging

- Add expense/income with:
  - amount
  - date
  - category
  - note
- View transaction list.

### 3. Categorization

- Start with hard-coded rules (merchant keywords to category).
- Allow user to override category.

### 4. Dashboard (Core Value)

- Current balance = total income - total expense.
- This month spend + top categories.
- Burn rate (daily/weekly/monthly average).
- Runway estimate = balance / average monthly spend.

## Definition of Done

A new user can:

1. Sign up.
2. Add an income transfer.
3. Add expenses.
4. See dashboard values update correctly.
5. Edit and delete transactions.

## Open Implementation Notes

- Define standard response codes for each POST/GET endpoint.
- Finalize database schema.
- Finalize category separation strategy.
