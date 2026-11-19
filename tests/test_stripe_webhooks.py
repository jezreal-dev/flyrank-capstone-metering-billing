"""Tests for Stripe cryptographic signature verification and event deduplication."""
import json
import uuid
import pytest
from app.services.stripe_service import stripe_service
from app.core.stripe_security import (
    generate_stripe_signature_header,
    StripeSignatureVerificationError
)

def test_forged_signature_fails_verification():
    payload = json.dumps({"id": "evt_test", "type": "ping"}).encode("utf-8")
    with pytest.raises(StripeSignatureVerificationError):
        stripe_service.process_webhook_event(payload, "t=1614553200,v1=bad_signature_12345")

def test_legitimate_webhook_processing():
    event_id = f"evt_valid_{uuid.uuid4().hex[:10]}"
    payload = {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_123",
                "client_reference_id": "tenant_alpha",
                "metadata": {"tenant_id": "tenant_alpha", "plan_id": "pro"}
            }
        }
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = generate_stripe_signature_header(raw, stripe_service.webhook_secret)

    res = stripe_service.process_webhook_event(raw, sig)
    assert res.status == "processed"
    assert res.event_id == event_id

def test_replayed_webhook_event_is_deduplicated():
    event_id = f"evt_replay_{uuid.uuid4().hex[:10]}"
    payload = {
        "id": event_id,
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_123", "status": "active"}}
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = generate_stripe_signature_header(raw, stripe_service.webhook_secret)

    # Delivery 1: Processed
    res1 = stripe_service.process_webhook_event(raw, sig)
    assert res1.status == "processed"

    # Delivery 2: Already processed
    res2 = stripe_service.process_webhook_event(raw, sig)
    assert res2.status == "already_processed"
