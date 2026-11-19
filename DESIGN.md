# Architecture & Design Specification: Usage Metering & Billing Engine

## 1. System Mission & Core Responsibilities
Every SaaS platform must answer three fundamental business questions:
1. **How much has this customer used?** (Accurate, idempotent usage metering)
2. **Have they reached their subscription limits?** (Honest, pre-action quota enforcement)
3. **How much should they pay?** (Correct money math and AI-token pricing)

The **Usage Metering & Billing Engine** provides a resilient multi-tenant backend service handling API calls and AI token accounting. It features strict boundary idempotency to eliminate double-charging on network retries, enforces plan quotas with explicit HTTP status codes (`429` vs. `402`), implements precise integer-based money mathematics for complex AI token tiers, and synchronizes subscription state via cryptographically verified Stripe test webhooks.

---

## 2. Core Invariants & Architectural Rules

1. **Exactly-Once Metering via Idempotency Keys**:
   - Every billable action accepts an `Idempotency-Key` HTTP header.
   - Replaying the identical key returns the original cached response with zero duplicate database mutations.
2. **Honest Boundary Quota Enforcement**:
   - Quotas are checked **before** executing the billable action (`current_usage + requested_usage <= plan_limit`).
   - Reaching plan boundaries behaves deterministically: call 1,000 of 1,000 succeeds; call 1,001 immediately yields `429 Too Many Requests` with a descriptive message and `Retry-After`.
   - Delinquent or unpaid accounts yield `402 Payment Required`.
3. **Integer Money Mathematics (No Floats)**:
   - Floating-point representations are strictly prohibited for monetary values to prevent IEEE-754 precision drift.
   - Money is computed and stored as integer microcents ($1\text{ USD} = 100\text{ cents} = 100,000,000\text{ microcents}$).
4. **AI Token Tiered Pricing Rules**:
   - Fresh input tokens are billed at standard base rates ($0.150 / 1M tokens).
   - Cached input tokens receive a discounted rate ($0.075 / 1M tokens).
   - Output tokens are billed at the generation rate ($0.600 / 1M tokens).
   - Reasoning ("thinking") tokens are classified and billed as **output tokens** (not free or unmetered).
5. **Cryptographic Webhook Verification & Deduplication**:
   - Inbound Stripe webhooks are verified using HMAC-SHA256 signatures against `STRIPE_WEBHOOK_SECRET`. Forged payloads immediately return `400 Bad Request`.
   - Webhook events are deduplicated by `stripe_event_id`; replayed events return `200 OK` (`already_processed`) with zero state mutation.

---

## 3. Data Model & Database Schema

- `tenants`: Primary customer organizations (`id`, `name`, `email`, `created_at`).
- `plans`: Tier specifications (`id`, `name`, `api_quota`, `token_quota`, `price_cents`, `is_active`).
- `subscriptions`: Active plan mappings (`id`, `tenant_id`, `plan_id`, `stripe_customer_id`, `stripe_subscription_id`, `status`, `current_period_start`, `current_period_end`).
- `usage_events`: Individual billable consumption records (`id`, `tenant_id`, `usage_type`, `quantity`, `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_tokens`, `cost_microcents`, `created_at`).
- `idempotency_records`: Request deduplication cache (`idempotency_key`, `tenant_id`, `request_hash`, `response_status`, `response_body`, `created_at`).
- `processed_stripe_events`: Webhook deduplication log (`event_id`, `event_type`, `processed_at`).

---

## 4. API Surface

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/meter` | `POST` | Record billable usage event with `Idempotency-Key` header |
| `/api/generate` | `POST` | Dummy billable AI endpoint: checks quota, meters tokens, returns result |
| `/api/usage` | `GET` | Aggregated monthly rollup: used, limit, cost, and plan status |
| `/api/billing/checkout-session`| `POST` | Create Stripe test Checkout session for Pro upgrade |
| `/api/webhooks/stripe` | `POST` | Cryptographically verified, deduplicated Stripe webhook handler |
| `/api/plans` | `GET` | Query available tiers (Free / Pro) and quotas |

---

## 5. Explicit Non-Goals
- Real money movement (Stripe test mode sandbox exclusively).
- Multi-currency conversion (USD integer units exclusively).
- Real LLM inference generation (metering tokens and numbers, no model keys required).
