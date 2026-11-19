"""API routes for usage metering and billable endpoints."""
import uuid
from fastapi import APIRouter, Header, HTTPException, Response
from app.models.schemas import (
    MeterRequest,
    MeterResponse,
    GenerateRequest,
    GenerateResponse,
    UsageTypeEnum
)
from app.services.meter_service import meter_service
from app.services.quota_service import QuotaExceededException
from app.core.money_math import (
    compute_token_cost_microcents,
    microcents_to_usd_display
)

router = APIRouter(prefix="/api", tags=["metering"])

@router.post("/meter", response_model=MeterResponse, status_code=201)
def record_meter_event(
    payload: MeterRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", description="Unique client idempotency key")
):
    """Records a billable usage event.
    Deduplicated by Idempotency-Key header.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=400, detail="Idempotency-Key header cannot be empty")

    try:
        res = meter_service.record_usage(
            tenant_id=payload.tenant_id,
            usage_type=payload.usage_type,
            quantity=payload.quantity,
            idempotency_key=idempotency_key.strip(),
            input_tokens=payload.input_tokens,
            cached_input_tokens=payload.cached_input_tokens,
            output_tokens=payload.output_tokens,
            reasoning_tokens=payload.reasoning_tokens
        )
        if res.is_idempotent_replay:
            response.status_code = 200
        return res
    except QuotaExceededException as qe:
        response.headers["Retry-After"] = str(qe.retry_after)
        raise HTTPException(status_code=qe.status_code, detail=qe.message)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

@router.post("/generate", response_model=GenerateResponse, status_code=200)
def generate_ai_completion(
    payload: GenerateRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", description="Unique client idempotency key")
):
    """Dummy billable endpoint simulating an AI completion request.
    Verifies quota, meters tokens, and returns response with cost attribution.
    """
    total_tokens = (
        payload.simulated_input_tokens +
        payload.simulated_cached_input_tokens +
        payload.simulated_output_tokens +
        payload.simulated_reasoning_tokens
    )

    try:
        meter_res = meter_service.record_usage(
            tenant_id=payload.tenant_id,
            usage_type=UsageTypeEnum.AI_TOKENS,
            quantity=total_tokens,
            idempotency_key=idempotency_key.strip(),
            input_tokens=payload.simulated_input_tokens,
            cached_input_tokens=payload.simulated_cached_input_tokens,
            output_tokens=payload.simulated_output_tokens,
            reasoning_tokens=payload.simulated_reasoning_tokens
        )

        return GenerateResponse(
            tenant_id=payload.tenant_id,
            result_text=f"Simulated completion for prompt: '{payload.prompt[:40]}...'",
            tokens_billed={
                "input_tokens": payload.simulated_input_tokens,
                "cached_input_tokens": payload.simulated_cached_input_tokens,
                "output_tokens": payload.simulated_output_tokens,
                "reasoning_tokens": payload.simulated_reasoning_tokens,
                "total_tokens": total_tokens
            },
            cost_microcents=meter_res.cost_microcents,
            cost_usd_display=meter_res.cost_usd_display,
            meter_event_id=meter_res.event_id
        )
    except QuotaExceededException as qe:
        response.headers["Retry-After"] = str(qe.retry_after)
        raise HTTPException(status_code=qe.status_code, detail=qe.message)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
