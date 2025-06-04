"""Tests for cost tracking functionality."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from text_to_audio.models import Article, Feed, OpenAIUsageStats
from text_to_audio.services.cost_calculator import (
    calculate_llm_cost,
    calculate_tts_cost,
    estimate_cost_from_total_tokens,
    format_cost_display,
    get_supported_models,
)
from text_to_audio.services.usage_logging import UsageLogger, log_openai_usage

User = get_user_model()


class CostCalculatorTests(TestCase):
    """Test cost calculation utilities."""

    def test_calculate_llm_cost_gpt_4o_mini(self):
        """Test cost calculation for gpt-4o-mini."""
        cost = calculate_llm_cost("gpt-4o-mini", 1000, 500)
        # (1000 * 0.150 + 500 * 0.600) / 1000000 = 0.000450
        expected = Decimal("0.000450")
        self.assertEqual(cost, expected)

    def test_calculate_llm_cost_gpt_4o(self):
        """Test cost calculation for gpt-4o."""
        cost = calculate_llm_cost("gpt-4o", 1000, 500)
        # (1000 * 2.50 + 500 * 10.00) / 1000000 = 0.007500
        expected = Decimal("0.007500")
        self.assertEqual(cost, expected)

    def test_calculate_llm_cost_unknown_model(self):
        """Test cost calculation for unknown model falls back to gpt-4o-mini."""
        cost = calculate_llm_cost("unknown-model", 1000, 500)
        # Should use gpt-4o-mini pricing
        expected = Decimal("0.000450")
        self.assertEqual(cost, expected)

    def test_calculate_tts_cost(self):
        """Test TTS cost calculation."""
        cost = calculate_tts_cost("tts-1", 10000)  # 10k characters
        # 10000 * 15.00 / 1000000 = 0.150000
        expected = Decimal("0.150000")
        self.assertEqual(cost, expected)

    def test_estimate_cost_from_total_tokens(self):
        """Test cost estimation from total tokens only."""
        cost = estimate_cost_from_total_tokens("gpt-4o-mini", 1000, input_ratio=0.8)
        # 800 input tokens, 200 output tokens
        # (800 * 0.150 + 200 * 0.600) / 1000000 = 0.000240
        expected = Decimal("0.000240")
        self.assertEqual(cost, expected)

    def test_format_cost_display(self):
        """Test cost formatting for display."""
        self.assertEqual(format_cost_display(Decimal("0")), "$0.00")
        self.assertEqual(format_cost_display(Decimal("0.001234")), "$0.001234")
        self.assertEqual(format_cost_display(Decimal("1.23")), "$1.23")
        self.assertEqual(format_cost_display(Decimal("0.100000")), "$0.10")

    def test_get_supported_models(self):
        """Test getting list of supported models."""
        models = get_supported_models()
        self.assertIn("gpt-4o-mini", models)
        self.assertIn("gpt-4o", models)
        self.assertIn("tts-1", models)


class UsageLoggingTests(TestCase):
    """Test usage logging with cost calculation."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed, title="Test Article", text_content="This is a test article."
        )

    def test_log_openai_usage_with_precise_tokens(self):
        """Test logging usage with precise input/output tokens."""
        usage_stats = log_openai_usage(
            user=self.user,
            article=self.article,
            operation="Test Operation",
            tokens_used=1500,
            processing_time_ms=2000,
            word_count=100,
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

    def test_log_openai_usage_total_tokens_only(self):
        """Test logging usage with only total tokens."""
        usage_stats = log_openai_usage(
            user=self.user,
            article=self.article,
            operation="Test Operation",
            tokens_used=1000,
            processing_time_ms=1500,
            word_count=50,
            model_name="gpt-4o-mini",
        )

        self.assertIsNotNone(usage_stats)
        self.assertEqual(usage_stats.tokens_used, 1000)
        self.assertIsNone(usage_stats.input_tokens)
        self.assertIsNone(usage_stats.output_tokens)
        self.assertIsNotNone(usage_stats.estimated_cost)
        # Should estimate with 75% input, 25% output
        expected = Decimal(
            "0.000263"
        )  # Actual calculation: (750*0.150 + 250*0.600)/1000000
        self.assertEqual(usage_stats.estimated_cost, expected)

    def test_usage_logger_log_llm_usage(self):
        """Test UsageLogger.log_llm_usage method."""
        logger = UsageLogger(self.user, self.article, "Test")

        usage_stats = logger.log_llm_usage(
            operation="Content Analysis",
            tokens_used=800,
            processing_time_ms=1200,
            word_count=40,
            model_name="gpt-4o",
            input_tokens=600,
            output_tokens=200,
        )

        self.assertIsNotNone(usage_stats)
        self.assertEqual(usage_stats.model_name, "gpt-4o")
        self.assertEqual(usage_stats.input_tokens, 600)
        self.assertEqual(usage_stats.output_tokens, 200)
        # gpt-4o: (600 * 2.50 + 200 * 10.00) / 1000000 = 0.003500
        self.assertEqual(usage_stats.estimated_cost, Decimal("0.003500"))

    def test_usage_logger_log_tts_usage(self):
        """Test UsageLogger.log_tts_usage method."""
        logger = UsageLogger(self.user, self.article, "TTS")

        usage_stats = logger.log_tts_usage(
            operation="Speech Generation",
            character_count=5000,
            processing_time_ms=3000,
            model_name="tts-1",
        )

        self.assertIsNotNone(usage_stats)
        self.assertEqual(usage_stats.operation_type, "TTS")
        self.assertEqual(usage_stats.model_name, "tts-1")
        self.assertEqual(
            usage_stats.tokens_used, 5000
        )  # Character count stored as tokens
        self.assertEqual(usage_stats.word_count, 0)  # No word count for TTS


class OpenAIUsageStatsModelTests(TestCase):
    """Test OpenAIUsageStats model functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed, title="Test Article", text_content="This is a test article."
        )

    def test_calculate_cost_with_precise_tokens(self):
        """Test calculate_cost method with precise input/output tokens."""
        usage = OpenAIUsageStats.objects.create(
            user=self.user,
            article=self.article,
            tokens_used=1000,
            input_tokens=700,
            output_tokens=300,
            processing_time_ms=1500,
            word_count=50,
            model_name="gpt-4o-mini",
            operation_type="LLM",
        )

        usage.calculate_cost()
        usage.refresh_from_db()

        # (700 * 0.150 + 300 * 0.600) / 1000000 = 0.000285
        expected = Decimal("0.000285")
        self.assertEqual(usage.estimated_cost, expected)

    def test_calculate_cost_fallback_to_total_tokens(self):
        """Test calculate_cost method falling back to total tokens."""
        usage = OpenAIUsageStats.objects.create(
            user=self.user,
            article=self.article,
            tokens_used=1000,
            processing_time_ms=1500,
            word_count=50,
            model_name="gpt-4o-mini",
            operation_type="LLM",
        )

        usage.calculate_cost()
        usage.refresh_from_db()

        self.assertIsNotNone(usage.estimated_cost)
        # Should estimate with default 75% input, 25% output

    def test_str_representation_with_cost(self):
        """Test string representation includes cost when available."""
        usage = OpenAIUsageStats.objects.create(
            user=self.user,
            article=self.article,
            tokens_used=1000,
            processing_time_ms=1500,
            word_count=50,
            model_name="gpt-4o-mini",
            operation_type="LLM",
            estimated_cost=Decimal("0.001234"),
        )

        str_repr = str(usage)
        self.assertIn("testuser", str_repr)
        self.assertIn("LLM usage", str_repr)
        self.assertIn("($0.001234)", str_repr)


class CostTrackingViewTests(TestCase):
    """Test cost tracking views."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed, title="Test Article", text_content="This is a test article."
        )
        self.client = Client()

    def test_usage_dashboard_requires_login(self):
        """Test that usage dashboard requires authentication."""
        url = reverse("usage-dashboard")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_usage_dashboard_authenticated(self):
        """Test usage dashboard for authenticated user."""
        self.client.force_login(self.user)

        # Create some usage data
        OpenAIUsageStats.objects.create(
            user=self.user,
            article=self.article,
            tokens_used=1000,
            processing_time_ms=1500,
            word_count=50,
            model_name="gpt-4o-mini",
            operation_type="LLM",
            estimated_cost=Decimal("0.001000"),
        )

        url = reverse("usage-dashboard")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Usage Dashboard")
        self.assertContains(response, "$0.001")  # Should show cost
        self.assertContains(response, "gpt-4o-mini")

    def test_article_cost_detail_view(self):
        """Test article cost detail view."""
        self.client.force_login(self.user)

        # Create usage data for the article
        OpenAIUsageStats.objects.create(
            user=self.user,
            article=self.article,
            tokens_used=1000,
            input_tokens=700,
            output_tokens=300,
            processing_time_ms=1500,
            word_count=50,
            model_name="gpt-4o-mini",
            operation_type="LLM",
            estimated_cost=Decimal("0.000285"),
        )

        url = reverse("article-cost-detail", kwargs={"article_id": self.article.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cost Details")
        self.assertContains(response, self.article.title)
        self.assertContains(response, "$0.000285")
        self.assertContains(response, "gpt-4o-mini")

    def test_article_cost_detail_unauthorized(self):
        """Test article cost detail view for unauthorized user."""
        other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass123"
        )
        self.client.force_login(other_user)

        url = reverse("article-cost-detail", kwargs={"article_id": self.article.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Article not found or access denied")


class CostTrackingIntegrationTests(TestCase):
    """Integration tests for cost tracking functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed, title="Test Article", text_content="This is a test article."
        )

    def test_end_to_end_cost_tracking(self):
        """Test complete cost tracking flow."""
        # Create usage logger
        usage_logger = UsageLogger(self.user, self.article, "Integration")

        # Log some LLM usage
        llm_usage = usage_logger.log_llm_usage(
            operation="Content Analysis",
            tokens_used=2000,
            processing_time_ms=3000,
            word_count=100,
            model_name="gpt-4o",
            input_tokens=1500,
            output_tokens=500,
        )

        # Log some TTS usage
        tts_usage = usage_logger.log_tts_usage(
            operation="Speech Generation",
            character_count=8000,
            processing_time_ms=5000,
            model_name="tts-1",
        )

        # Verify data was logged correctly
        self.assertEqual(OpenAIUsageStats.objects.filter(user=self.user).count(), 2)

        # Verify LLM cost calculation
        self.assertIsNotNone(llm_usage.estimated_cost)
        # gpt-4o: (1500 * 2.50 + 500 * 10.00) / 1000000 = 0.008750
        self.assertEqual(llm_usage.estimated_cost, Decimal("0.008750"))

        # Verify TTS record
        self.assertEqual(tts_usage.operation_type, "TTS")
        self.assertEqual(tts_usage.tokens_used, 8000)  # Character count

        # Test dashboard aggregation
        from django.db.models import Sum

        total_stats = OpenAIUsageStats.objects.filter(user=self.user).aggregate(
            total_cost=Sum("estimated_cost")
        )

        # Should include LLM cost (TTS cost calculation not yet implemented)
        self.assertGreaterEqual(total_stats["total_cost"], Decimal("0.008750"))

    def test_migration_of_existing_usage_records(self):
        """Test that existing usage records can have costs calculated."""
        # Create an old-style usage record without cost data
        old_usage = OpenAIUsageStats.objects.create(
            user=self.user,
            article=self.article,
            tokens_used=1000,
            processing_time_ms=1500,
            word_count=50,
            model_name="gpt-4o-mini",
            operation_type="LLM",
            # No estimated_cost, input_tokens, or output_tokens
        )

        # Calculate cost for the record
        old_usage.calculate_cost()
        old_usage.refresh_from_db()

        # Should now have estimated cost
        self.assertIsNotNone(old_usage.estimated_cost)
        self.assertGreater(old_usage.estimated_cost, Decimal("0"))
