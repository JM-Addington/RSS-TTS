"""Utility functions for logging OpenAI API usage across services."""

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
    output_tokens: Optional[int] = None
):
    """
    Log OpenAI API usage to the OpenAIUsageStats model with cost calculation.

    This is a centralized function that can be used by all services
    to consistently log their API usage and calculate costs.

    Args:
        user: The user who made the request
        article: The article being processed
        operation: Description of the operation (e.g., "Chunk Tone Analysis")
        tokens_used: Number of tokens consumed (for backwards compatibility)
        processing_time_ms: Processing time in milliseconds
        word_count: Number of words processed
        operation_type: Type of operation (LLM, TTS, etc.) for logging
        model_name: Name of the OpenAI model used
        input_tokens: Number of input tokens (if available)
        output_tokens: Number of output tokens (if available)
    """
    try:
        from django.db import transaction
        from ..models import OpenAIUsageStats
        from .cost_calculator import calculate_llm_cost, estimate_cost_from_total_tokens

        # Calculate cost
        estimated_cost = None
        if operation_type == "LLM":
            if input_tokens is not None and output_tokens is not None:
                estimated_cost = calculate_llm_cost(model_name, input_tokens, output_tokens)
            elif tokens_used:
                estimated_cost = estimate_cost_from_total_tokens(model_name, tokens_used)

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
                estimated_cost=estimated_cost,
            )

            cost_str = f", cost=${estimated_cost}" if estimated_cost else ""
            logger.info(
                f"{operation_type} usage logged: {operation} - "
                f"model={model_name}, tokens={tokens_used}, "
                f"time={processing_time_ms}ms, words={word_count}{cost_str}, "
                f"user={getattr(user, 'username', 'unknown')}"
            )

            return usage_stats

    except Exception as exc:
        logger.error(
            f"Failed to log {operation_type} usage for {operation}: {exc}"
        )


class UsageLogger:
    """
    A helper class for services to log their OpenAI usage.

    This provides a clean interface for services to report usage
    without tight coupling to the Article model.
    """

    def __init__(self, user, article, operation_prefix: str):
        """
        Initialize usage logger for a specific context.

        Args:
            user: The user context for logging
            article: The article context for logging
            operation_prefix: Prefix for operation names (e.g., "ChunkTone")
        """
        self.user = user
        self.article = article
        self.operation_prefix = operation_prefix

    def log_llm_usage(
        self,
        operation: str,
        tokens_used: int,
        processing_time_ms: int,
        word_count: int,
        model_name: str = "gpt-4o-mini",
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None
    ):
        """Log LLM API usage with cost tracking."""
        full_operation = f"{self.operation_prefix} {operation}"
        return log_openai_usage(
            user=self.user,
            article=self.article,
            operation=full_operation,
            tokens_used=tokens_used,
            processing_time_ms=processing_time_ms,
            word_count=word_count,
            operation_type="LLM",
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )

    def log_tts_usage(
        self,
        operation: str,
        character_count: int,
        processing_time_ms: int,
        model_name: str = "tts-1"
    ):
        """Log TTS API usage with cost tracking."""
        full_operation = f"{self.operation_prefix} {operation}"
        return log_openai_usage(
            user=self.user,
            article=self.article,
            operation=full_operation,
            tokens_used=character_count,  # Store character count in tokens_used for TTS
            processing_time_ms=processing_time_ms,
            word_count=0,  # TTS doesn't have word count
            operation_type="TTS",
            model_name=model_name
        )
