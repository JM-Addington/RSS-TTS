"""Cost calculation utilities for TTS and LLM API usage."""

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# AIDEV-NOTE: TTS pricing per million characters, LLM pricing per million tokens
# Sources: https://openai.com/api/pricing/, https://cloud.google.com/text-to-speech/pricing

# OpenAI pricing per million tokens (as of 2025-01)
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
    "gpt-4o-2024-08-06": {
        "input": Decimal("2.50"),
        "output": Decimal("10.00"),
    },
    "gpt-4o-mini-2024-07-18": {
        "input": Decimal("0.150"),
        "output": Decimal("0.600"),
    },
    "chatgpt-4o-latest": {
        "input": Decimal("5.00"),  # $5.00 per million input tokens
        "output": Decimal("15.00"),  # $15.00 per million output tokens
    },
    # GPT-4.x models
    "gpt-4.5": {
        "input": Decimal("75.00"),  # $75.00 per million input tokens
        "output": Decimal("150.00"),  # $150.00 per million output tokens
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
    # O1 models
    "o1": {
        "input": Decimal("15.00"),  # $15.00 per million input tokens
        "output": Decimal("60.00"),  # $60.00 per million output tokens
    },
    "o1-preview": {
        "input": Decimal("15.00"),  # $15.00 per million input tokens
        "output": Decimal("60.00"),  # $60.00 per million output tokens
    },
    "o1-pro": {
        "input": Decimal("150.00"),  # $150.00 per million input tokens
        "output": Decimal("600.00"),  # $600.00 per million output tokens
    },
    "o1-mini": {
        "input": Decimal("1.10"),  # $1.10 per million input tokens
        "output": Decimal("4.40"),  # $4.40 per million output tokens
    },
    # TTS models - pricing per million characters
    "tts-1": {
        "input": Decimal("15.00"),  # $15.00 per million characters
        "output": Decimal("0"),  # No output tokens for TTS
    },
    "tts-1-hd": {
        "input": Decimal("30.00"),  # $30.00 per million characters
        "output": Decimal("0"),  # No output tokens for TTS
    },
    # gpt-4o-mini-tts uses token-based pricing (~$0.015/minute, ~$12.60/million chars)
    "gpt-4o-mini-tts": {
        "input": Decimal("12.60"),  # ~$12.60 per million characters (estimated)
        "output": Decimal("0"),  # No output tokens for TTS
    },
}

# Google Cloud TTS pricing per million characters (as of 2025-01)
# Source: https://cloud.google.com/text-to-speech/pricing
GOOGLE_TTS_PRICING = {
    # Standard voices - basic quality
    "standard": {
        "input": Decimal("4.00"),  # $4.00 per million characters
        "output": Decimal("0"),
    },
    # WaveNet voices - high quality neural synthesis
    "wavenet": {
        "input": Decimal("16.00"),  # $16.00 per million characters
        "output": Decimal("0"),
    },
    # Neural2 voices - improved neural synthesis
    "neural2": {
        "input": Decimal("16.00"),  # $16.00 per million characters
        "output": Decimal("0"),
    },
    # Journey voices - experimental (currently free)
    "journey": {
        "input": Decimal("0.00"),  # Free during experimental phase
        "output": Decimal("0"),
    },
    # Chirp3-HD voices - high-definition voices
    "chirp3": {
        "input": Decimal("16.00"),  # $16.00 per million characters (Neural2 tier)
        "output": Decimal("0"),
    },
    # Gemini AI Studio TTS voices - supports prompts
    "gemini": {
        "input": Decimal("16.00"),  # $16.00 per million characters (estimated)
        "output": Decimal("0"),
    },
    # Studio voices - premium quality
    "studio": {
        "input": Decimal("160.00"),  # $160.00 per million characters
        "output": Decimal("0"),
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


def _get_google_tts_voice_type(voice_name: str) -> str:
    """Determine Google TTS voice type from voice name.

    Args:
        voice_name: Full voice name (e.g., "en-US-Journey-D", "Kore")

    Returns:
        Voice type key for GOOGLE_TTS_PRICING
    """
    voice_lower = voice_name.lower()

    # Check for specific voice type prefixes in full voice names
    if "journey" in voice_lower:
        return "journey"
    elif "chirp3-hd" in voice_lower or "chirp3" in voice_lower:
        return "chirp3"
    elif "neural2" in voice_lower:
        return "neural2"
    elif "wavenet" in voice_lower:
        return "wavenet"
    elif "studio" in voice_lower:
        return "studio"
    elif "standard" in voice_lower:
        return "standard"

    # Check for Gemini short voice names (AI Studio voices)
    # These are single-word names like Kore, Charon, Fenrir, etc.
    gemini_voices = {
        "achernar",
        "aoede",
        "autonoe",
        "callirrhoe",
        "despina",
        "erinome",
        "gacrux",
        "kore",
        "laomedeia",
        "leda",
        "pulcherrima",
        "sulafat",
        "vindemiatrix",
        "zephyr",
        "achird",
        "algenib",
        "algieba",
        "alnilam",
        "charon",
        "enceladus",
        "fenrir",
        "iapetus",
        "orus",
        "puck",
        "rasalgethi",
        "sadachbia",
        "sadaltager",
        "schedar",
        "umbriel",
        "zubenelgenubi",
    }
    if voice_lower in gemini_voices:
        return "gemini"

    # Default to neural2 for unknown Google voices
    return "neural2"


def calculate_tts_cost(
    model_name: str, character_count: int, provider: str = "openai"
) -> Decimal:
    """
    Calculate the cost of a TTS API call.

    Args:
        model_name: Name of the TTS model or voice used
        character_count: Number of characters processed
        provider: TTS provider ("openai" or "google")

    Returns:
        Estimated cost in USD as a Decimal
    """
    # Handle Google TTS provider
    if provider == "google":
        voice_type = _get_google_tts_voice_type(model_name)
        if voice_type in GOOGLE_TTS_PRICING:
            pricing = GOOGLE_TTS_PRICING[voice_type]
            logger.debug(f"Using Google TTS pricing for voice type '{voice_type}'")
        else:
            pricing = GOOGLE_TTS_PRICING["neural2"]
            logger.warning(
                f"Unknown Google TTS voice type for '{model_name}', using neural2 pricing"
            )
    # Handle OpenAI TTS provider
    elif model_name in OPENAI_PRICING:
        pricing = OPENAI_PRICING[model_name]
    else:
        pricing = OPENAI_PRICING["tts-1"]
        logger.warning(f"Unknown TTS model {model_name}, using tts-1 pricing")

    # TTS models are priced per character
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
