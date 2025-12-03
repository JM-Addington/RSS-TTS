# flake8: noqa
# mypy: ignore-errors
"""Tests for cost analytics views."""

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from text_to_audio.models import Article, Feed, OpenAIUsageStats

User = get_user_model()


class CostAnalyticsViewTests(TestCase):
    """Tests for the cost analytics dashboard view."""

    def setUp(self):
        """Create users, feeds, articles, and usage stats for tests."""
        # Create two users
        self.user1 = User.objects.create_user(
            username="costuser1", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="costuser2", password="testpass123"
        )

        # Create feeds for user1
        self.feed1 = Feed.objects.create(
            user=self.user1, name="Tech Feed", tts_provider="openai"
        )
        self.feed2 = Feed.objects.create(
            user=self.user1, name="News Feed", tts_provider="google"
        )

        # Create articles
        self.article1 = Article.objects.create(
            feed=self.feed1,
            title="Tech Article 1",
            status=Article.COMPLETED,
            tts_provider="openai",
        )
        self.article2 = Article.objects.create(
            feed=self.feed1,
            title="Tech Article 2",
            status=Article.COMPLETED,
            tts_provider="openai",
        )
        self.article3 = Article.objects.create(
            feed=self.feed2,
            title="News Article 1",
            status=Article.COMPLETED,
            tts_provider="google",
        )

        # Create usage stats with different dates, providers, and models
        now = timezone.now()

        # User1 - LLM usage
        OpenAIUsageStats.objects.create(
            user=self.user1,
            article=self.article1,
            tokens_used=1000,
            input_tokens=800,
            output_tokens=200,
            model_name="gpt-4o-mini",
            operation_type="LLM",
            provider="openai",
            estimated_cost=Decimal("0.000240"),
            processing_time_ms=500,
            word_count=100,
            request_timestamp=now - timedelta(days=1),
        )

        # User1 - OpenAI TTS usage
        OpenAIUsageStats.objects.create(
            user=self.user1,
            article=self.article1,
            tokens_used=5000,
            model_name="tts-1-hd",
            operation_type="TTS",
            provider="openai",
            estimated_cost=Decimal("0.150000"),
            processing_time_ms=2000,
            word_count=1000,
            request_timestamp=now - timedelta(days=1),
        )

        # User1 - Google TTS usage (different feed)
        OpenAIUsageStats.objects.create(
            user=self.user1,
            article=self.article3,
            tokens_used=3000,
            model_name="en-US-Chirp3-HD-Acacia",
            operation_type="TTS",
            provider="google",
            estimated_cost=Decimal("0.048000"),
            processing_time_ms=1500,
            word_count=600,
            request_timestamp=now - timedelta(days=2),
        )

        # User1 - Older usage (7 days ago)
        OpenAIUsageStats.objects.create(
            user=self.user1,
            article=self.article2,
            tokens_used=2000,
            model_name="tts-1",
            operation_type="TTS",
            provider="openai",
            estimated_cost=Decimal("0.030000"),
            processing_time_ms=1000,
            word_count=400,
            request_timestamp=now - timedelta(days=7),
        )

        # User2 - Should not appear in user1's dashboard
        self.user2_feed = Feed.objects.create(user=self.user2, name="User2 Feed")
        self.user2_article = Article.objects.create(
            feed=self.user2_feed,
            title="User2 Article",
            status=Article.COMPLETED,
        )
        OpenAIUsageStats.objects.create(
            user=self.user2,
            article=self.user2_article,
            tokens_used=10000,
            model_name="tts-1-hd",
            operation_type="TTS",
            provider="openai",
            estimated_cost=Decimal("0.300000"),
            processing_time_ms=5000,
            word_count=2000,
            request_timestamp=now,
        )

        self.client = Client()

    def test_cost_analytics_requires_login(self):
        """Test that cost analytics page requires authentication."""
        response = self.client.get(reverse("cost-analytics"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_cost_analytics_renders_for_authenticated_user(self):
        """Test that authenticated users can access the page."""
        self.client.login(username="costuser1", password="testpass123")
        response = self.client.get(reverse("cost-analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "text_to_audio/cost_analytics.html")

    def test_cost_analytics_shows_total_cost(self):
        """Test that total cost is calculated correctly for user."""
        self.client.login(username="costuser1", password="testpass123")
        response = self.client.get(reverse("cost-analytics"))

        # User1's total cost: 0.000240 + 0.150000 + 0.048000 + 0.030000 = 0.228240
        self.assertIn("total_cost", response.context)
        expected_total = Decimal("0.228240")
        self.assertEqual(response.context["total_cost"], expected_total)

    def test_cost_analytics_shows_costs_by_provider(self):
        """Test that costs are grouped by TTS provider."""
        self.client.login(username="costuser1", password="testpass123")
        response = self.client.get(reverse("cost-analytics"))

        self.assertIn("costs_by_provider", response.context)
        costs_by_provider = {
            item["provider"]: item["total"]
            for item in response.context["costs_by_provider"]
        }

        # Should have both Openai and Google (capitalized by view)
        # OpenAI: LLM 0.000240 + TTS 0.150000 + TTS 0.030000 = 0.180240
        # Google: TTS 0.048000
        self.assertIn("Openai", costs_by_provider)
        self.assertIn("Google", costs_by_provider)
        self.assertEqual(costs_by_provider["Openai"], Decimal("0.180240"))
        self.assertEqual(costs_by_provider["Google"], Decimal("0.048000"))

    def test_cost_analytics_shows_costs_by_model(self):
        """Test that costs are grouped by model."""
        self.client.login(username="costuser1", password="testpass123")
        response = self.client.get(reverse("cost-analytics"))

        self.assertIn("costs_by_model", response.context)
        costs_by_model = response.context["costs_by_model"]

        # Should have entries for gpt-4o-mini, tts-1-hd, tts-1, and chirp voice
        model_names = [item["model_name"] for item in costs_by_model]
        self.assertIn("tts-1-hd", model_names)
        self.assertIn("tts-1", model_names)

    def test_cost_analytics_shows_costs_by_feed(self):
        """Test that costs are grouped by feed."""
        self.client.login(username="costuser1", password="testpass123")
        response = self.client.get(reverse("cost-analytics"))

        self.assertIn("costs_by_feed", response.context)
        costs_by_feed = response.context["costs_by_feed"]

        # Should have entries for Tech Feed and News Feed
        feed_names = [item["feed_name"] for item in costs_by_feed]
        self.assertIn("Tech Feed", feed_names)
        self.assertIn("News Feed", feed_names)

    def test_cost_analytics_shows_costs_over_time(self):
        """Test that daily costs are calculated."""
        self.client.login(username="costuser1", password="testpass123")
        response = self.client.get(reverse("cost-analytics"))

        self.assertIn("costs_over_time", response.context)
        costs_over_time = response.context["costs_over_time"]

        # Should have multiple days of data
        self.assertGreater(len(costs_over_time), 0)

    def test_cost_analytics_only_shows_user_data(self):
        """Test that users only see their own usage data."""
        self.client.login(username="costuser1", password="testpass123")
        response = self.client.get(reverse("cost-analytics"))

        # User1's total should NOT include User2's $0.30
        total_cost = response.context["total_cost"]
        self.assertLess(total_cost, Decimal("0.30"))

    def test_cost_analytics_date_filter_30_days(self):
        """Test date filtering for 30 days."""
        self.client.login(username="costuser1", password="testpass123")
        response = self.client.get(reverse("cost-analytics") + "?days=30")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_days"], 30)

    def test_cost_analytics_date_filter_7_days(self):
        """Test date filtering for 7 days."""
        self.client.login(username="costuser1", password="testpass123")
        response = self.client.get(reverse("cost-analytics") + "?days=7")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_days"], 7)

    def test_cost_analytics_date_filter_all_time(self):
        """Test showing all time costs."""
        self.client.login(username="costuser1", password="testpass123")
        response = self.client.get(reverse("cost-analytics") + "?days=0")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_days"], 0)

    def test_cost_analytics_shows_operation_type_breakdown(self):
        """Test that LLM and TTS costs are shown separately."""
        self.client.login(username="costuser1", password="testpass123")
        response = self.client.get(reverse("cost-analytics"))

        self.assertIn("costs_by_operation", response.context)
        costs_by_op = {
            item["operation_type"]: item["total"]
            for item in response.context["costs_by_operation"]
        }

        # Should have both LLM and TTS
        self.assertIn("LLM", costs_by_op)
        self.assertIn("TTS", costs_by_op)


class CostAnalyticsEmptyDataTests(TestCase):
    """Tests for cost analytics with no usage data."""

    def setUp(self):
        """Create user with no usage data."""
        self.user = User.objects.create_user(
            username="emptyuser", password="testpass123"
        )
        self.client = Client()

    def test_cost_analytics_handles_empty_data(self):
        """Test that page renders correctly with no usage data."""
        self.client.login(username="emptyuser", password="testpass123")
        response = self.client.get(reverse("cost-analytics"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_cost"], Decimal("0"))
        self.assertEqual(len(response.context["costs_by_provider"]), 0)
        self.assertEqual(len(response.context["costs_by_model"]), 0)


class CostAnalyticsAdminViewTests(TestCase):
    """Tests for admin-level cost analytics (all users)."""

    def setUp(self):
        """Create admin and regular users with usage data."""
        from accounts.models import UserProfile

        # Create admin user
        self.admin = User.objects.create_user(
            username="adminuser", password="testpass123"
        )
        # Make user an admin
        profile, _ = UserProfile.objects.get_or_create(user=self.admin)
        profile.is_super_admin = True
        profile.is_approved = True
        profile.save()

        # Create regular user
        self.regular_user = User.objects.create_user(
            username="regularuser", password="testpass123"
        )
        # Approve regular user
        reg_profile, _ = UserProfile.objects.get_or_create(user=self.regular_user)
        reg_profile.is_approved = True
        reg_profile.save()

        # Create usage data for both users
        feed = Feed.objects.create(user=self.regular_user, name="Regular Feed")
        article = Article.objects.create(
            feed=feed, title="Article", status=Article.COMPLETED
        )

        OpenAIUsageStats.objects.create(
            user=self.regular_user,
            article=article,
            tokens_used=5000,
            model_name="tts-1",
            operation_type="TTS",
            provider="openai",
            estimated_cost=Decimal("0.075000"),
            processing_time_ms=1000,
            word_count=1000,
        )

        self.client = Client()

    def test_admin_can_see_all_users_costs(self):
        """Test that admins can view costs for all users."""
        self.client.login(username="adminuser", password="testpass123")
        response = self.client.get(reverse("cost-analytics") + "?view=all")

        self.assertEqual(response.status_code, 200)
        # Admin should see all users' data
        self.assertIn("costs_by_user", response.context)

    def test_regular_user_cannot_see_all_users_view(self):
        """Test that regular users cannot access all-users view."""
        self.client.login(username="regularuser", password="testpass123")
        response = self.client.get(reverse("cost-analytics") + "?view=all")

        # Should still work but only show their own data
        self.assertEqual(response.status_code, 200)
        # Should not have costs_by_user in context for non-admins
        if "costs_by_user" in response.context:
            # If present, should only contain their own data
            users = [item["username"] for item in response.context["costs_by_user"]]
            self.assertEqual(users, ["regularuser"])
