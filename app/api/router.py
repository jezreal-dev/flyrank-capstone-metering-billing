"""Central API router assembling modular billing and metering endpoints."""
from fastapi import APIRouter
from app.api.routes_meter import router as meter_router
from app.api.routes_usage import router as usage_router
from app.api.routes_billing import router as billing_router
from app.api.routes_webhooks import router as webhooks_router
from app.api.routes_tenants import router as tenants_router

api_router = APIRouter()
api_router.include_router(meter_router)
api_router.include_router(usage_router)
api_router.include_router(billing_router)
api_router.include_router(webhooks_router)
api_router.include_router(tenants_router)
