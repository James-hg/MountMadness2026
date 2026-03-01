"""Seed ~30 sample transactions for the dev admin user via the API."""

import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import psycopg

DATABASE_URL = os.environ.get("DATABASE_URL", "")
JWT_SECRET = "change-me"
API_BASE = "http://localhost:8000"

SAMPLE_TRANSACTIONS = [
    # Expenses (~20)
    {"type": "expense", "cat": "food", "amount": "12.50", "date": "2026-01-03", "merchant": "Trader Joe's", "note": "Weekly groceries"},
    {"type": "expense", "cat": "food", "amount": "8.75", "date": "2026-01-05", "merchant": "Chipotle", "note": "Lunch"},
    {"type": "expense", "cat": "housing_rent", "amount": "1200.00", "date": "2026-01-01", "merchant": "Apartment Complex", "note": "January rent"},
    {"type": "expense", "cat": "transport", "amount": "45.00", "date": "2026-01-07", "merchant": "Uber", "note": "Airport ride"},
    {"type": "expense", "cat": "food", "amount": "5.25", "date": "2026-01-10", "merchant": "Blue Bottle Coffee", "note": "Morning coffee"},
    {"type": "expense", "cat": "shopping", "amount": "89.99", "date": "2026-01-12", "merchant": "Amazon", "note": "Headphones"},
    {"type": "expense", "cat": "entertainment", "amount": "15.99", "date": "2026-01-14", "merchant": "Netflix", "note": "Monthly subscription"},
    {"type": "expense", "cat": "health", "amount": "49.99", "date": "2026-01-15", "merchant": "Gold's Gym", "note": "Monthly membership"},
    {"type": "expense", "cat": "food", "amount": "32.40", "date": "2026-01-18", "merchant": "Whole Foods", "note": "Groceries"},
    {"type": "expense", "cat": "transport", "amount": "3.50", "date": "2026-01-20", "merchant": "Metro Transit", "note": "Bus fare"},
    {"type": "expense", "cat": "food", "amount": "22.00", "date": "2026-01-22", "merchant": "Domino's Pizza", "note": "Friday dinner"},
    {"type": "expense", "cat": "tuition", "amount": "29.99", "date": "2026-01-25", "merchant": "Udemy", "note": "Python course"},
    {"type": "expense", "cat": "bills_utilities", "amount": "85.00", "date": "2026-02-01", "merchant": "Electric Company", "note": "Electric bill"},
    {"type": "expense", "cat": "housing_rent", "amount": "1200.00", "date": "2026-02-01", "merchant": "Apartment Complex", "note": "February rent"},
    {"type": "expense", "cat": "food", "amount": "14.30", "date": "2026-02-03", "merchant": "Starbucks", "note": "Coffee and pastry"},
    {"type": "expense", "cat": "shopping", "amount": "55.00", "date": "2026-02-07", "merchant": "Zara", "note": "New shirt"},
    {"type": "expense", "cat": "transport", "amount": "38.00", "date": "2026-02-10", "merchant": "Lyft", "note": "Ride to downtown"},
    {"type": "expense", "cat": "food", "amount": "67.80", "date": "2026-02-14", "merchant": "Olive Garden", "note": "Valentine's dinner"},
    {"type": "expense", "cat": "entertainment", "amount": "25.00", "date": "2026-02-16", "merchant": "AMC Theaters", "note": "Movie tickets"},
    {"type": "expense", "cat": "food", "amount": "9.50", "date": "2026-02-20", "merchant": "McDonald's", "note": "Quick lunch"},
    # Incomes (~10)
    {"type": "income", "cat": "part_time_job", "amount": "850.00", "date": "2026-01-15", "merchant": "Campus Bookstore", "note": "January paycheck"},
    {"type": "income", "cat": "allowance_transfer", "amount": "500.00", "date": "2026-01-01", "merchant": None, "note": "Monthly allowance from parents"},
    {"type": "income", "cat": "scholarship", "amount": "2000.00", "date": "2026-01-10", "merchant": "University", "note": "Spring semester scholarship"},
    {"type": "income", "cat": "part_time_job", "amount": "200.00", "date": "2026-01-20", "merchant": "Fiverr Client", "note": "Logo design project"},
    {"type": "income", "cat": "other_income", "amount": "50.00", "date": "2026-01-28", "merchant": None, "note": "Sold old textbooks"},
    {"type": "income", "cat": "part_time_job", "amount": "850.00", "date": "2026-02-15", "merchant": "Campus Bookstore", "note": "February paycheck"},
    {"type": "income", "cat": "allowance_transfer", "amount": "500.00", "date": "2026-02-01", "merchant": None, "note": "Monthly allowance from parents"},
    {"type": "income", "cat": "part_time_job", "amount": "350.00", "date": "2026-02-08", "merchant": "Upwork Client", "note": "Web scraping task"},
    {"type": "income", "cat": "other_income", "amount": "25.00", "date": "2026-02-18", "merchant": "Venmo", "note": "Refund from friend"},
    {"type": "income", "cat": "part_time_job", "amount": "425.00", "date": "2026-02-25", "merchant": "Campus Bookstore", "note": "Extra shift pay"},
]


def main():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL env var is not set")
        sys.exit(1)

    # Step 1: Connect to DB, fetch dev admin user ID and category slugs->IDs
    print("Connecting to database...")
    with psycopg.connect(DATABASE_URL, row_factory=psycopg.rows.dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email = 'devadmin@mountmadness.local'")
            row = cur.fetchone()
            if not row:
                print("ERROR: Dev admin user not found. Run migrations first.")
                sys.exit(1)
            user_id = str(row["id"])
            print(f"  Dev admin user ID: {user_id}")

            cur.execute("SELECT id, slug, kind FROM categories WHERE is_system = TRUE")
            categories = {r["slug"]: str(r["id"]) for r in cur.fetchall()}
            print(f"  Found {len(categories)} system categories")

    # Step 2: Generate JWT
    token = jwt.encode(
        {"sub": user_id, "type": "access", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        JWT_SECRET,
        algorithm="HS256",
    )
    print(f"  Generated JWT token")

    # Step 3: POST transactions via API
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    success = 0
    errors = 0

    for txn in SAMPLE_TRANSACTIONS:
        cat_id = categories.get(txn["cat"])
        if not cat_id:
            print(f"  SKIP: category '{txn['cat']}' not found")
            errors += 1
            continue

        payload = {
            "type": txn["type"],
            "amount": txn["amount"],
            "occurred_on": txn["date"],
            "category_id": cat_id,
            "merchant": txn["merchant"],
            "note": txn["note"],
        }

        resp = httpx.post(f"{API_BASE}/transactions", json=payload, headers=headers)
        if resp.status_code == 201:
            success += 1
            print(f"  OK: {txn['type']:7s} ${txn['amount']:>8s}  {txn.get('merchant') or '(no merchant)':20s}  {txn['date']}")
        else:
            errors += 1
            print(f"  FAIL ({resp.status_code}): {resp.text}")

    print(f"\nDone! {success} created, {errors} errors.")


if __name__ == "__main__":
    main()
