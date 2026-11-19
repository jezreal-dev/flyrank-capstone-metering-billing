"""Tests for integer money mathematics and token pricing rules."""
import pytest
from app.core.money_math import (
    compute_token_cost_microcents,
    microcents_to_cents,
    microcents_to_usd_display
)

def test_compute_token_cost_microcents_standard():
    # 10k input @ $0.150/1M = 150k microcents
    # 20k cached @ $0.075/1M = 150k microcents
    # 5k output @ $0.600/1M = 300k microcents
    # 5k reasoning @ $0.600/1M = 300k microcents
    total = compute_token_cost_microcents(
        input_tokens=10000,
        cached_input_tokens=20000,
        output_tokens=5000,
        reasoning_tokens=5000
    )
    assert total == 900000

def test_reasoning_tokens_billed_as_output():
    cost_regular = compute_token_cost_microcents(0, 0, 1000, 0)
    cost_reasoning = compute_token_cost_microcents(0, 0, 0, 1000)
    assert cost_regular == cost_reasoning, "Reasoning tokens must be billed at exact output token rate"

def test_cached_input_tokens_discount():
    cost_fresh = compute_token_cost_microcents(10000, 0, 0, 0)
    cost_cached = compute_token_cost_microcents(0, 10000, 0, 0)
    assert cost_cached < cost_fresh, "Cached input tokens must be cheaper than fresh input"
    assert cost_cached * 2 == cost_fresh, "Cached tokens should be 50% of fresh input rate"

def test_negative_tokens_rejected():
    with pytest.raises(ValueError):
        compute_token_cost_microcents(-10, 0, 0, 0)

def test_microcents_to_cents_conversion():
    assert microcents_to_cents(1_000_000) == 1
    assert microcents_to_cents(1_499_999) == 1
    assert microcents_to_cents(1_500_000) == 2  # Round half up
    assert microcents_to_cents(2_900_000_000) == 2900  # $29.00 = 2,900 cents

def test_microcents_to_usd_display():
    assert microcents_to_usd_display(900_000) == "$0.009000"
    assert microcents_to_usd_display(100_000_000) == "$1.000000"
