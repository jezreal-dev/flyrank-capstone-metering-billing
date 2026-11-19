"""Regression tests ensuring all 5 FlyRank Evaluator Acceptance Probes pass."""
import pytest
from scripts.verify_probes import (
    probe_1_idempotency,
    probe_2_quota_boundaries,
    probe_3_stripe_checkout_flip,
    probe_4_webhook_security,
    probe_5_token_pricing_rules
)

def test_acceptance_probe_1_idempotency():
    probe_1_idempotency()

def test_acceptance_probe_2_quota_boundaries():
    probe_2_quota_boundaries()

def test_acceptance_probe_3_stripe_checkout_flip():
    probe_3_stripe_checkout_flip()

def test_acceptance_probe_4_webhook_security():
    probe_4_webhook_security()

def test_acceptance_probe_5_token_pricing_rules():
    probe_5_token_pricing_rules()
