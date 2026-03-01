-- Run all DB migrations in the correct order.
\ir 001_auth_schema.sql
\ir 002_categories_schema.sql
\ir 003_transactions_schema.sql
\ir 004_seed_dev_admin.sql
\ir 005_budget_limits_schema.sql
\ir 006_smart_budget_allocation.sql
\ir 007_reports_indexes.sql
\ir 008_fixed_and_recurring_schema.sql
