# BUILDLOG.md — AI-Assisted Engineering Journal

**Author:** Jezreal Momoh  
**Project:** LLM Usage Metering & Billing Engine (`flyrank-capstone-metering-billing`)  
**Track:** Backend AI Engineering — Week 8 Capstone  

---

## 1. Where AI Assisted & Accelerated Development
1. **Schema & Model Definition**:
   - Accelerated the definition of Pydantic v2 boundary models (`MeterRequest`, `UsageRollupResponse`, `CheckoutSessionResponse`).
2. **Stripe Webhook Event Structure Scaffolding**:
   - Generated standard Stripe test webhook JSON fixtures (`checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`).
3. **FastAPI Route Scaffolding**:
   - Rapidly assembled boilerplate REST routes and Swagger documentation decorators.

---

## 2. Where AI Was Wrong, Hallucinated, or Required Architectural Intervention
1. **Financial Float Precision Hallucination**:
   - *Issue:* Initially, the AI attempted to store dollars and cents as floating-point floats (`round(tokens * rate, 2)`), which causes IEEE-754 binary floating-point inaccuracies over millions of records.
   - *Fix:* Architected an integer-only microcents standard ($1\text{ USD} = 100\text{ cents} = 100,000,000\text{ microcents}$) using pure integer division and modulus (`//` and `%`), strictly preventing fractional cent leakage.
2. **Test Mutation Side-Effect on Shared Tenant**:
   - *Issue:* The AI wrote a webhook test that used `tenant_boundary` to test the Stripe Pro upgrade. This mutated `tenant_boundary` from Free (1,000 quota) to Pro (50,000 quota), which subsequently broke the boundary quota test expecting 1,001 calls to trigger HTTP 429.
   - *Fix:* Isolated test state by ensuring each probe function self-resets its required preconditions and test fixtures to prevent cross-test contamination.
3. **Stripe Webhook Signature Verification Algorithm**:
   - *Issue:* The AI initially suggested installing the external `stripe` Python SDK, which failed in network-isolated sandbox environments.
   - *Fix:* Implemented Stripe's official HMAC-SHA256 signature verification directly in Python standard library (`hmac`, `hashlib`), verifying `t=...,v1=...` headers with constant-time `hmac.compare_digest` and zero external dependencies.

---

## 3. Human Engineering Decisions & Invariants
1. **Idempotency Header Contract**:
   - Enforced the `Idempotency-Key` header on all billable endpoints. Replayed keys fetch the original cached response with zero database row mutations, guaranteeing no double-charging.
2. **Pre-Action Quota Enforcement**:
   - Quotas are checked *before* performing billable actions, returning clean machine-readable status codes: `429 Too Many Requests` (with `Retry-After`) for plan limits, and `402 Payment Required` for delinquent or past-due subscriptions.
3. **Tiered AI Token Pricing Rules**:
   - Strictly enforced that cached input tokens receive a 50% discount, while reasoning ("thinking") tokens are billed as output tokens rather than left unmetered.
