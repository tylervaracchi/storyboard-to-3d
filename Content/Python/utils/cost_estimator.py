# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Cost Estimator Utility
Rough pre-flight USD cost estimates for a batch storyboard-to-3D run, before
any API calls are made. Pure Python, no `unreal` import required so it can be
unit tested and reused outside of the Unreal-embedded interpreter.

Pricing is a snapshot and WILL drift as providers update their price pages.
Treat every number here as an estimate, not a bill.
"""

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Pricing table (USD per 1,000,000 tokens), current models only.
# ---------------------------------------------------------------------------
# "verified" == True means the price was cross-checked against the pricing
# already used elsewhere in this codebase (see core/ai_providers/claude_provider.py
# and core/ai_providers/gpt4v_provider.py) at the time this table was written.
MODEL_PRICING = {
    # Anthropic Claude family
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "verified": True},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "verified": True},
    "claude-opus-4-1": {"input": 15.00, "output": 75.00, "verified": True},

    # OpenAI GPT-4o
    # UNVERIFIED: this price was not cross-checked against OpenAI's live pricing
    # page as of writing. Confirm before relying on it for a budget-critical estimate.
    "gpt-4o": {"input": 2.50, "output": 10.00, "verified": False},

    # Local models served via Ollama - no per-token API cost.
    "llava": {"input": 0.00, "output": 0.00, "verified": True},
    "bakllava": {"input": 0.00, "output": 0.00, "verified": True},
    "internvl2": {"input": 0.00, "output": 0.00, "verified": True},
    "ollama": {"input": 0.00, "output": 0.00, "verified": True},
}

# Short-key aliases seen elsewhere in this codebase (e.g. analysis/multi_model_tracker.py)
# that don't match a MODEL_PRICING key by prefix.
MODEL_ALIASES = {
    "gpt4o": "gpt-4o",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
    "opus": "claude-opus-4-1",
}

# Anthropic prompt caching: cached reads cost ~10% of a normal input token
# (see claude_provider.py: cost_per_1m_cache_read_tokens = 0.30 vs cost_per_1m_input_tokens = 3.00).
CLAUDE_CACHE_READ_DISCOUNT = 0.10

# Conservative fallback used when a model string matches nothing known.
_UNKNOWN_PRICING = {"input": 0.00, "output": 0.00, "verified": False}


def _lookup_pricing(model):
    """
    Resolve a model name string to its pricing entry.

    Tries, in order: exact match, alias match, then prefix match (so dated
    suffixes like "claude-opus-4-1-20250805" still resolve). Falls back to a
    $0/$0 unverified entry for unrecognized models rather than raising, so a
    typo'd or brand-new model name degrades to "no estimate" instead of a crash.

    Args:
        model: Model name/id string.

    Returns:
        Dict with 'input', 'output' (USD per 1M tokens) and 'verified' (bool).
    """
    if not model:
        return dict(_UNKNOWN_PRICING)

    model_lower = str(model).lower()

    if model_lower in MODEL_PRICING:
        return MODEL_PRICING[model_lower]

    if model_lower in MODEL_ALIASES:
        aliased = MODEL_ALIASES[model_lower]
        if aliased in MODEL_PRICING:
            return MODEL_PRICING[aliased]

    # Prefix match, longest key first so "claude-opus-4-1" beats a shorter
    # accidental collision.
    for key in sorted(MODEL_PRICING.keys(), key=len, reverse=True):
        if model_lower.startswith(key):
            return MODEL_PRICING[key]

    # Substring match catches things like "llava:13b" or "ollama/llava:34b"
    # where the known key isn't a strict prefix.
    for key in sorted(MODEL_PRICING.keys(), key=len, reverse=True):
        if key in model_lower:
            return MODEL_PRICING[key]

    return dict(_UNKNOWN_PRICING)


def _is_claude_model(model):
    """Return True if `model` resolves to an Anthropic Claude model string."""
    if not model:
        return False
    return "claude" in str(model).lower() or str(model).lower() in ("sonnet", "haiku", "opus")


def _format_iterations(avg_iterations):
    """Format an iteration count without a trailing '.0' for whole numbers."""
    try:
        as_float = float(avg_iterations)
    except (TypeError, ValueError):
        return str(avg_iterations)

    if as_float.is_integer():
        return str(int(as_float))
    return f"{as_float:.1f}"


def estimate_run(
    num_panels,
    avg_iterations,
    model,
    images_per_iteration=7,
    tokens_per_image=1600,
    prompt_tokens=2500,
    output_tokens=800,
):
    # type: (int, float, str, int, int, int, int) -> Dict[str, Any]
    """
    Estimate the total token usage and USD cost of a batch run before it starts.

    Assumes each iteration sends `images_per_iteration` images (reference
    storyboard panel + rendered comparison shots, etc.) plus a text prompt,
    and receives a text-only analysis response back.

    Args:
        num_panels: Number of storyboard panels in the batch.
        avg_iterations: Average refinement iterations expected per panel
            (e.g. from historical metrics_tracker data, or a planning guess).
        model: Model name/id string, e.g. "claude-sonnet-4-6", "gpt-4o", "llava:13b".
        images_per_iteration: Images sent to the model per iteration. Default 7.
        tokens_per_image: Estimated tokens per image. Default 1600 (matches
            claude_provider.py's avg_tokens_per_image estimate).
        prompt_tokens: Text prompt tokens per iteration. Default 2500.
        output_tokens: Expected response tokens per iteration. Default 800.

    Returns:
        Dict with:
            input_tokens (int): total estimated input tokens across the run.
            output_tokens (int): total estimated output tokens across the run.
            usd (float): total estimated cost in USD (uncached / worst case).
            notes (List[str]): caveats -- unverified pricing, local-model
                zero-cost, and (for Claude models) an estimate of what prompt
                caching would realistically bring the cost down to.
            model (str): the model string this estimate was computed for.
            num_panels (int): echoed back for convenience (used by format_estimate).
            avg_iterations (float): echoed back for convenience.
    """
    num_panels = max(0, int(num_panels))
    avg_iterations = max(0.0, float(avg_iterations))
    images_per_iteration = max(0, int(images_per_iteration))
    tokens_per_image = max(0, int(tokens_per_image))
    prompt_tokens = max(0, int(prompt_tokens))
    output_tokens = max(0, int(output_tokens))

    total_iterations = num_panels * avg_iterations
    input_tokens_per_iter = (images_per_iteration * tokens_per_image) + prompt_tokens

    total_input_tokens = int(round(total_iterations * input_tokens_per_iter))
    total_output_tokens = int(round(total_iterations * output_tokens))

    pricing = _lookup_pricing(model)
    usd = (total_input_tokens / 1_000_000.0) * pricing["input"]
    usd += (total_output_tokens / 1_000_000.0) * pricing["output"]

    notes = []  # type: List[str]

    if pricing["input"] == 0.0 and pricing["output"] == 0.0 and pricing.get("verified"):
        notes.append(f"'{model}' runs locally (Ollama) - no per-token API cost, estimate is $0.00.")
    elif not pricing.get("verified"):
        notes.append(
            f"Pricing for '{model}' is UNVERIFIED or unrecognized - "
            "confirm against the provider's current pricing page before budgeting from this number."
        )

    if _is_claude_model(model) and avg_iterations > 1 and num_panels > 0:
        # First iteration per panel pays full input price; iterations after the
        # first can hit Anthropic's prompt cache on the repeated image context,
        # at roughly CLAUDE_CACHE_READ_DISCOUNT of the normal input price.
        cached_iterations = num_panels * (avg_iterations - 1)
        first_iter_input_cost = (num_panels * input_tokens_per_iter / 1_000_000.0) * pricing["input"]
        cached_input_cost = (
            (cached_iterations * input_tokens_per_iter / 1_000_000.0)
            * (pricing["input"] * CLAUDE_CACHE_READ_DISCOUNT)
        )
        output_cost = (total_output_tokens / 1_000_000.0) * pricing["output"]
        cached_usd = first_iter_input_cost + cached_input_cost + output_cost

        notes.append(
            f"With Anthropic prompt caching, iterations after the first per panel cost "
            f"~{int(CLAUDE_CACHE_READ_DISCOUNT * 100)}% of first-iteration input price; "
            f"realistic cached estimate ~${cached_usd:.2f} vs ${usd:.2f} shown (uncached, worst case)."
        )

    return {
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "usd": round(usd, 4),
        "notes": notes,
        "model": model,
        "num_panels": num_panels,
        "avg_iterations": avg_iterations,
    }


def format_estimate(d):
    # type: (Dict[str, Any]) -> str
    """
    Render an estimate_run() result as a short human-readable string.

    Args:
        d: Dict as returned by estimate_run().

    Returns:
        A short string, e.g. "$4.20 est (12 panels x 15 iters on claude-sonnet-4-6)".
    """
    usd = d.get("usd", 0.0) if isinstance(d, dict) else 0.0
    model = d.get("model") if isinstance(d, dict) else None
    num_panels = d.get("num_panels") if isinstance(d, dict) else None
    avg_iterations = d.get("avg_iterations") if isinstance(d, dict) else None

    model_str = model or "unknown model"

    if num_panels is not None and avg_iterations is not None:
        iters_str = _format_iterations(avg_iterations)
        return f"${usd:.2f} est ({num_panels} panels x {iters_str} iters on {model_str})"

    return f"${usd:.2f} est ({model_str})"


# Self-test
if __name__ == "__main__":
    print("Testing cost_estimator...")

    for test_model in ["claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-1-20250805", "gpt-4o", "llava:13b"]:
        result = estimate_run(num_panels=12, avg_iterations=15, model=test_model)
        print(f"\n{test_model}:")
        print(f"  {format_estimate(result)}")
        print(f"  input_tokens={result['input_tokens']:,} output_tokens={result['output_tokens']:,}")
        for note in result["notes"]:
            print(f"  note: {note}")
