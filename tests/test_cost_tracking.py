"""Tests for cost tracking functionality."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from text_to_audio.models import Article, Feed, OpenAIUsageStats
from text_to_audio.services.cost_calculator import (
    calculate_llm_cost,
    calculate_tts_cost,
    estimate_cost_from_total_tokens,
    format_cost_display,
)
from text_to_audio.services.usage_logging import log_openai_usage

User = get_user_model()


class CostCalculatorTests(TestCase):
    """Tests for the cost calculator service."""

    def test_calculate_llm_cost_gpt4o(self):
        """Test cost calculation for GPT-4o model."""
        cost = calculate_llm_cost("gpt-4o", input_tokens=1000, output_tokens=500)
        # Expected: (1000 * 2.50 / 1,000,000) + (500 * 10.00 / 1,000,000)
        # = 0.0025 + 0.005 = 0.0075
        self.assertEqual(cost, Decimal("0.007500"))

    def test_calculate_llm_cost_gpt4o_mini(self):
        """Test cost calculation for GPT-4o-mini model."""
        cost = calculate_llm_cost("gpt-4o-mini", input_tokens=1000, output_tokens=500)
        # Expected: (1000 * 0.150 / 1,000,000) + (500 * 0.600 / 1,000,000)
        # = 0.00015 + 0.0003 = 0.00045
        self.assertEqual(cost, Decimal("0.000450"))

    def test_calculate_llm_cost_unknown_model(self):
        """Test cost calculation falls back to default for unknown model."""
        cost = calculate_llm_cost("unknown-model", input_tokens=1000, output_tokens=500)
        # Should use gpt-4o-mini pricing as default
        self.assertEqual(cost, Decimal("0.000450"))

    def test_calculate_tts_cost(self):
        """Test cost calculation for TTS models."""
        # Test tts-1
        cost = calculate_tts_cost("tts-1", character_count=1000)
        # Expected: 1000 * 15.00 / 1,000,000 = 0.015
        self.assertEqual(cost, Decimal("0.015000"))

        # Test tts-1-hd
        cost = calculate_tts_cost("tts-1-hd", character_count=1000)
        # Expected: 1000 * 30.00 / 1,000,000 = 0.030
        self.assertEqual(cost, Decimal("0.030000"))

    def test_estimate_cost_from_total_tokens(self):
        """Test cost estimation when only total tokens are available."""
        # Default 75% input, 25% output
        cost = estimate_cost_from_total_tokens("gpt-4o-mini", total_tokens=1000)
        # Expected: 750 input + 250 output
        # = (750 * 0.150 / 1,000,000) + (250 * 0.600 / 1,000,000)
        # = 0.0001125 + 0.00015 = 0.0002625
        self.assertEqual(cost, Decimal("0.000263"))  # Rounded to 6 decimal places

    def test_format_cost_display(self):
        """Test cost formatting for display."""
        self.assertEqual(format_cost_display(Decimal("0")), "$0.00")
        self.assertEqual(format_cost_display(Decimal("0.001234")), "$0.001234")
        self.assertEqual(format_cost_display(Decimal("0.001200")), "$0.0012")
        self.assertEqual(format_cost_display(Decimal("1.234567")), "$1.23")
        self.assertEqual(format_cost_display(Decimal("10.00")), "$10.00")


class UsageLoggingTests(TestCase):
    """Tests for the usage logging service."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed,
            title="Test Article",
            text_content="Test content for cost tracking.",
            status=Article.PROCESSING,
        )

    def test_log_openai_usage_llm_with_precise_tokens(self):
        """Test logging LLM usage with input/output tokens."""
        usage_stats = log_openai_usage(
            user=self.user,
            article=self.article,
            operation="Test LLM Operation",
            tokens_used=1500,  # Total for backwards compatibility
            processing_time_ms=1000,
            word_count=100,
            operation_type="LLM",
            model_name="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=500,
        )

        self.assertIsNotNone(usage_stats)
        self.assertEqual(usage_stats.user, self.user)
        self.assertEqual(usage_stats.article, self.article)
        self.assertEqual(usage_stats.tokens_used, 1500)
        self.assertEqual(usage_stats.input_tokens, 1000)
        self.assertEqual(usage_stats.output_tokens, 500)
        self.assertEqual(usage_stats.model_name, "gpt-4o-mini")
        self.assertEqual(usage_stats.operation_type, "LLM")
        self.assertIsNotNone(usage_stats.estimated_cost)
        self.assertEqual(usage_stats.estimated_cost, Decimal("0.000450"))

    def test_log_openai_usage_llm_total_tokens_only(self):
        """Test logging LLM usage with only total tokens."""
        usage_stats = log_openai_usage(
            user=self.user,
            article=self.article,
            operation="Test LLM Operation",
            tokens_used=1000,
            processing_time_ms=500,
            word_count=50,
            operation_type="LLM",
            model_name="gpt-4o",
        )

        self.assertIsNotNone(usage_stats)
        self.assertEqual(usage_stats.tokens_used, 1000)
        self.assertIsNone(usage_stats.input_tokens)
        self.assertIsNone(usage_stats.output_tokens)
        self.assertEqual(usage_stats.model_name, "gpt-4o")
        self.assertIsNotNone(usage_stats.estimated_cost)
        # With 75% input ratio: 750 input, 250 output
        # (750 * 2.50 / 1,000,000) + (250 * 10.00 / 1,000,000) = 0.001875 + 0.0025 = 0.004375
        expected = Decimal("0.004375")
        self.assertEqual(usage_stats.estimated_cost, expected)

    def test_log_openai_usage_tts(self):
        """Test logging TTS usage."""
        usage_stats = log_openai_usage(
            user=self.user,
            article=self.article,
            operation="Test TTS Operation",
            tokens_used=5000,  # Character count for TTS
            processing_time_ms=2000,
            word_count=0,  # TTS doesn't have word count
            operation_type="TTS",
            model_name="tts-1",
        )

        self.assertIsNotNone(usage_stats)
        self.assertEqual(usage_stats.operation_type, "TTS")
        self.assertEqual(usage_stats.model_name, "tts-1")
        self.assertEqual(usage_stats.tokens_used, 5000)
        self.assertIsNotNone(usage_stats.estimated_cost)
        # 5000 * 15.00 / 1,000,000 = 0.075
        self.assertEqual(usage_stats.estimated_cost, Decimal("0.075000"))

    def test_log_openai_usage_without_article(self):
        """Test logging usage without an article context."""
        usage_stats = log_openai_usage(
            user=self.user,
            article=None,
            operation="Test Operation Without Article",
            tokens_used=100,
            processing_time_ms=100,
            word_count=10,
            operation_type="LLM",
            model_name="gpt-4o-mini",
        )

        self.assertIsNotNone(usage_stats)
        self.assertIsNone(usage_stats.article)
        self.assertEqual(usage_stats.user, self.user)
