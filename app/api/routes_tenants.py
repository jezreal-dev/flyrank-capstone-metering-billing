"""API routes for tenant management and registration."""
import uuid
from typing import List
from fastapi import APIRouter, HTTPException
from app.models.schemas import TenantCreateRequest, TenantResponse
from app.core.database import get_db_connection

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

@router.post("", response_model=TenantResponse, status_code=201)
def create_tenant(payload: TenantCreateRequest):
    tenant_id = payload.id or f"tenant_{uuid.uuid4().hex[:10]}"
    with get_db_connection() as conn:
        existing = conn.execute("SELECT id FROM tenants WHERE email = ?", (payload.email,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"Tenant with email '{payload.email}' already exists")

        plan = conn.execute("SELECT id FROM plans WHERE id = ?", (payload.plan_id,)).fetchone()
        if not plan:
            raise HTTPException(status_code=400, detail=f"Plan '{payload.plan_id}' does not exist")

        conn.execute(
            "INSERT INTO tenants (id, name, email) VALUES (?, ?, ?)",
            (tenant_id, payload.name, payload.email)
        )
        conn.execute(
            """
            INSERT INTO subscriptions (id, tenant_id, plan_id, status)
            VALUES (?, ?, ?, 'active')
            """,
            (f"sub_{uuid.uuid4().hex[:10]}", tenant_id, payload.plan_id)
        )
        conn.commit()

        row = conn.execute(
            """
            SELECT t.id, t.name, t.email, s.plan_id, s.status as subscription_status, t.created_at
            FROM tenants t
            JOIN subscriptions s ON t.id = s.tenant_id
            WHERE t.id = ?
            """,
            (tenant_id,)
        ).fetchone()

        return TenantResponse(**dict(row))

@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant_id: str):
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT t.id, t.name, t.email, s.plan_id, s.status as subscription_status, t.created_at
            FROM tenants t
            JOIN subscriptions s ON t.id = s.tenant_id
            WHERE t.id = ?
            """,
            (tenant_id,)
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Tenant with ID '{tenant_id}' not found")
        return TenantResponse(**dict(row))
