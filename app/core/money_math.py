"""Integer-only money mathematics utilities.
Strictly avoids floating-point numbers to guarantee zero financial rounding drift.
"""
from typing import Dict, Any

# Scaling Constants
MICROCENTS_PER_CENT = 1_000_000
MICROCENTS_PER_USD = 100_000_000

# Default Pinned Pricing (Integer microcents per 1,000,000 tokens)
# $0.150 / 1M input tokens = 15,000,000 microcents per 1M tokens
DEFAULT_INPUT_RATE_MICROCENTS_PER_M = 15_000_000
# $0.075 / 1M cached input tokens (50% discount) = 7,500,000 microcents per 1M tokens
DEFAULT_CACHED_INPUT_RATE_MICROCENTS_PER_M = 7_500_000
# $0.600 / 1M output tokens = 60,000,000 microcents per 1M tokens
DEFAULT_OUTPUT_RATE_MICROCENTS_PER_M = 60_000_000

def compute_token_cost_microcents(
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    input_rate_per_m: int = DEFAULT_INPUT_RATE_MICROCENTS_PER_M,
    cached_rate_per_m: int = DEFAULT_CACHED_INPUT_RATE_MICROCENTS_PER_M,
    output_rate_per_m: int = DEFAULT_OUTPUT_RATE_MICROCENTS_PER_M,
) -> int:
    """Computes exact cost in integer microcents using the rule:
    - Cached input tokens are cheaper.
    - Reasoning tokens count as output tokens.
    - Token categories cannot simply be added together.
    """
    if input_tokens < 0 or cached_input_tokens < 0 or output_tokens < 0 or reasoning_tokens < 0:
        raise ValueError("Token counts cannot be negative")

    # Math: (tokens * rate_per_million) // 1_000_000
    cost_input = (input_tokens * input_rate_per_m) // 1_000_000
    cost_cached = (cached_input_tokens * cached_rate_per_m) // 1_000_000
    # Reasoning tokens are strictly billed as output tokens!
    effective_output_tokens = output_tokens + reasoning_tokens
    cost_output = (effective_output_tokens * output_rate_per_m) // 1_000_000

    total_microcents = cost_input + cost_cached + cost_output
    return total_microcents

def microcents_to_cents(microcents: int) -> int:
    """Converts integer microcents to integer cents (standard round half up)."""
    return (microcents + 500_000) // MICROCENTS_PER_CENT

def microcents_to_usd_display(microcents: int) -> str:
    """Formats microcents into a precise readable USD string (e.g. '$0.001234')."""
    dollars = microcents // MICROCENTS_PER_USD
    fraction = microcents % MICROCENTS_PER_USD
    return f"${dollars}.{fraction:08d}"[:9]
