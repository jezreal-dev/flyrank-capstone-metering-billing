"""Pydantic v2 schemas for tenants, metering, quotas, usage rollups, and Stripe billing."""
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator

class UsageTypeEnum(str, Enum):
    API_CALL = "api_call"
    AI_TOKENS = "ai_tokens"

class SubscriptionStatusEnum(str, Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    TRIALING = "trialing"

class TenantCreateRequest(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=2)
    email: str = Field(..., min_length=5)
    plan_id: str = Field(default="free")

class TenantResponse(BaseModel):
    id: str
    name: str
    email: str
    plan_id: str
    subscription_status: str
    created_at: str

class PlanResponse(BaseModel):
    id: str
    name: str
    api_quota: int
    token_quota: int
    price_cents: int
    price_usd_display: str

class MeterRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    usage_type: UsageTypeEnum
    quantity: int = Field(default=1, ge=1)
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: int, info) -> int:
        if v < 1:
            raise ValueError("Usage quantity must be at least 1")
        return v

class MeterResponse(BaseModel):
    event_id: str
    tenant_id: str
    usage_type: UsageTypeEnum
    quantity: int
    cost_microcents: int
    cost_usd_display: str
    is_idempotent_replay: bool = False
    recorded_at: str

class GenerateRequest(BaseModel):
    """Payload for the dummy billable AI generation endpoint."""
    tenant_id: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    # Simulated token counts (for predictable $0 testing & verification)
    simulated_input_tokens: int = Field(default=100, ge=0)
    simulated_cached_input_tokens: int = Field(default=0, ge=0)
    simulated_output_tokens: int = Field(default=50, ge=0)
    simulated_reasoning_tokens: int = Field(default=0, ge=0)

class GenerateResponse(BaseModel):
    tenant_id: str
    result_text: str
    tokens_billed: Dict[str, int]
    cost_microcents: int
    cost_usd_display: str
    meter_event_id: str

class QuotaMetric(BaseModel):
    used: int
    quota: int
    remaining: int
    percentage: float

class UsageRollupResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    plan_id: str
    plan_name: str
    subscription_status: SubscriptionStatusEnum
    billing_period: Dict[str, str]
    api_calls: QuotaMetric
    ai_tokens: QuotaMetric
    token_breakdown: Dict[str, int]
    cost: Dict[str, Any]

class CheckoutSessionRequest(BaseModel):
    tenant_id: str
    plan_id: str = Field(default="pro")
    success_url: Optional[str] = "https://example.com/billing/success"
    cancel_url: Optional[str] = "https://example.com/billing/cancel"

class CheckoutSessionResponse(BaseModel):
    session_id: str
    checkout_url: str
    tenant_id: str
    plan_id: str
    mode: str = "subscription"
    status: str = "open"

class WebhookResponse(BaseModel):
    status: str
    event_id: str
    event_type: str
    details: Optional[str] = None
