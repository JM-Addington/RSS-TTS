"""Cost calculation utilities for OpenAI API usage."""

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# OpenAI pricing per million tokens (as of 2025-01-04)
# Source: https://www.llm-prices.com/
OPENAI_PRICING = {
    "gpt-4o": {
        "input": Decimal("2.50"),  # $2.50 per million input tokens
        "output": Decimal("10.00"),  # $10.00 per million output tokens
    },
    "gpt-4o-mini": {
        "input": Decimal("0.150"),  # $0.150 per million input tokens
        "output": Decimal("0.600"),  # $0.600 per million output tokens
    },
    "gpt-4o-mini-tts": {
        "input": Decimal("0.150"),  # Same as gpt-4o-mini
        "output": Decimal("0.600"),
    },
    "gpt-4.1": {
        "input": Decimal("2.00"),  # $2.00 per million input tokens
        "output": Decimal("8.00"),  # $8.00 per million output tokens
    },
    "gpt-4.1-mini": {
        "input": Decimal("0.40"),  # $0.40 per million input tokens
        "output": Decimal("1.60"),  # $1.60 per million output tokens
    },
    "gpt-4.1-nano": {
        "input": Decimal("0.10"),  # $0.10 per million input tokens
        "output": Decimal("0.40"),  # $0.40 per million output tokens
    },
    # TTS models - estimated pricing (need to verify with OpenAI)
    "tts-1": {
        "input": Decimal("15.00"),  # Estimated $15 per million characters
        "output": Decimal("0"),  # No output tokens for TTS
    },
    "tts-1-hd": {
        "input": Decimal("30.00"),  # Estimated $30 per million characters
        "output": Decimal("0"),  # No output tokens for TTS
    },
}

# Default pricing for unknown models (use gpt-4o-mini rates)
DEFAULT_PRICING = OPENAI_PRICING["gpt-4o-mini"]


def calculate_llm_cost(
    model_name: str, input_tokens: int, output_tokens: int
) -> Decimal:
    """
    Calculate the cost of an LLM API call.

    Args:
        model_name: Name of the OpenAI model used
        input_tokens: Number of input tokens consumed
        output_tokens: Number of output tokens generated

    Returns:
        Estimated cost in USD as a Decimal
    """
    # Get pricing for the model, fall back to default if unknown
    pricing = OPENAI_PRICING.get(model_name, DEFAULT_PRICING)

    # Calculate cost per token type
    input_cost = (Decimal(input_tokens) * pricing["input"]) / Decimal("1000000")
    output_cost = (Decimal(output_tokens) * pricing["output"]) / Decimal("1000000")

    total_cost = input_cost + output_cost

    # Round to 6 decimal places for storage
    rounded_cost = total_cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    logger.debug(
        f"Cost calculation for {model_name}: "
        f"{input_tokens} input + {output_tokens} output = ${rounded_cost}"
    )

    return rounded_cost


def calculate_tts_cost(model_name: str, character_count: int) -> Decimal:
    """
    Calculate the cost of a TTS API call.

    Args:
        model_name: Name of the TTS model used
        character_count: Number of characters processed

    Returns:
        Estimated cost in USD as a Decimal
    """
    # Get pricing for the model, fall back to tts-1 if unknown
    if model_name in OPENAI_PRICING:
        pricing = OPENAI_PRICING[model_name]
    else:
        pricing = OPENAI_PRICING["tts-1"]
        logger.warning(f"Unknown TTS model {model_name}, using tts-1 pricing")

    # TTS models are typically priced per character/token
    cost = (Decimal(character_count) * pricing["input"]) / Decimal("1000000")

    # Round to 6 decimal places for storage
    rounded_cost = cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    logger.debug(
        f"TTS cost calculation for {model_name}: "
        f"{character_count} characters = ${rounded_cost}"
    )

    return rounded_cost


def estimate_cost_from_total_tokens(
    model_name: str, total_tokens: int, input_ratio: float = 0.75
) -> Decimal:
    """
    Estimate cost when only total tokens are available.

    This is a fallback for existing usage records that only have total_tokens.
    We estimate the input/output split based on typical patterns.

    Args:
        model_name: Name of the OpenAI model used
        total_tokens: Total tokens used
        input_ratio: Estimated ratio of input tokens (default 0.75 = 75% input)

    Returns:
        Estimated cost in USD as a Decimal
    """
    estimated_input = int(total_tokens * input_ratio)
    estimated_output = total_tokens - estimated_input

    return calculate_llm_cost(model_name, estimated_input, estimated_output)


def get_model_pricing_info(model_name: str) -> Optional[Dict[str, Decimal]]:
    """
    Get pricing information for a specific model.

    Args:
        model_name: Name of the OpenAI model

    Returns:
        Dictionary with 'input' and 'output' pricing per million tokens,
        or None if model is unknown
    """
    return OPENAI_PRICING.get(model_name)


def format_cost_display(cost: Decimal) -> str:
    """
    Format a cost value for display to users.

    Args:
        cost: Cost value as Decimal

    Returns:
        Formatted string for display (e.g., "$0.001234" or "$1.23")
    """
    if cost == 0:
        return "$0.00"
    elif cost < Decimal("0.01"):
        # Show more precision for very small amounts
        return f"${cost:.6f}".rstrip("0").rstrip(".")
    else:
        # Standard currency format for larger amounts
        return f"${cost:.2f}"


def get_supported_models() -> list[str]:
    """Get list of models with pricing information."""
    return list(OPENAI_PRICING.keys())
