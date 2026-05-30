#!/usr/bin/env python3
from __future__ import annotations

from typing import Any


OPENAI_API_PRICING_PER_1M: dict[str, dict[str, float]] = {
    "gpt-5.5": {"input": 5.00, "cached_input": 0.50, "output": 30.00},
    "gpt-5.5-xhigh": {"input": 5.00, "cached_input": 0.50, "output": 30.00},
    "gpt-5.4": {"input": 2.50, "cached_input": 0.25, "output": 15.00},
}

CODEX_CREDITS_PER_1M: dict[str, dict[str, float]] = {
    "gpt-5.5": {"input": 125.0, "cached_input": 12.50, "output": 750.0},
    "gpt-5.5-xhigh": {"input": 125.0, "cached_input": 12.50, "output": 750.0},
    "gpt-5.4": {"input": 62.50, "cached_input": 6.250, "output": 375.0},
}

PRICING_VERSION = "2026-05-30"
OPENAI_API_PRICING_URL = "https://developers.openai.com/api/docs/models/gpt-5.5/"
CODEX_RATE_CARD_URL = "https://help.openai.com/en/articles/20001106-codex-rate-card"


def int_value(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def float_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def pricing_for_model(model: str | None, table: dict[str, dict[str, float]]) -> tuple[str, dict[str, float]] | None:
    if not model:
        return None
    normalized = model.strip().lower()
    if normalized in table:
        return normalized, table[normalized]
    if normalized.startswith("gpt-5.5"):
        return "gpt-5.5", table["gpt-5.5"]
    if normalized.startswith("gpt-5.4"):
        return "gpt-5.4", table["gpt-5.4"]
    return None


def token_cost(
    *,
    uncached_input_tokens: int,
    cache_read_input_tokens: int,
    output_tokens: int,
    pricing: dict[str, float],
) -> float:
    return (
        uncached_input_tokens * pricing["input"]
        + cache_read_input_tokens * pricing["cached_input"]
        + output_tokens * pricing["output"]
    ) / 1_000_000


def build_billing_usage(usage: dict[str, Any], provider: str | None) -> dict[str, Any]:
    input_tokens = int_value(usage.get("input_tokens"))
    output_tokens = int_value(usage.get("output_tokens"))
    reasoning_output_tokens = int_value(usage.get("reasoning_output_tokens"))
    cache_read_input_tokens = int_value(usage.get("cache_read_input_tokens"))
    cache_creation_input_tokens = int_value(usage.get("cache_creation_input_tokens"))

    if provider == "codex":
        uncached_input_tokens = max(input_tokens - cache_read_input_tokens, 0)
    else:
        uncached_input_tokens = input_tokens

    billing_usage: dict[str, Any] = {
        "uncached_input_tokens": uncached_input_tokens,
        "cache_read_input_tokens": cache_read_input_tokens,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_output_tokens,
        "reasoning_output_tokens_included": bool(reasoning_output_tokens),
    }

    reported_cost = float_value(usage.get("provider_reported_cost_usd"))
    if reported_cost is not None:
        billing_usage["provider_reported_cost_usd"] = reported_cost

    duration_ms = int_value(usage.get("duration_ms"))
    if duration_ms:
        billing_usage["duration_ms"] = duration_ms

    return billing_usage


def normalize_usage(usage: Any, *, model: str | None = None) -> dict[str, dict[str, Any]]:
    if not isinstance(usage, dict):
        return {}

    provider = usage.get("provider") if isinstance(usage.get("provider"), str) else None
    input_tokens = int_value(usage.get("input_tokens"))
    output_tokens = int_value(usage.get("output_tokens"))
    reasoning_output_tokens = int_value(usage.get("reasoning_output_tokens"))
    cache_read_input_tokens = int_value(usage.get("cache_read_input_tokens"))
    cache_creation_input_tokens = int_value(usage.get("cache_creation_input_tokens"))

    if provider == "codex":
        normalized_input_tokens = input_tokens
    else:
        normalized_input_tokens = input_tokens + cache_read_input_tokens + cache_creation_input_tokens

    billing_usage = build_billing_usage(usage, provider)
    normalized_usage: dict[str, Any] = {
        "input_tokens": normalized_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_output_tokens,
        "reasoning_output_tokens_included": bool(reasoning_output_tokens),
        "cache_read_input_tokens": cache_read_input_tokens,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "cost_usd": None,
        "cost_source": "unknown",
    }

    if provider:
        normalized_usage["provider"] = provider

    duration_ms = int_value(usage.get("duration_ms"))
    if duration_ms:
        normalized_usage["duration_ms"] = duration_ms

    reported_cost = float_value(usage.get("provider_reported_cost_usd"))
    if reported_cost is not None:
        normalized_usage["cost_usd"] = reported_cost
        normalized_usage["cost_source"] = "provider_reported"
    elif provider == "codex":
        pricing_match = pricing_for_model(model, OPENAI_API_PRICING_PER_1M)
        if pricing_match is not None:
            pricing_model, pricing = pricing_match
            estimated_cost = token_cost(
                uncached_input_tokens=billing_usage["uncached_input_tokens"],
                cache_read_input_tokens=cache_read_input_tokens,
                output_tokens=output_tokens,
                pricing=pricing,
            )
            normalized_usage.update(
                {
                    "cost_usd": estimated_cost,
                    "cost_source": "estimated_api_equivalent",
                    "pricing_model": pricing_model,
                    "pricing_version": PRICING_VERSION,
                    "pricing_url": OPENAI_API_PRICING_URL,
                }
            )

    if provider == "codex":
        credit_match = pricing_for_model(model, CODEX_CREDITS_PER_1M)
        if credit_match is not None:
            credit_model, credit_pricing = credit_match
            billing_usage["estimated_codex_credits"] = token_cost(
                uncached_input_tokens=billing_usage["uncached_input_tokens"],
                cache_read_input_tokens=cache_read_input_tokens,
                output_tokens=output_tokens,
                pricing=credit_pricing,
            )
            billing_usage["codex_credit_source"] = "estimated_codex_rate_card"
            billing_usage["codex_rate_card_model"] = credit_model
            billing_usage["codex_rate_card_version"] = PRICING_VERSION
            billing_usage["codex_rate_card_url"] = CODEX_RATE_CARD_URL

    return {
        "normalized_usage": normalized_usage,
        "billing_usage": billing_usage,
    }
