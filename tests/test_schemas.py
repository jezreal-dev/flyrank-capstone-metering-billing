"""Tests for boundary schemas and validation models."""
import pytest
from pydantic import ValidationError
from app.models.schemas import (
    MeterRequest,
    TenantCreateRequest,
    UsageTypeEnum,
    CheckoutSessionRequest
)

def test_meter_request_valid():
    req = MeterRequest(
        tenant_id="tenant_123",
        usage_type=UsageTypeEnum.API_CALL,
        quantity=5
    )
    assert req.tenant_id == "tenant_123"
    assert req.usage_type == UsageTypeEnum.API_CALL
    assert req.quantity == 5

def test_meter_request_invalid_quantity():
    with pytest.raises(ValidationError):
        MeterRequest(
            tenant_id="tenant_123",
            usage_type=UsageTypeEnum.API_CALL,
            quantity=0  # ge=1 required
        )

def test_meter_request_negative_tokens():
    with pytest.raises(ValidationError):
        MeterRequest(
            tenant_id="tenant_123",
            usage_type=UsageTypeEnum.AI_TOKENS,
            quantity=10,
            input_tokens=-1
        )

def test_tenant_create_request_validation():
    req = TenantCreateRequest(
        name="Acme Corp",
        email="dev@acme.org",
        plan_id="free"
    )
    assert req.name == "Acme Corp"
    assert req.plan_id == "free"

    with pytest.raises(ValidationError):
        TenantCreateRequest(name="A", email="dev@acme.org")  # name min_length=2
