"""Cryptographic Stripe webhook signature verification and test payload signing."""
import hmac
import hashlib
import time
from typing import Dict

class StripeSignatureVerificationError(ValueError):
    """Raised when an inbound webhook fails cryptographic signature verification."""
    pass

def verify_stripe_signature(
    payload_bytes: bytes,
    signature_header: str,
    secret: str,
    tolerance_seconds: int = 300
) -> Dict[str, str]:
    """Verifies Stripe HMAC-SHA256 webhook signature against signing secret.
    Conforms strictly to Stripe's v1 signature verification specification.
    """
    if not signature_header or not secret:
        raise StripeSignatureVerificationError("Missing Stripe signature header or signing secret")

    # Parse header pairs: t=timestamp,v1=signature
    pairs = {}
    for part in signature_header.split(","):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            pairs[k] = v

    timestamp_str = pairs.get("t")
    v1_sig = pairs.get("v1")

    if not timestamp_str or not v1_sig:
        raise StripeSignatureVerificationError("Malformed Stripe-Signature header format")

    try:
        timestamp = int(timestamp_str)
    except ValueError:
        raise StripeSignatureVerificationError("Invalid timestamp in Stripe-Signature header")

    # Tolerance check (replay attacks)
    current_time = int(time.time())
    if abs(current_time - timestamp) > tolerance_seconds:
        raise StripeSignatureVerificationError(
            f"Stripe webhook timestamp drift ({abs(current_time - timestamp)}s) exceeds tolerance ({tolerance_seconds}s)"
        )

    # Compute expected HMAC-SHA256
    signed_payload = f"{timestamp_str}.".encode("utf-8") + payload_bytes
    expected_hash = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256
    ).hexdigest()

    # Constant-time comparison
    if not hmac.compare_digest(v1_sig, expected_hash):
        raise StripeSignatureVerificationError("Cryptographic signature mismatch: webhook payload may be forged")

    return {"timestamp": timestamp_str, "signature": v1_sig}

def generate_stripe_signature_header(
    payload_bytes: bytes,
    secret: str,
    timestamp: int | None = None
) -> str:
    """Generates an authentic Stripe-Signature header (t=...,v1=...) for testing."""
    ts = timestamp or int(time.time())
    signed_payload = f"{ts}.".encode("utf-8") + payload_bytes
    computed_sig = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256
    ).hexdigest()
    return f"t={ts},v1={computed_sig}"
