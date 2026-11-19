"""Usage aggregation and monthly cost rollup service."""
from app.core.database import get_db_connection
from app.core.money_math import (
    microcents_to_cents,
    microcents_to_usd_display
)
from app.models.schemas import (
    UsageRollupResponse,
    QuotaMetric,
    SubscriptionStatusEnum,
    UsageTypeEnum
)

class RollupService:
    def get_tenant_usage_rollup(self, tenant_id: str) -> UsageRollupResponse:
        with get_db_connection() as conn:
            # 1. Tenant, Plan & Subscription
            query = """
                SELECT 
                    t.id as tenant_id, t.name as tenant_name,
                    p.id as plan_id, p.name as plan_name, p.api_quota, p.token_quota, p.price_cents,
                    s.status as subscription_status,
                    s.current_period_start, s.current_period_end
                FROM tenants t
                JOIN subscriptions s ON t.id = s.tenant_id
                JOIN plans p ON s.plan_id = p.id
                WHERE t.id = ?
            """
            tenant_row = conn.execute(query, (tenant_id,)).fetchone()
            if not tenant_row:
                raise ValueError(f"Tenant with ID '{tenant_id}' not found")

            # 2. Sum API calls
            api_row = conn.execute(
                """
                SELECT COALESCE(SUM(quantity), 0) as used
                FROM usage_events
                WHERE tenant_id = ? AND usage_type = 'api_call'
                  AND created_at >= ?
                """,
                (tenant_id, tenant_row["current_period_start"])
            ).fetchone()
            api_used = int(api_row["used"])

            # 3. Sum AI tokens & breakdown
            token_row = conn.execute(
                """
                SELECT 
                    COALESCE(SUM(quantity), 0) as total_tokens,
                    COALESCE(SUM(input_tokens), 0) as inp,
                    COALESCE(SUM(cached_input_tokens), 0) as cached,
                    COALESCE(SUM(output_tokens), 0) as outp,
                    COALESCE(SUM(reasoning_tokens), 0) as reas,
                    COALESCE(SUM(cost_microcents), 0) as cost_micro
                FROM usage_events
                WHERE tenant_id = ? AND usage_type = 'ai_tokens'
                  AND created_at >= ?
                """,
                (tenant_id, tenant_row["current_period_start"])
            ).fetchone()

            tokens_used = int(token_row["total_tokens"])
            total_microcents = int(token_row["cost_micro"])

            # Calculate quotas & remaining
            api_quota = tenant_row["api_quota"]
            api_rem = max(0, api_quota - api_used)
            api_pct = round((api_used / api_quota) * 100.0, 2) if api_quota > 0 else 0.0

            token_quota = tenant_row["token_quota"]
            tok_rem = max(0, token_quota - tokens_used)
            tok_pct = round((tokens_used / token_quota) * 100.0, 2) if token_quota > 0 else 0.0

            total_cents = microcents_to_cents(total_microcents)

            return UsageRollupResponse(
                tenant_id=tenant_row["tenant_id"],
                tenant_name=tenant_row["tenant_name"],
                plan_id=tenant_row["plan_id"],
                plan_name=tenant_row["plan_name"],
                subscription_status=SubscriptionStatusEnum(tenant_row["subscription_status"]),
                billing_period={
                    "start": tenant_row["current_period_start"],
                    "end": tenant_row["current_period_end"]
                },
                api_calls=QuotaMetric(
                    used=api_used,
                    quota=api_quota,
                    remaining=api_rem,
                    percentage=api_pct
                ),
                ai_tokens=QuotaMetric(
                    used=tokens_used,
                    quota=token_quota,
                    remaining=tok_rem,
                    percentage=tok_pct
                ),
                token_breakdown={
                    "input_tokens": int(token_row["inp"]),
                    "cached_input_tokens": int(token_row["cached"]),
                    "output_tokens": int(token_row["outp"]),
                    "reasoning_tokens": int(token_row["reas"])
                },
                cost={
                    "plan_base_cents": tenant_row["price_cents"],
                    "plan_base_usd": f"${tenant_row['price_cents'] / 100.0:.2f}",
                    "token_usage_microcents": total_microcents,
                    "token_usage_cents": total_cents,
                    "token_usage_usd": microcents_to_usd_display(total_microcents),
                    "total_incurred_usd": f"${(tenant_row['price_cents'] + total_cents) / 100.0:.2f}"
                }
            )

rollup_service = RollupService()
