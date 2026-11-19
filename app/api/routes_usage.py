"""API route for tenant monthly usage rollups and limits."""
from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import UsageRollupResponse
from app.services.rollup_service import rollup_service

router = APIRouter(prefix="/api/usage", tags=["usage"])

@router.get("", response_model=UsageRollupResponse)
def get_usage_rollup(tenant_id: str = Query(..., description="Tenant ID to inspect")):
    """Aggregates monthly usage events into an overview:
    used, limit, cost, and plan status.
    """
    try:
        return rollup_service.get_tenant_usage_rollup(tenant_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
