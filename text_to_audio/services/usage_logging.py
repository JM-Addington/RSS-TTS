"""Utility functions for logging API usage across services."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def log_openai_usage(
    user,
    article,
    operation: str,
    tokens_used: int,
    processing_time_ms: int,
    word_count: int,
    operation_type: str = "LLM",
    model_name: str = "gpt-4o-mini",
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    tts_provider: Optional[str] = None,
):
    """
    Log API usage to the OpenAIUsageStats model with cost calculation.

    Note: Function name retained for backwards compatibility, but this function
    logs usage for all providers (OpenAI, Google, etc.).

    This is a centralized function that can be used by all services
    to consistently log their API usage and calculate costs.

    Args:
        user: The user who made the request
        article: The article being processed
        operation: Description of the operation (e.g., "Content Analysis")
        tokens_used: Number of tokens consumed (for backwards compatibility)
        processing_time_ms: Processing time in milliseconds
        word_count: Number of words processed
        operation_type: Type of operation (LLM, TTS, etc.) for logging
        model_name: Name of the model/voice used
        input_tokens: Number of input tokens (if available)
        output_tokens: Number of output tokens (if available)
        tts_provider: Provider for TTS operations ("openai" or "google")
    """
    try:
        from django.db import transaction

        from ..models import OpenAIUsageStats
        from .cost_calculator import (
            calculate_llm_cost,
            calculate_tts_cost,
            estimate_cost_from_total_tokens,
        )

        # Determine provider - for TTS use tts_provider, for LLM default to "openai"
        provider = tts_provider if operation_type == "TTS" else "openai"
        provider = provider or "openai"  # Ensure we always have a value

        # Calculate cost
        estimated_cost = None
        if operation_type == "LLM":
            if input_tokens is not None and output_tokens is not None:
                estimated_cost = calculate_llm_cost(
                    model_name, input_tokens, output_tokens
                )
            elif tokens_used:
                estimated_cost = estimate_cost_from_total_tokens(
                    model_name, tokens_used
                )
        elif operation_type == "TTS":
            # For TTS, tokens_used contains character count
            # Pass provider for accurate Google TTS pricing
            estimated_cost = calculate_tts_cost(model_name, tokens_used, provider)

        # Use transaction.atomic to ensure DB operations are isolated
        with transaction.atomic():
            usage_stats = OpenAIUsageStats.objects.create(
                user=user,
                article=article,
                tokens_used=tokens_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                processing_time_ms=processing_time_ms,
                word_count=word_count,
                operation_type=operation_type,
                model_name=model_name,
                provider=provider,
                estimated_cost=estimated_cost,
            )

            cost_str = f", cost=${estimated_cost}" if estimated_cost else ""
            # Include provider in log for TTS operations
            provider_str = f", provider={provider}" if operation_type == "TTS" else ""
            logger.info(
                f"{operation_type} usage logged: {operation} - "
                f"model={model_name}, tokens={tokens_used}, "
                f"time={processing_time_ms}ms, words={word_count}{cost_str}{provider_str}, "
                f"user={getattr(user, 'username', 'unknown')}"
            )

            return usage_stats

    except Exception as exc:
        logger.error(f"Failed to log {operation_type} usage for {operation}: {exc}")
        return None
