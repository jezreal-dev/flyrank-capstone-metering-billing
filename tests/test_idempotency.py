"""Tests for exactly-once metering and idempotency deduplication."""
import uuid
import pytest
from app.services.meter_service import meter_service
from app.core.database import get_db_connection
from app.models.schemas import UsageTypeEnum

def test_idempotent_replay_returns_cached_response():
    tenant_id = "tenant_beta"
    key = f"key_test_{uuid.uuid4().hex[:10]}"

    res1 = meter_service.record_usage(
        tenant_id=tenant_id,
        usage_type=UsageTypeEnum.API_CALL,
        quantity=3,
        idempotency_key=key
    )
    assert res1.is_idempotent_replay is False

    res2 = meter_service.record_usage(
        tenant_id=tenant_id,
        usage_type=UsageTypeEnum.API_CALL,
        quantity=3,
        idempotency_key=key
    )
    assert res2.is_idempotent_replay is True
    assert res1.event_id == res2.event_id
    assert res1.cost_microcents == res2.cost_microcents

def test_no_double_counting_in_database():
    tenant_id = "tenant_beta"
    key = f"key_db_check_{uuid.uuid4().hex[:10]}"

    for _ in range(5):
        meter_service.record_usage(
            tenant_id=tenant_id,
            usage_type=UsageTypeEnum.API_CALL,
            quantity=2,
            idempotency_key=key
        )

    with get_db_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) as c FROM usage_events WHERE idempotency_key = ?",
            (key,)
        ).fetchone()["c"]

    assert count == 1, "Even under 5 replayed requests, exactly 1 usage row must exist"
