"""Evaluator Acceptance Probes verification script (Section 12 Layer 2).
Automates the exact behavioral probes required by the FlyRank Evaluator.
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import get_db_connection
from app.services.meter_service import meter_service
from app.services.quota_service import QuotaExceededException
from app.services.rollup_service import rollup_service
from app.services.stripe_service import stripe_service
from app.core.stripe_security import (
    generate_stripe_signature_header,
    StripeSignatureVerificationError
)
from app.core.money_math import (
    compute_token_cost_microcents,
    DEFAULT_INPUT_RATE_MICROCENTS_PER_M,
    DEFAULT_CACHED_INPUT_RATE_MICROCENTS_PER_M,
    DEFAULT_OUTPUT_RATE_MICROCENTS_PER_M
)
from app.models.schemas import UsageTypeEnum

def probe_1_idempotency():
    print("--- [PROBE 1] Exactly-Once Metering & Idempotency Key Replay ---")
    tenant_id = "tenant_alpha"
    idempotency_key = f"key_probe1_{uuid.uuid4().hex[:8]}"

    # Request 1
    resp1 = meter_service.record_usage(
        tenant_id=tenant_id,
        usage_type=UsageTypeEnum.API_CALL,
        quantity=5,
        idempotency_key=idempotency_key
    )
    print(f"Request 1 Status: recorded event '{resp1.event_id}', replay={resp1.is_idempotent_replay}")

    # Request 2 (Exact duplicate retry with same Idempotency-Key)
    resp2 = meter_service.record_usage(
        tenant_id=tenant_id,
        usage_type=UsageTypeEnum.API_CALL,
        quantity=5,
        idempotency_key=idempotency_key
    )
    print(f"Request 2 Status: recorded event '{resp2.event_id}', replay={resp2.is_idempotent_replay}")

    assert resp1.event_id == resp2.event_id, "Idempotent replay must return original event_id"
    assert resp2.is_idempotent_replay is True, "Second call must flag is_idempotent_replay = True"

    # Query DB directly to verify no duplicate rows exist
    with get_db_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) as c FROM usage_events WHERE idempotency_key = ?",
            (idempotency_key,)
        ).fetchone()["c"]

    print(f"Database row count for idempotency_key '{idempotency_key}': {count}")
    assert count == 1, f"Expected exactly 1 database row, found {count}"
    print("PROBE 1: PASSED (Duplicate call mirrored original response with zero double-counting)\n")

def probe_2_quota_boundaries():
    print("--- [PROBE 2] Quota Boundaries & 429/402 Enforcement ---")
    tenant_id = "tenant_boundary"

    # Reset boundary test tenant to Free plan and exactly 999 used
    with get_db_connection() as conn:
        conn.execute("UPDATE subscriptions SET plan_id = 'free', status = 'active' WHERE tenant_id = ?", (tenant_id,))
        conn.execute("DELETE FROM usage_events WHERE tenant_id = ?", (tenant_id,))
        conn.execute(
            """
            INSERT INTO usage_events (id, tenant_id, usage_type, quantity, cost_microcents, idempotency_key)
            VALUES ('evt_reset_999', ?, 'api_call', 999, 0, 'key_reset_999')
            """,
            (tenant_id,)
        )
        conn.commit()

    # Pre-condition: tenant_boundary has 999 used of 1,000 quota
    rollup_before = rollup_service.get_tenant_usage_rollup(tenant_id)
    print(f"Initial State: {rollup_before.api_calls.used} / {rollup_before.api_calls.quota} used")
    assert rollup_before.api_calls.used == 999, "Expected 999 initial used calls"

    # Boundary call: 1,000th call (requested = 1) -> MUST SUCCEED (current 999 + 1 <= 1000)
    boundary_key = f"key_boundary_{uuid.uuid4().hex[:8]}"
    resp_boundary = meter_service.record_usage(
        tenant_id=tenant_id,
        usage_type=UsageTypeEnum.API_CALL,
        quantity=1,
        idempotency_key=boundary_key
    )
    print(f"Call #1,000 Result: SUCCEEDED (event_id={resp_boundary.event_id})")

    # Post-boundary call: 1,001st call -> MUST TRIGGER 429
    breach_key = f"key_breach_{uuid.uuid4().hex[:8]}"
    triggered_429 = False
    try:
        meter_service.record_usage(
            tenant_id=tenant_id,
            usage_type=UsageTypeEnum.API_CALL,
            quantity=1,
            idempotency_key=breach_key
        )
    except QuotaExceededException as qe:
        print(f"Call #1,001 Result: REJECTED with HTTP {qe.status_code}")
        print(f"Explanation: '{qe.message}' (Retry-After: {qe.retry_after}s)")
        assert qe.status_code == 429, f"Expected 429, got {qe.status_code}"
        triggered_429 = True

    assert triggered_429 is True, "Expected 1,001st call to trigger 429 QuotaExceededException"

    # Also test delinquent account triggers 402 Payment Required
    triggered_402 = False
    try:
        meter_service.record_usage(
            tenant_id="tenant_delinquent",
            usage_type=UsageTypeEnum.API_CALL,
            quantity=1,
            idempotency_key=f"key_delinq_{uuid.uuid4().hex[:8]}"
        )
    except QuotaExceededException as qe:
        print(f"Delinquent Tenant Result: REJECTED with HTTP {qe.status_code} ('{qe.message}')")
        assert qe.status_code == 402, f"Expected 402, got {qe.status_code}"
        triggered_402 = True

    assert triggered_402 is True, "Expected delinquent tenant to trigger 402 Payment Required"
    print("PROBE 2: PASSED (Exact boundary succeeded; overflow returned 429; delinquent returned 402)\n")

def probe_3_stripe_checkout_flip():
    print("--- [PROBE 3] Stripe Test Checkout & Webhook Plan Upgrade (Free -> Pro) ---")
    tenant_id = "tenant_alpha"

    # Reset tenant_alpha to Free plan
    with get_db_connection() as conn:
        conn.execute("UPDATE subscriptions SET plan_id = 'free', status = 'active' WHERE tenant_id = ?", (tenant_id,))
        conn.commit()

    # 1. Verify initially on Free plan (1,000 API calls, 100k tokens)
    rollup_before = rollup_service.get_tenant_usage_rollup(tenant_id)
    print(f"Pre-Webhook Plan: '{rollup_before.plan_name}' (Quotas: {rollup_before.api_calls.quota:,} calls, {rollup_before.ai_tokens.quota:,} tokens)")
    assert rollup_before.plan_id == "free", "Expected initial plan to be 'free'"

    # 2. Simulate signed Stripe 'checkout.session.completed' webhook event
    event_id = f"evt_stripe_test_{uuid.uuid4().hex[:12]}"
    webhook_payload = {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_test_{uuid.uuid4().hex[:10]}",
                "customer": f"cus_test_{uuid.uuid4().hex[:10]}",
                "subscription": f"sub_test_{uuid.uuid4().hex[:10]}",
                "client_reference_id": tenant_id,
                "metadata": {"tenant_id": tenant_id, "plan_id": "pro"}
            }
        }
    }
    payload_bytes = json.dumps(webhook_payload).encode("utf-8")
    sig_header = generate_stripe_signature_header(payload_bytes, stripe_service.webhook_secret)

    # 3. Process webhook
    wh_resp = stripe_service.process_webhook_event(payload_bytes, sig_header)
    print(f"Webhook Execution: status='{wh_resp.status}', details='{wh_resp.details}'")
    assert wh_resp.status == "processed", "Expected webhook status to be 'processed'"

    # 4. Inspect GET /usage to verify new Pro limits
    rollup_after = rollup_service.get_tenant_usage_rollup(tenant_id)
    print(f"Post-Webhook Plan: '{rollup_after.plan_name}' (New Quotas: {rollup_after.api_calls.quota:,} calls, {rollup_after.ai_tokens.quota:,} tokens)")
    assert rollup_after.plan_id == "pro", f"Expected plan to flip to 'pro', got '{rollup_after.plan_id}'"
    assert rollup_after.api_calls.quota == 50000, "Expected Pro API quota (50,000)"
    assert rollup_after.ai_tokens.quota == 10000000, "Expected Pro Token quota (10,000,000)"
    print("PROBE 3: PASSED (Stripe webhook flipped tenant Free -> Pro and updated limits)\n")

def probe_4_webhook_security():
    print("--- [PROBE 4] Webhook Cryptographic Verification & Replay Deduplication ---")
    test_event_id = f"evt_replay_test_{uuid.uuid4().hex[:12]}"
    valid_payload = {
        "id": test_event_id,
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_test_123", "status": "active"}}
    }
    valid_bytes = json.dumps(valid_payload).encode("utf-8")

    # 1. Test Forged Signature -> MUST FAIL WITH 400
    forged_sig = "t=1614553200,v1=bad_forged_hex_signature_abcdef1234567890"
    forgery_caught = False
    try:
        stripe_service.process_webhook_event(valid_bytes, forged_sig)
    except (StripeSignatureVerificationError, ValueError) as err:
        print(f"Forged Webhook Test: Caught signature mismatch -> '{err}'")
        forgery_caught = True

    assert forgery_caught is True, "Forged signature must be rejected"

    # 2. Test Real Event (Valid signature) -> Processes successfully
    valid_sig = generate_stripe_signature_header(valid_bytes, stripe_service.webhook_secret)
    res_initial = stripe_service.process_webhook_event(valid_bytes, valid_sig)
    print(f"First Real Event Delivery: status='{res_initial.status}'")
    assert res_initial.status == "processed"

    # 3. Test Replay of Same Event -> Must be deduplicated without error
    res_replay = stripe_service.process_webhook_event(valid_bytes, valid_sig)
    print(f"Replay Delivery: status='{res_replay.status}' ('{res_replay.details}')")
    assert res_replay.status == "already_processed", "Replay must be recognized as 'already_processed'"

    print("PROBE 4: PASSED (Forged signatures rejected; replayed events safely deduplicated)\n")

def probe_5_token_pricing_rules():
    print("--- [PROBE 5] AI Token Pricing Math (Cached Input & Reasoning Tokens) ---")
    tenant_id = "tenant_beta"

    # Test Scenarios:
    # 10,000 Fresh Input Tokens @ $0.150/1M = 150,000 microcents
    # 20,000 Cached Input Tokens @ $0.075/1M (cheaper) = 150,000 microcents
    # 5,000 Output Tokens @ $0.600/1M = 300,000 microcents
    # 5,000 Reasoning Tokens @ $0.600/1M (billed as output) = 300,000 microcents
    # Total Expected Cost = 150,000 + 150,000 + 300,000 + 300,000 = 900,000 microcents = $0.009000 USD
    input_tok = 10000
    cached_tok = 20000
    output_tok = 5000
    reason_tok = 5000

    expected_microcents = compute_token_cost_microcents(
        input_tokens=input_tok,
        cached_input_tokens=cached_tok,
        output_tokens=output_tok,
        reasoning_tokens=reason_tok
    )
    print(f"Computed Math: {expected_microcents} microcents ($0.009000 USD)")
    assert expected_microcents == 900000, f"Expected 900,000 microcents, got {expected_microcents}"

    # Record via meter service
    key = f"key_pricing_{uuid.uuid4().hex[:8]}"
    resp = meter_service.record_usage(
        tenant_id=tenant_id,
        usage_type=UsageTypeEnum.AI_TOKENS,
        quantity=(input_tok + cached_tok + output_tok + reason_tok),
        idempotency_key=key,
        input_tokens=input_tok,
        cached_input_tokens=cached_tok,
        output_tokens=output_tok,
        reasoning_tokens=reason_tok
    )
    print(f"Metered Cost Response: {resp.cost_microcents} microcents ({resp.cost_usd_display})")
    assert resp.cost_microcents == 900000

    # Query GET /usage to verify rollup matches pinned rules
    rollup = rollup_service.get_tenant_usage_rollup(tenant_id)
    print(f"Rollup GET /usage Cost: {rollup.cost['token_usage_microcents']} microcents ({rollup.cost['token_usage_usd']})")
    assert rollup.cost["token_usage_microcents"] >= 900000

    print("PROBE 5: PASSED (Cached input and reasoning token pricing rules match exact money math)\n")

def main():
    parser = argparse.ArgumentParser(description="Verify Evaluator Acceptance Probes")
    parser.add_argument("--probe", type=int, choices=[1, 2, 3, 4, 5], help="Run specific probe")
    args = parser.parse_args()

    probes = {
        1: probe_1_idempotency,
        2: probe_2_quota_boundaries,
        3: probe_3_stripe_checkout_flip,
        4: probe_4_webhook_security,
        5: probe_5_token_pricing_rules
    }

    if args.probe:
        probes[args.probe]()
    else:
        print("======================================================================")
        print("RUNNING ALL ACCEPTANCE PROBES (PROBES 1 TO 5)")
        print("======================================================================\n")
        for num in range(1, 6):
            probes[num]()
        print("======================================================================")
        print("ALL 5 ACCEPTANCE PROBES PASSED WITH ZERO ERRORS!")
        print("======================================================================\n")

if __name__ == "__main__":
    main()
