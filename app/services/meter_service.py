"""Idempotent usage recording and meter accounting service."""
import uuid
import datetime
from typing import Dict, Any, Tuple
from app.core.database import get_db_connection
from app.core.money_math import (
    compute_token_cost_microcents,
    microcents_to_usd_display
)
from app.core.idempotency import idempotency_manager, hash_payload
from app.services.quota_service import quota_service
from app.models.schemas import UsageTypeEnum, MeterResponse

class MeterService:
    def record_usage(
        self,
        tenant_id: str,
        usage_type: UsageTypeEnum,
        quantity: int,
        idempotency_key: str,
        input_tokens: int = 0,
        cached_input_tokens: int = 0,
        output_tokens: int = 0,
        reasoning_tokens: int = 0,
    ) -> MeterResponse:
        """Records a billable usage event idempotently.
        Guarantees that re-sending the same request with the same idempotency key
        returns the identical original response without creating duplicate usage events.
        """
        request_data = {
            "tenant_id": tenant_id,
            "usage_type": usage_type.value,
            "quantity": quantity,
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
        }
        req_hash = hash_payload(request_data)

        # 1. Idempotency Check: Return existing record if already processed
        cached_record = idempotency_manager.get_existing_record(idempotency_key, tenant_id)
        if cached_record:
            body = cached_record["response_body"]
            body["is_idempotent_replay"] = True
            return MeterResponse(**body)

        # 2. Quota Check: Assert pre-action limits (raises QuotaExceededException on breach)
        quota_service.check_quota(tenant_id, usage_type, quantity)

        # 3. Calculate Cost in Integer Microcents
        cost_microcents = 0
        if usage_type == UsageTypeEnum.AI_TOKENS:
            cost_microcents = compute_token_cost_microcents(
                input_tokens=input_tokens,
                cached_input_tokens=cached_input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens
            )

        # 4. Insert Usage Event Atomically
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO usage_events (
                    id, tenant_id, usage_type, quantity,
                    input_tokens, cached_input_tokens, output_tokens, reasoning_tokens,
                    cost_microcents, idempotency_key, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    tenant_id,
                    usage_type.value,
                    quantity,
                    input_tokens,
                    cached_input_tokens,
                    output_tokens,
                    reasoning_tokens,
                    cost_microcents,
                    idempotency_key,
                    now_iso
                )
            )
            conn.commit()

        # 5. Build Response & Cache Idempotency Record
        response = MeterResponse(
            event_id=event_id,
            tenant_id=tenant_id,
            usage_type=usage_type,
            quantity=quantity,
            cost_microcents=cost_microcents,
            cost_usd_display=microcents_to_usd_display(cost_microcents),
            is_idempotent_replay=False,
            recorded_at=now_iso
        )

        idempotency_manager.store_record(
            idempotency_key=idempotency_key,
            tenant_id=tenant_id,
            request_hash=req_hash,
            status_code=201,
            response_body=response.model_dump()
        )

        return response

meter_service = MeterService()
