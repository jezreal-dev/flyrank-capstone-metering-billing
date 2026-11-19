"""API routes for plans and Stripe Checkout integration."""
from typing import List
from fastapi import APIRouter, HTTPException
from app.models.schemas import (
    PlanResponse,
    CheckoutSessionRequest,
    CheckoutSessionResponse
)
from app.core.database import get_db_connection
from app.services.stripe_service import stripe_service

router = APIRouter(prefix="/api", tags=["billing"])

@router.get("/plans", response_model=List[PlanResponse])
def list_available_plans():
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM plans WHERE is_active = 1 ORDER BY price_cents ASC").fetchall()
        result = []
        for r in rows:
            result.append(
                PlanResponse(
                    id=r["id"],
                    name=r["name"],
                    api_quota=r["api_quota"],
                    token_quota=r["token_quota"],
                    price_cents=r["price_cents"],
                    price_usd_display=f"${r['price_cents'] / 100.0:.2f}/mo"
                )
            )
        return result

@router.post("/billing/checkout-session", response_model=CheckoutSessionResponse, status_code=201)
def create_checkout_session(payload: CheckoutSessionRequest):
    """Initiates a Stripe Checkout flow in test mode."""
    try:
        session = stripe_service.create_checkout_session(
            tenant_id=payload.tenant_id,
            plan_id=payload.plan_id,
            success_url=payload.success_url or "https://example.com/billing/success",
            cancel_url=payload.cancel_url or "https://example.com/billing/cancel"
        )
        return session
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
