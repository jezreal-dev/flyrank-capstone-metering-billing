"""Quota evaluation service with boundary honesty and explicit 429/402 exceptions."""
from typing import Dict, Any, Tuple
from app.core.database import get_db_connection
from app.models.schemas import UsageTypeEnum, SubscriptionStatusEnum

class QuotaExceededException(Exception):
    def __init__(self, status_code: int, message: str, retry_after: int = 3600):
        self.status_code = status_code
        self.message = message
        self.retry_after = retry_after
        super().__init__(message)

class QuotaService:
    def check_quota(
        self,
        tenant_id: str,
        usage_type: UsageTypeEnum,
        quantity: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """Evaluates whether tenant can perform the requested usage quantity.
        Enforces pre-action quota limits: current + requested <= limit.
        """
        with get_db_connection() as conn:
            # 1. Fetch Tenant Subscription & Plan
            query = """
                SELECT 
                    t.id as tenant_id, t.name as tenant_name,
                    p.id as plan_id, p.name as plan_name, p.api_quota, p.token_quota,
                    s.status as subscription_status,
                    s.current_period_start, s.current_period_end
                FROM tenants t
                JOIN subscriptions s ON t.id = s.tenant_id
                JOIN plans p ON s.plan_id = p.id
                WHERE t.id = ?
            """
            row = conn.execute(query, (tenant_id,)).fetchone()
            if not row:
                raise ValueError(f"Tenant '{tenant_id}' not found or has no active plan")

            sub_status = row["subscription_status"]
            plan_name = row["plan_name"]
            api_quota = row["api_quota"]
            token_quota = row["token_quota"]

            # 2. Check Subscription Lapsed / Delinquent Status -> 402 Payment Required
            if sub_status in (SubscriptionStatusEnum.PAST_DUE.value, SubscriptionStatusEnum.CANCELED.value):
                raise QuotaExceededException(
                    status_code=402,
                    message=f"Payment Required: subscription status is '{sub_status}'. Update payment method or re-activate subscription."
                )

            # 3. Sum current billing period usage for this type
            usage_query = """
                SELECT COALESCE(SUM(quantity), 0) as total_used
                FROM usage_events
                WHERE tenant_id = ? AND usage_type = ?
                  AND created_at >= ?
            """
            usage_row = conn.execute(
                usage_query,
                (tenant_id, usage_type.value, row["current_period_start"])
            ).fetchone()
            current_used = int(usage_row["total_used"])

            # 4. Check Quota Limit
            quota_limit = api_quota if usage_type == UsageTypeEnum.API_CALL else token_quota
            new_total = current_used + quantity

            if new_total > quota_limit:
                metric_label = "API calls" if usage_type == UsageTypeEnum.API_CALL else "tokens"
                raise QuotaExceededException(
                    status_code=429,
                    message=(
                        f"Usage quota exceeded: current usage ({current_used:,} {metric_label}) "
                        f"+ requested ({quantity:,}) exceeds {plan_name} plan monthly quota ({quota_limit:,}). "
                        f"Upgrade to Pro plan to continue."
                    ),
                    retry_after=3600
                )

            return True, {
                "tenant_id": tenant_id,
                "plan_name": plan_name,
                "usage_type": usage_type.value,
                "current_used": current_used,
                "requested": quantity,
                "quota_limit": quota_limit,
                "remaining_after": quota_limit - new_total
            }

quota_service = QuotaService()
