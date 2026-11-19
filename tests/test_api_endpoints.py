"""End-to-end HTTP boundary and API endpoint integration tests."""
import json
import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.stripe_security import generate_stripe_signature_header
from app.services.stripe_service import stripe_service

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"

def test_plans_endpoint(client):
    res = client.get("/api/plans")
    assert res.status_code == 200
    plans = res.json()
    assert len(plans) >= 2
    assert any(p["id"] == "free" for p in plans)
    assert any(p["id"] == "pro" for p in plans)

def test_boundary_validation_422_on_missing_fields(client):
    # Missing tenant_id & usage_type
    res = client.post("/api/meter", json={"quantity": 5}, headers={"Idempotency-Key": "test-key"})
    assert res.status_code == 422
    assert res.json()["error"] == "Validation Error"

def test_missing_idempotency_header_rejected(client):
    res = client.post("/api/meter", json={"tenant_id": "tenant_beta", "usage_type": "api_call", "quantity": 1})
    assert res.status_code == 422  # Header required

def test_generate_billable_endpoint(client):
    key = f"key_gen_{uuid.uuid4().hex[:8]}"
    res = client.post(
        "/api/generate",
        json={
            "tenant_id": "tenant_beta",
            "prompt": "Hello AI billing engine",
            "simulated_input_tokens": 500,
            "simulated_cached_input_tokens": 200,
            "simulated_output_tokens": 100,
            "simulated_reasoning_tokens": 50
        },
        headers={"Idempotency-Key": key}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["tenant_id"] == "tenant_beta"
    assert "cost_microcents" in data
    assert "meter_event_id" in data

def test_get_usage_rollup_endpoint(client):
    res = client.get("/api/usage?tenant_id=tenant_beta")
    assert res.status_code == 200
    rollup = res.json()
    assert rollup["tenant_id"] == "tenant_beta"
    assert "api_calls" in rollup
    assert "ai_tokens" in rollup
    assert "cost" in rollup

def test_checkout_session_creation(client):
    res = client.post(
        "/api/billing/checkout-session",
        json={"tenant_id": "tenant_alpha", "plan_id": "pro"}
    )
    assert res.status_code == 201
    data = res.json()
    assert "checkout_url" in data
    assert data["plan_id"] == "pro"

def test_forged_webhook_rejected_with_400(client):
    payload = json.dumps({"id": "evt_forged", "type": "ping"}).encode("utf-8")
    res = client.post(
        "/api/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": "t=1000,v1=fake_signature"}
    )
    assert res.status_code == 400
