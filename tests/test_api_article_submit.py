"""Tests for the article submission API."""

import json
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from text_to_audio.models import Article, Feed

User = get_user_model()


class FeedArticleSubmitAPITests(TestCase):
    """Test the article submission API endpoint."""

    def setUp(self):
        """Set up test data."""
        # AIDEV-NOTE: Clear throttle cache so 30+ tests don't hit 30/min anon rate limit
        from django.core.cache import cache

        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.url = reverse("api-feed-article-submit", kwargs={"token": self.feed.token})

    @patch("text_to_audio.api_views.process_article")
    def test_submit_text_article(self, mock_process):
        """Test submitting a new article with text content."""
        # Prepare test data
        payload = {
            "title": "Test Article",
            "text_content": "This is test content for the article submission API.",
        }

        # Make API request
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("audio_uuid", data)
        self.assertIn("id", data)
        self.assertEqual(Article.objects.count(), 1)

        # Verify article data
        article = Article.objects.first()
        self.assertEqual(data["audio_uuid"], str(article.audio_uuid))
        self.assertEqual(data["id"], article.id)
        self.assertEqual(article.title, "Test Article")
        self.assertEqual(
            article.text_content, "This is test content for the article submission API."
        )
        self.assertEqual(article.feed, self.feed)
        self.assertEqual(article.status, Article.PROCESSING)

        # Verify task was called
        mock_process.delay.assert_called_once_with(article.id)

    @patch("text_to_audio.api_views.process_article")
    def test_submit_url_article(self, mock_process):
        """Test submitting a new article with a URL.

        AIDEV-NOTE: URL fetching is now async - the API returns immediately
        and the Celery task handles URL fetching and title extraction.
        """
        # Prepare test data
        payload = {
            "source_url": "https://example.com/test-article",
        }

        # Make API request
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response - should return immediately without fetching URL
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("audio_uuid", data)
        self.assertEqual(Article.objects.count(), 1)

        # Verify article data - URL is saved, content will be fetched async
        article = Article.objects.first()
        self.assertEqual(
            article.title, "Processing..."
        )  # Placeholder until async task runs
        self.assertEqual(article.source_url, "https://example.com/test-article")
        self.assertEqual(article.text_content, "")  # Will be filled by async task
        self.assertEqual(article.feed, self.feed)
        self.assertEqual(article.status, Article.PROCESSING)

        # Verify task was queued (URL fetching happens in task)
        mock_process.delay.assert_called_once_with(article.id)

    @patch("text_to_audio.api_views.process_article")
    def test_submit_url_article_with_title(self, mock_process):
        """Test submitting a URL article with a custom title."""
        # Prepare test data with explicit title
        payload = {
            "source_url": "https://example.com/test-article",
            "title": "My Custom Title",
        }

        # Make API request
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify custom title is preserved
        article = Article.objects.first()
        self.assertEqual(article.title, "My Custom Title")
        self.assertEqual(article.source_url, "https://example.com/test-article")

    def test_submit_both_text_and_url(self):
        """Test that submitting both text and URL fails."""
        # Prepare test data
        payload = {
            "title": "Test Article",
            "text_content": "This is test content.",
            "source_url": "https://example.com/test",
        }

        # Make API request
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Article.objects.count(), 0)
        self.assertIn("both text_content and source_url", str(response.json()))

    def test_submit_neither_text_nor_url(self):
        """Test that submitting neither text nor URL fails."""
        # Prepare test data
        payload = {
            "title": "Test Article",
        }

        # Make API request
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Article.objects.count(), 0)
        self.assertIn("must provide either", str(response.json()))

    def test_submit_to_nonexistent_feed(self):
        """Test submitting to a feed that doesn't exist."""
        # Generate a random UUID that doesn't match any feed
        random_uuid = uuid.uuid4()
        url = reverse("api-feed-article-submit", kwargs={"token": random_uuid})

        # Prepare test data
        payload = {
            "title": "Test Article",
            "text_content": "This is test content.",
        }

        # Make API request
        response = self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Article.objects.count(), 0)

    @patch("text_to_audio.api_views.process_article")
    def test_submit_with_voice_parameters(self, mock_process):
        """Test submitting an article with voice and speed parameters."""
        # Prepare test data
        payload = {
            "title": "Test Article with Voice",
            "text_content": "This is test content with voice parameters.",
            "voice_id": "nova",
            "speed": 1.2,
        }

        # Make API request
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("audio_uuid", data)
        self.assertEqual(Article.objects.count(), 1)

        # Verify article data
        article = Article.objects.first()
        self.assertEqual(article.voice_id, "nova")
        self.assertEqual(article.speed, 1.2)

        # Verify task was called
        mock_process.delay.assert_called_once_with(article.id)

    def test_speed_validation_rejects_negative(self):
        """Test that negative speed values are rejected. Closes #194."""
        payload = {
            "title": "Test Article",
            "text_content": "Some content here.",
            "speed": -1.0,
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_speed_validation_rejects_zero(self):
        """Test that zero speed is rejected. Closes #194."""
        payload = {
            "title": "Test Article",
            "text_content": "Some content here.",
            "speed": 0.0,
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_speed_validation_rejects_extreme_high(self):
        """Test that extremely high speed values are rejected. Closes #194."""
        payload = {
            "title": "Test Article",
            "text_content": "Some content here.",
            "speed": 100.0,
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("text_to_audio.api_views.process_article")
    def test_speed_validation_accepts_valid_bounds(self, mock_process):
        """Test that speed at valid boundaries is accepted."""
        for speed_val in [0.25, 1.0, 4.0]:
            Article.objects.all().delete()
            payload = {
                "title": "Test Article",
                "text_content": "Some content here.",
                "speed": speed_val,
            }
            response = self.client.post(
                self.url, data=json.dumps(payload), content_type="application/json"
            )
            self.assertEqual(
                response.status_code,
                status.HTTP_201_CREATED,
                f"Speed {speed_val} should be accepted but got {response.status_code}",
            )

    def test_speed_validation_rejects_nan_string(self):
        """Test that string 'NaN' speed value is rejected. Closes #194."""
        # Send raw JSON string since json.dumps can't produce NaN literal
        raw_payload = '{"title": "Test", "text_content": "Content", "speed": "NaN"}'
        response = self.client.post(
            self.url, data=raw_payload, content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_speed_validation_rejects_infinity_string(self):
        """Test that string 'Infinity' speed value is rejected. Closes #194."""
        raw_payload = '{"title": "Test", "text_content": "Content", "speed": "Infinity"}'
        response = self.client.post(
            self.url, data=raw_payload, content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_speed_validation_rejects_negative_infinity_string(self):
        """Test that string '-Infinity' speed value is rejected. Closes #194."""
        raw_payload = '{"title": "Test", "text_content": "Content", "speed": "-Infinity"}'
        response = self.client.post(
            self.url, data=raw_payload, content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_speed_validation_rejects_json_nan_literal(self):
        """Test that JSON NaN literal speed value is rejected. Closes #194."""
        # NaN is not valid JSON but Python's json module may parse it
        raw_payload = '{"title": "Test", "text_content": "Content", "speed": NaN}'
        response = self.client.post(
            self.url, data=raw_payload, content_type="application/json"
        )
        # Should get 400 - either JSON parse error or validation error
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE],
        )

    def test_speed_validation_rejects_json_infinity_literal(self):
        """Test that JSON Infinity literal speed value is rejected. Closes #194."""
        raw_payload = '{"title": "Test", "text_content": "Content", "speed": Infinity}'
        response = self.client.post(
            self.url, data=raw_payload, content_type="application/json"
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE],
        )

    @patch("text_to_audio.api_views.process_article")
    def test_exception_leakage_prevented(self, mock_process):
        """Test that internal exception details are not leaked to client. Closes #193."""
        with patch.object(
            Article,
            "clean",
            side_effect=DjangoValidationError(
                "Internal DB constraint: column xyz violated"
            ),
        ):
            payload = {
                "title": "Test Article",
                "text_content": "Some content here.",
            }
            response = self.client.post(
                self.url, data=json.dumps(payload), content_type="application/json"
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            response_text = json.dumps(response.json())
            # Should NOT contain internal exception details
            self.assertNotIn("Internal DB constraint", response_text)
            self.assertNotIn("column xyz", response_text)
            # Should contain a generic error message
            self.assertIn("error", response.json())

    @patch("text_to_audio.api_views.process_article")
    def test_response_includes_audio_uuid(self, mock_process):
        """Test that successful submission returns audio_uuid. Closes #197."""
        payload = {
            "title": "Test Article",
            "text_content": "Some content here.",
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertIn("audio_uuid", data)
        article = Article.objects.first()
        self.assertEqual(data["audio_uuid"], str(article.audio_uuid))

    @patch("text_to_audio.api_views.process_article")
    def test_response_includes_article_id(self, mock_process):
        """Test that successful submission returns the article id."""
        payload = {
            "title": "Test Article",
            "text_content": "Some content here.",
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertIn("id", data)
        article = Article.objects.first()
        self.assertEqual(data["id"], article.id)

    def test_text_content_max_length_rejected(self):
        """Test that extremely long text_content is rejected."""
        payload = {
            "title": "Test Article",
            "text_content": "a" * 500001,
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rate_limiting_returns_429(self):
        """Test that rate limiting kicks in after threshold. Closes #189."""
        from rest_framework.throttling import AnonRateThrottle

        payload = {
            "title": "Test",
            "text_content": "Content.",
        }
        # Mock throttle to deny the request, simulating rate limit exceeded
        with patch.object(AnonRateThrottle, "allow_request", return_value=False):
            with patch.object(AnonRateThrottle, "wait", return_value=30):
                response = self.client.post(
                    self.url,
                    data=json.dumps(payload),
                    content_type="application/json",
                )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_ssrf_url_rejected(self):
        """Test that SSRF URLs are rejected at the API layer. Closes #190."""
        payload = {
            "source_url": "http://169.254.169.254/latest/meta-data/",
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_text = json.dumps(response.json())
        self.assertIn("private", response_text.lower())

    def test_submit_with_invalid_voice_id_rejected(self):
        """Test that an invalid voice_id is rejected. Closes #198."""
        payload = {
            "title": "Test Article",
            "text_content": "Some content here.",
            "voice_id": "not-a-real-voice",
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_text = json.dumps(response.json())
        self.assertIn("voice_id", response_text)

    @patch("text_to_audio.api_views.process_article")
    def test_submit_with_valid_openai_voice_id(self, mock_process):
        """Test that a valid OpenAI voice_id is accepted. Closes #198."""
        payload = {
            "title": "Test Article",
            "text_content": "Some content here.",
            "voice_id": "nova",
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @patch("text_to_audio.api_views.process_article")
    def test_submit_with_valid_google_voice_id(self, mock_process):
        """Test that a valid Google Chirp3 HD voice_id is accepted. Closes #198."""
        payload = {
            "title": "Test Article",
            "text_content": "Some content here.",
            "voice_id": "en-US-Chirp3-HD-Achernar",
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @patch("text_to_audio.api_views.process_article")
    def test_submit_with_valid_gemini_voice_id(self, mock_process):
        """Test that a valid Gemini TTS voice_id is accepted. Closes #198."""
        payload = {
            "title": "Test Article",
            "text_content": "Some content here.",
            "voice_id": "Zephyr",
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @patch("text_to_audio.api_views.process_article")
    def test_submit_with_empty_voice_id_allowed(self, mock_process):
        """Test that empty voice_id is accepted (field is optional). Closes #198."""
        payload = {
            "title": "Test Article",
            "text_content": "Some content here.",
            "voice_id": "",
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @patch("text_to_audio.api_views.process_article")
    def test_submit_without_voice_id_allowed(self, mock_process):
        """Test that omitting voice_id is accepted (field is optional). Closes #198."""
        payload = {
            "title": "Test Article",
            "text_content": "Some content here.",
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @patch("text_to_audio.api_views.process_article")
    def test_unexpected_exception_leakage_prevented(self, mock_process):
        """Test that unexpected exceptions don't leak details to client. Closes #193."""
        with patch.object(
            Article,
            "clean",
            side_effect=RuntimeError("secret DB info: pg_constraint_abc123"),
        ):
            payload = {
                "title": "Test Article",
                "text_content": "Some content here.",
            }
            response = self.client.post(
                self.url, data=json.dumps(payload), content_type="application/json"
            )
            self.assertEqual(
                response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            response_text = json.dumps(response.json())
            # Should NOT contain internal exception details
            self.assertNotIn("secret DB info", response_text)
            self.assertNotIn("pg_constraint_abc123", response_text)
            # Should contain a generic error message
            self.assertIn("error", response.json())

    def test_error_response_format_consistent(self):
        """Test that error responses use consistent format. Closes #195."""
        payload = {"title": "Test Article"}
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn("error", data)

    @patch("text_to_audio.api_views.process_article")
    def test_text_content_word_limit_at_boundary(self, mock_process):
        """Test that text_content with exactly 40,000 words is accepted. Closes #196."""
        payload = {
            "title": "Test Article",
            "text_content": " ".join(["word"] * 40_000),
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_process.delay.assert_called_once()

    def test_text_content_word_limit_exceeded(self):
        """Test that text_content with 40,001 words is rejected. Closes #196."""
        payload = {
            "title": "Test Article",
            "text_content": " ".join(["word"] * 40_001),
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response_text = json.dumps(response.json())
        self.assertIn("40,000", response_text)

    @patch("text_to_audio.api_views.process_article")
    def test_title_at_max_length(self, mock_process):
        """Test that a title with exactly 1024 chars is accepted. Closes #196."""
        payload = {
            "title": "A" * 1024,
            "text_content": "Some content here.",
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        article = Article.objects.first()
        self.assertEqual(len(article.title), 1024)

    def test_title_exceeds_max_length(self):
        """Test that a title with 1025 chars is rejected. Closes #196."""
        payload = {
            "title": "A" * 1025,
            "text_content": "Some content here.",
        }
        response = self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_malformed_json_body(self):
        """Test that a malformed JSON body returns 400. Closes #196."""
        response = self.client.post(
            self.url, data="{invalid json", content_type="application/json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
