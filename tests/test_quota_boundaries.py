"""Tests for quota boundary checks and 429/402 responses."""
import uuid
import pytest
from app.services.quota_service import quota_service, QuotaExceededException
from app.models.schemas import UsageTypeEnum
from app.core.database import get_db_connection

def test_delinquent_tenant_triggers_402():
    with pytest.raises(QuotaExceededException) as exc_info:
        quota_service.check_quota("tenant_delinquent", UsageTypeEnum.API_CALL, 1)
    assert exc_info.value.status_code == 402
    assert "past_due" in exc_info.value.message

def test_boundary_overflow_triggers_429():
    tenant_id = "tenant_test_boundary_ovf"
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO tenants (id, name, email) VALUES (?, 'Boundary', 'b@test.com')", (tenant_id,))
        conn.execute("INSERT OR REPLACE INTO subscriptions (id, tenant_id, plan_id, status) VALUES (?, ?, 'free', 'active')", (f"sub_{tenant_id}", tenant_id))
        conn.execute("DELETE FROM usage_events WHERE tenant_id = ?", (tenant_id,))
        # Pre-seed 999
        conn.execute(
            "INSERT INTO usage_events (id, tenant_id, usage_type, quantity, idempotency_key) VALUES ('e1', ?, 'api_call', 999, 'k1')",
            (tenant_id,)
        )
        conn.commit()

    # Call 1000: Allowed
    allowed, details = quota_service.check_quota(tenant_id, UsageTypeEnum.API_CALL, 1)
    assert allowed is True
    assert details["remaining_after"] == 0

    # Call 1001: Overflow -> 429
    with pytest.raises(QuotaExceededException) as exc_info:
        quota_service.check_quota(tenant_id, UsageTypeEnum.API_CALL, 2)
    assert exc_info.value.status_code == 429
    assert "Usage quota exceeded" in exc_info.value.message
