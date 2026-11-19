"""API route for Stripe signed webhooks."""
from fastapi import APIRouter, Request, Header, HTTPException, status
from app.services.stripe_service import stripe_service
from app.core.stripe_security import StripeSignatureVerificationError
from app.models.schemas import WebhookResponse

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

@router.post("/stripe", response_model=WebhookResponse, status_code=status.HTTP_200_OK)
async def handle_stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature")
):
    """Handles incoming Stripe webhooks with cryptographic signature verification
    and event deduplication.
    """
    if not stripe_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required Stripe-Signature header"
        )

    raw_body = await request.body()
    try:
        response = stripe_service.process_webhook_event(
            payload_bytes=raw_body,
            signature_header=stripe_signature
        )
        return response
    except StripeSignatureVerificationError as se:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Webhook verification failed: {se}"
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
