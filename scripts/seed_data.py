"""Seeding script for plans, benchmark tenants, and initial usage events."""
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import init_db, get_db_connection

def seed_database():
    print("[1/3] Initializing SQLite tables and indexes...")
    init_db()

    print("[2/3] Seeding subscription plans (Free and Pro)...")
    plans = [
        {
            "id": "free",
            "name": "Free Tier",
            "api_quota": 1000,
            "token_quota": 100000,
            "price_cents": 0
        },
        {
            "id": "pro",
            "name": "Pro Tier",
            "api_quota": 50000,
            "token_quota": 10000000,
            "price_cents": 2900
        }
    ]

    with get_db_connection() as conn:
        for p in plans:
            conn.execute(
                """
                INSERT INTO plans (id, name, api_quota, token_quota, price_cents)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    api_quota = excluded.api_quota,
                    token_quota = excluded.token_quota,
                    price_cents = excluded.price_cents
                """,
                (p["id"], p["name"], p["api_quota"], p["token_quota"], p["price_cents"])
            )

        print("[3/3] Seeding test tenants and subscriptions...")
        tenants = [
            {
                "id": "tenant_alpha",
                "name": "Alpha Corp",
                "email": "billing@alpha-corp.io",
                "plan_id": "free",
                "status": "active"
            },
            {
                "id": "tenant_beta",
                "name": "Beta Labs",
                "email": "ops@beta-labs.ai",
                "plan_id": "pro",
                "status": "active"
            },
            {
                "id": "tenant_delinquent",
                "name": "Delinquent Ventures",
                "email": "finance@delinquent.org",
                "plan_id": "free",
                "status": "past_due"
            },
            {
                "id": "tenant_boundary",
                "name": "Boundary Test Org",
                "email": "qa@boundary-test.dev",
                "plan_id": "free",
                "status": "active"
            }
        ]

        for t in tenants:
            conn.execute(
                """
                INSERT INTO tenants (id, name, email)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    email = excluded.email
                """,
                (t["id"], t["name"], t["email"])
            )
            conn.execute(
                """
                INSERT INTO subscriptions (id, tenant_id, plan_id, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id) DO UPDATE SET
                    plan_id = excluded.plan_id,
                    status = excluded.status
                """,
                (f"sub_{t['id']}", t["id"], t["plan_id"], t["status"])
            )

        # Clear existing usage for fresh benchmark runs
        conn.execute("DELETE FROM usage_events WHERE tenant_id = 'tenant_boundary'")

        # Pre-seed tenant_boundary with exactly 999 API calls
        conn.execute(
            """
            INSERT INTO usage_events (
                id, tenant_id, usage_type, quantity, cost_microcents, idempotency_key
            )
            VALUES (?, 'tenant_boundary', 'api_call', 999, 0, 'seed_boundary_999')
            """,
            (f"evt_seed_{uuid.uuid4().hex[:10]}",)
        )
        conn.commit()

    print("Database seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
