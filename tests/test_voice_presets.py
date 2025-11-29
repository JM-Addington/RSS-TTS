"""Tests for voice presets functionality."""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from text_to_audio.models import Article, Feed, UserVoicePreset
from text_to_audio.services.user_preferences import UserPreferencesService
from text_to_audio.services.voice_configuration import VoiceConfigurationService


class VoicePresetModelTest(TestCase):
    """Tests for the UserVoicePreset model."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )

    def test_create_preset(self):
        """Test creating a voice preset."""
        preset = UserVoicePreset.objects.create(
            user=self.user,
            name="Test Preset",
            voice_id="nova",
            speed=1.2,
            description="A test preset",
        )

        self.assertEqual(preset.name, "Test Preset")
        self.assertEqual(preset.voice_id, "nova")
        self.assertEqual(preset.speed, 1.2)
        self.assertEqual(preset.description, "A test preset")
        self.assertEqual(preset.user, self.user)

    def test_unique_name_per_user(self):
        """Test that preset names must be unique per user."""
        # Create first preset
        UserVoicePreset.objects.create(
            user=self.user, name="Test Preset", voice_id="nova", speed=1.2
        )

        # Create second user
        user2 = User.objects.create_user(username="testuser2", password="password123")

        # Second user can use the same name
        preset2 = UserVoicePreset.objects.create(
            user=user2, name="Test Preset", voice_id="alloy", speed=1.0
        )

        self.assertEqual(preset2.name, "Test Preset")
        self.assertEqual(preset2.user, user2)

        # But first user can't create another preset with the same name
        with self.assertRaises(Exception):
            UserVoicePreset.objects.create(
                user=self.user, name="Test Preset", voice_id="echo", speed=0.9
            )


class UserPreferencesServiceTest(TestCase):
    """Tests for the UserPreferencesService."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Test Feed")
        self.article = Article.objects.create(
            feed=self.feed, title="Test Article", text_content="This is a test article."
        )
        self.service = UserPreferencesService()

    def test_create_preset(self):
        """Test creating a preset via service."""
        preset = self.service.create_voice_preset(
            user=self.user,
            name="Service Test Preset",
            voice_id="fable",
            speed=0.9,
            description="Created via service",
        )

        self.assertEqual(preset.name, "Service Test Preset")
        self.assertEqual(preset.voice_id, "fable")
        self.assertEqual(preset.speed, 0.9)

        # Verify it exists in database
        saved_preset = UserVoicePreset.objects.get(
            id=preset.id
        )  # type: ignore[attr-defined]
        self.assertEqual(saved_preset.name, "Service Test Preset")

    def test_update_preset(self):
        """Test updating a preset via service."""
        # Create preset
        preset = UserVoicePreset.objects.create(
            user=self.user, name="Update Test", voice_id="shimmer", speed=1.1
        )

        # Update via service
        updated = self.service.update_voice_preset(
            preset_id=preset.id,  # type: ignore[attr-defined]
            name="Updated Name",
            voice_id="echo",
            speed=1.3,
            description="Updated description",
        )

        self.assertEqual(updated.name, "Updated Name")
        self.assertEqual(updated.voice_id, "echo")
        self.assertEqual(updated.speed, 1.3)
        self.assertEqual(updated.description, "Updated description")

        # Verify changes persisted
        preset.refresh_from_db()
        self.assertEqual(preset.name, "Updated Name")

    def test_delete_preset(self):
        """Test deleting a preset via service."""
        # Create preset
        preset = UserVoicePreset.objects.create(
            user=self.user, name="Delete Test", voice_id="alloy", speed=1.0
        )

        # Get preset count before
        count_before = UserVoicePreset.objects.count()

        # Delete via service
        result = self.service.delete_voice_preset(
            preset.id  # type: ignore[attr-defined]
        )

        # Check result
        self.assertTrue(result)

        # Verify it's gone
        count_after = UserVoicePreset.objects.count()
        self.assertEqual(count_after, count_before - 1)
        with self.assertRaises(UserVoicePreset.DoesNotExist):
            UserVoicePreset.objects.get(id=preset.id)  # type: ignore[attr-defined]

    def test_apply_preset_to_article(self):
        """Test applying a preset to an article."""
        # Create preset
        preset = UserVoicePreset.objects.create(
            user=self.user, name="Article Test", voice_id="nova", speed=1.25
        )

        # Apply to article
        self.service.save_article_preferences(article=self.article, voice_preset=preset)

        # Verify article updated
        self.article.refresh_from_db()
        self.assertEqual(self.article.voice_preset, preset)
        self.assertEqual(
            self.article.voice, "nova"
        )  # Standard voice goes in voice field
        self.assertIsNone(
            self.article.voice_id
        )  # voice_id should be None for standard voices
        self.assertEqual(self.article.speed, 1.25)


class VoiceConfigurationServiceTest(TestCase):
    """Tests for the VoiceConfigurationService with presets."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        self.service = VoiceConfigurationService()

        # Create a preset
        self.preset = UserVoicePreset.objects.create(
            user=self.user, name="Config Test", voice_id="echo", speed=0.8
        )

    def test_get_available_voices(self):
        """Service returns the full list of available voices."""
        voices = dict(self.service.get_available_voices())
        expected = {
            "alloy",
            "ash",
            "ballad",
            "coral",
            "echo",
            "fable",
            "onyx",
            "nova",
            "sage",
            "shimmer",
        }
        self.assertEqual(set(voices.keys()), expected)

    def test_get_user_presets(self):
        """Test getting presets for a user."""
        # Create another preset
        UserVoicePreset.objects.create(
            user=self.user, name="Second Preset", voice_id="nova", speed=1.1
        )

        # Get presets
        presets = self.service.get_user_presets(self.user)

        # Should be 2 presets
        self.assertEqual(len(presets), 2)

        # Should be formatted as tuples with id and name
        self.assertIsInstance(presets[0], tuple)
        self.assertEqual(len(presets[0]), 2)

    def test_voice_config_with_preset(self):
        """Test that presets override other settings."""
        # Basic config without preset
        self.service.get_voice_config(
            detected_tone="formal",
            user_preferences={"voice": "alloy", "speed": 1.0},
            article_preferences={"voice": "shimmer", "speed": 1.1},
        )

        # With preset
        config2 = self.service.get_voice_config(
            detected_tone="formal",
            user_preferences={"voice": "alloy", "speed": 1.0},
            voice_preset=self.preset,
        )

        # Preset should override user preferences
        self.assertEqual(config2["voice"], "echo")
        self.assertEqual(config2["speed"], 0.8)

        # But article preferences should still take highest priority
        config3 = self.service.get_voice_config(
            detected_tone="formal",
            user_preferences={"voice": "alloy", "speed": 1.0},
            voice_preset=self.preset,
            article_preferences={"voice": "shimmer", "speed": 1.1},
        )

        self.assertEqual(config3["voice"], "shimmer")
        self.assertEqual(config3["speed"], 1.1)


class VoicePresetViewsTest(TestCase):
    """Tests for voice preset views."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        self.client.login(username="testuser", password="password123")

    def test_preset_list_view(self):
        """Test the preset list view."""
        # Create some presets
        UserVoicePreset.objects.create(
            user=self.user, name="Test Preset 1", voice_id="nova", speed=1.0
        )
        UserVoicePreset.objects.create(
            user=self.user, name="Test Preset 2", voice_id="echo", speed=0.9
        )

        # Access the list view
        response = self.client.get(reverse("voice_preset_list"))

        # Check response
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Preset 1")
        self.assertContains(response, "Test Preset 2")

    def test_preset_create_view(self):
        """Test creating a preset via view."""
        # Get the create form
        response = self.client.get(reverse("voice_preset_create"))
        self.assertEqual(response.status_code, 200)

        # Submit the form
        response = self.client.post(
            reverse("voice_preset_create"),
            {
                "name": "New View Preset",
                "voice_id": "alloy",
                "speed": 1.0,
                "description": "Created via view test",
            },
        )

        # Should redirect to list view
        self.assertRedirects(response, reverse("voice_preset_list"))

        # Verify preset was created
        preset = UserVoicePreset.objects.get(name="New View Preset")
        self.assertEqual(preset.voice_id, "alloy")
        self.assertEqual(preset.user, self.user)

    def test_preset_edit_view(self):
        """Test editing a preset via view."""
        # Create a preset
        preset = UserVoicePreset.objects.create(
            user=self.user, name="Edit View Test", voice_id="shimmer", speed=1.1
        )

        # Get the edit form
        response = self.client.get(
            reverse("voice_preset_edit", args=[preset.id])  # type: ignore[attr-defined]
        )
        self.assertEqual(response.status_code, 200)

        # Submit the form
        preset_id = preset.id  # type: ignore[attr-defined]
        edit_url = reverse(
            "voice_preset_edit",
            args=[preset_id],
        )
        response = self.client.post(
            edit_url,
            {
                "name": "Updated View Preset",
                "voice_id": "fable",
                "speed": 0.9,  # Use valid speed choice
                "prompt": "",
                "sample_input": "",
                "description": "Updated via view test",
            },
        )

        # Check that it redirects to the list page
        self.assertRedirects(response, reverse("voice_preset_list"))

        # Verify preset was updated
        preset.refresh_from_db()
        self.assertEqual(preset.name, "Updated View Preset")
        self.assertEqual(preset.voice_id, "fable")
        self.assertEqual(preset.speed, 0.9)

    def test_preset_delete_view(self):
        """Test deleting a preset via view."""
        # Create a preset
        preset = UserVoicePreset.objects.create(
            user=self.user, name="Delete View Test", voice_id="nova", speed=1.0
        )

        # Get the delete confirmation
        delete_id = preset.id  # type: ignore[attr-defined]
        delete_url = reverse("voice_preset_delete", args=[delete_id])
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 200)

        # Submit the form
        response = self.client.post(delete_url)

        # Should redirect to list view
        self.assertRedirects(response, reverse("voice_preset_list"))

        # Verify preset was deleted
        with self.assertRaises(UserVoicePreset.DoesNotExist):
            UserVoicePreset.objects.get(id=preset.id)  # type: ignore[attr-defined]

    def test_feed_default_preset_applied(self):
        """Article creation uses feed default preset when none selected."""
        default_preset = UserVoicePreset.objects.create(
            user=self.user, name="Default", voice_id="nova", speed=1.1
        )
        feed = Feed.objects.create(
            user=self.user,
            name="Feed With Default",
            default_voice_preset=default_preset,
        )

        with patch("text_to_audio.views.process_article.delay") as mock_delay:
            mock_task = mock_delay.return_value
            mock_task.id = "task-id"
            response = self.client.post(
                reverse("feed-article-create", args=[feed.pk]),
                {"title": "A", "text_content": "b"},
            )
            self.assertEqual(response.status_code, 302)

            article = Article.objects.get(title="A")
            self.assertEqual(article.voice_preset, default_preset)


@patch("text_to_audio.services.tts_service.TTSService")
class VoicePresetSampleViewTests(TestCase):
    """Tests for generating voice samples from presets."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="sampleuser", password="password123"
        )
        self.client.login(username="sampleuser", password="password123")
        self.preset = UserVoicePreset.objects.create(
            user=self.user, name="Preset", voice_id="alloy", speed=1.0
        )

    def test_get_sample_form(self, MockTTSService):
        url = reverse("voice_preset_sample", args=[self.preset.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Generate Sample")

    def test_generate_sample_openai(self, MockTTSService):
        """Test generating a sample with OpenAI voice."""
        mock_instance = MockTTSService.return_value
        mock_instance.generate_speech.return_value = b"dummy audio data"

        url = reverse("voice_preset_sample", args=[self.preset.pk])
        response = self.client.post(url, {"text": "hello world"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "audio/mpeg")
        self.assertEqual(
            response["Content-Disposition"], 'inline; filename="voice_sample.mp3"'
        )
        # Verify TTSService was initialized with OpenAI provider
        MockTTSService.assert_called_once_with(provider="openai")
        mock_instance.generate_speech.assert_called_once()
        call_kwargs = mock_instance.generate_speech.call_args.kwargs
        self.assertEqual(call_kwargs["voice"], "alloy")
        self.assertEqual(call_kwargs["speed"], 1.0)
        self.assertEqual(call_kwargs["text"], "hello world")

    def test_generate_sample_google(self, MockTTSService):
        """Test generating a sample with Google TTS voice."""
        # Create a preset with Google voice
        google_preset = UserVoicePreset.objects.create(
            user=self.user,
            name="Google Preset",
            voice_id="en-US-Chirp3-HD-Charon",
            speed=1.2,
        )
        mock_instance = MockTTSService.return_value
        mock_instance.generate_speech.return_value = b"dummy google audio"

        url = reverse("voice_preset_sample", args=[google_preset.pk])
        response = self.client.post(url, {"text": "hello from google"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "audio/mpeg")
        # Verify TTSService was initialized with Google provider
        MockTTSService.assert_called_once_with(provider="google")
        mock_instance.generate_speech.assert_called_once()
        call_kwargs = mock_instance.generate_speech.call_args.kwargs
        self.assertEqual(call_kwargs["voice"], "en-US-Chirp3-HD-Charon")
        self.assertEqual(call_kwargs["speed"], 1.2)

    def test_word_limit_validation(self, MockTTSService):
        text = "word " * 101
        url = reverse("voice_preset_sample", args=[self.preset.pk])
        response = self.client.post(url, {"text": text})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "100 words or fewer")
        MockTTSService.assert_not_called()

    def test_ajax_word_limit_validation(self, MockTTSService):
        text = "word " * 101
        url = reverse("voice_preset_sample", args=[self.preset.pk])
        response = self.client.post(
            url, {"text": text}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("100 words or fewer", response.content.decode())
        MockTTSService.assert_not_called()


@patch("text_to_audio.services.tts_service.TTSService")
class VoicePresetTestViewTests(TestCase):
    """Tests for real-time voice testing in preset edit form."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", password="password123"
        )
        self.client.login(username="testuser", password="password123")
        self.preset = UserVoicePreset.objects.create(
            user=self.user, name="Test Preset", voice_id="alloy", speed=1.0
        )

    def test_voice_test_ajax_required(self, MockTTSService):
        url = reverse("voice_preset_test")
        response = self.client.post(
            url, {"voice_id": "alloy", "speed": "1.0", "text": "test"}
        )
        self.assertEqual(response.status_code, 400)
        MockTTSService.assert_not_called()

    def test_voice_test_success_openai(self, MockTTSService):
        """Test voice test with OpenAI voice."""
        mock_instance = MockTTSService.return_value
        mock_instance.generate_speech.return_value = b"dummy audio data"

        url = reverse("voice_preset_test")
        response = self.client.post(
            url,
            {"voice_id": "alloy", "speed": "1.0", "text": "test voice"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "audio/mpeg")
        self.assertEqual(
            response["Content-Disposition"], 'inline; filename="voice_test.mp3"'
        )
        # Verify TTSService was initialized with OpenAI provider
        MockTTSService.assert_called_once_with(provider="openai")
        mock_instance.generate_speech.assert_called_once()
        call_kwargs = mock_instance.generate_speech.call_args.kwargs
        self.assertEqual(call_kwargs["voice"], "alloy")
        self.assertEqual(call_kwargs["speed"], 1.0)
        self.assertEqual(call_kwargs["text"], "test voice")

    def test_voice_test_success_google(self, MockTTSService):
        """Test voice test with Google TTS voice (Chirp3-HD)."""
        mock_instance = MockTTSService.return_value
        mock_instance.generate_speech.return_value = b"dummy google audio"

        url = reverse("voice_preset_test")
        response = self.client.post(
            url,
            {
                "voice_id": "en-US-Chirp3-HD-Charon",
                "speed": "1.2",
                "text": "test google voice",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "audio/mpeg")
        # Verify TTSService was initialized with Google provider
        MockTTSService.assert_called_once_with(provider="google")
        mock_instance.generate_speech.assert_called_once()
        call_kwargs = mock_instance.generate_speech.call_args.kwargs
        self.assertEqual(call_kwargs["voice"], "en-US-Chirp3-HD-Charon")
        self.assertEqual(call_kwargs["speed"], 1.2)

    def test_voice_test_google_journey(self, MockTTSService):
        """Test voice test with Google Journey voice."""
        mock_instance = MockTTSService.return_value
        mock_instance.generate_speech.return_value = b"dummy journey audio"

        url = reverse("voice_preset_test")
        response = self.client.post(
            url,
            {
                "voice_id": "en-US-Journey-D",
                "speed": "1.0",
                "text": "test journey voice",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        MockTTSService.assert_called_once_with(provider="google")

    def test_voice_test_google_neural2(self, MockTTSService):
        """Test voice test with Google Neural2 voice."""
        mock_instance = MockTTSService.return_value
        mock_instance.generate_speech.return_value = b"dummy neural2 audio"

        url = reverse("voice_preset_test")
        response = self.client.post(
            url,
            {
                "voice_id": "en-US-Neural2-A",
                "speed": "1.0",
                "text": "test neural2 voice",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        MockTTSService.assert_called_once_with(provider="google")

    def test_voice_test_validation(self, MockTTSService):
        url = reverse("voice_preset_test")

        # Test missing fields
        response = self.client.post(
            url, {"voice_id": "alloy"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 400)

        # Test invalid speed
        response = self.client.post(
            url,
            {"voice_id": "alloy", "speed": "invalid", "text": "test"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)

        # Test word limit
        response = self.client.post(
            url,
            {"voice_id": "alloy", "speed": "1.0", "text": "word " * 101},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("100 words or fewer", response.content.decode())

        MockTTSService.assert_not_called()


class VoicePresetAPITests(TestCase):
    """Tests for voice preset API endpoints."""

    def setUp(self):
        """Set up test data."""
        from rest_framework.test import APIClient

        self.client = APIClient()
        self.user = User.objects.create_user(
            username="apiuser", email="api@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass123"
        )

        # Create presets for main user
        self.preset1 = UserVoicePreset.objects.create(
            user=self.user,
            name="News Reader",
            voice_id="nova",
            speed=1.0,
            description="A clear news reading voice",
        )
        self.preset2 = UserVoicePreset.objects.create(
            user=self.user,
            name="Storyteller",
            voice_id="echo",
            speed=0.9,
            description="A warm storytelling voice",
            prompt="Speak warmly and engagingly",
        )

        # Create preset for other user
        self.other_preset = UserVoicePreset.objects.create(
            user=self.other_user,
            name="Other Voice",
            voice_id="alloy",
            speed=1.0,
            description="Another user's preset",
        )

    def test_list_presets_requires_auth(self):
        """Test that listing presets requires authentication."""
        url = reverse("api-voice-preset-list")
        response = self.client.get(url)
        # DRF returns 403 for unauthenticated session requests
        self.assertIn(response.status_code, [401, 403])

    def test_list_presets_returns_user_presets_only(self):
        """Test that listing presets returns only the authenticated user's presets."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api-voice-preset-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Should only return 2 presets (not the other user's preset)
        self.assertEqual(len(data), 2)

        # Check preset names
        preset_names = [p["name"] for p in data]
        self.assertIn("News Reader", preset_names)
        self.assertIn("Storyteller", preset_names)
        self.assertNotIn("Other Voice", preset_names)

    def test_list_presets_includes_description(self):
        """Test that listed presets include description field."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api-voice-preset-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Find the News Reader preset
        news_reader = next(p for p in data if p["name"] == "News Reader")
        self.assertEqual(news_reader["description"], "A clear news reading voice")

    def test_list_presets_includes_all_fields(self):
        """Test that listed presets include all relevant fields."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api-voice-preset-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Find the Storyteller preset
        storyteller = next(p for p in data if p["name"] == "Storyteller")

        # Check all expected fields are present
        expected_fields = [
            "id",
            "name",
            "voice_id",
            "speed",
            "description",
            "prompt",
            "created_at",
            "updated_at",
        ]
        for field in expected_fields:
            self.assertIn(field, storyteller)

        self.assertEqual(storyteller["voice_id"], "echo")
        self.assertEqual(storyteller["speed"], 0.9)
        self.assertEqual(storyteller["prompt"], "Speak warmly and engagingly")

    def test_get_preset_detail_requires_auth(self):
        """Test that getting a preset detail requires authentication."""
        url = reverse("api-voice-preset-detail", kwargs={"preset_id": self.preset1.id})
        response = self.client.get(url)
        # DRF returns 403 for unauthenticated session requests
        self.assertIn(response.status_code, [401, 403])

    def test_get_preset_detail(self):
        """Test getting a single preset by ID."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api-voice-preset-detail", kwargs={"preset_id": self.preset1.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["id"], self.preset1.id)
        self.assertEqual(data["name"], "News Reader")
        self.assertEqual(data["voice_id"], "nova")
        self.assertEqual(data["speed"], 1.0)
        self.assertEqual(data["description"], "A clear news reading voice")

    def test_get_preset_detail_not_found(self):
        """Test getting a non-existent preset returns 404."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api-voice-preset-detail", kwargs={"preset_id": 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_get_preset_detail_other_users_preset(self):
        """Test that users cannot access other users' presets."""
        self.client.force_authenticate(user=self.user)
        url = reverse(
            "api-voice-preset-detail", kwargs={"preset_id": self.other_preset.id}
        )
        response = self.client.get(url)

        # Should return 404, not 403 (to not leak info about other users' presets)
        self.assertEqual(response.status_code, 404)

    def test_list_presets_empty(self):
        """Test listing presets when user has none."""
        # Create a new user with no presets
        empty_user = User.objects.create_user(
            username="emptyuser", email="empty@example.com", password="testpass123"
        )
        self.client.force_authenticate(user=empty_user)
        url = reverse("api-voice-preset-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data, [])

    def test_create_preset_requires_auth(self):
        """Test that creating a preset requires authentication."""
        url = reverse("api-voice-preset-list")
        payload = {
            "name": "New Preset",
            "voice_id": "nova",
            "speed": 1.0,
        }
        response = self.client.post(url, payload, format="json")
        # DRF returns 403 for unauthenticated session requests
        self.assertIn(response.status_code, [401, 403])

    def test_create_preset_success(self):
        """Test successfully creating a voice preset."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api-voice-preset-list")
        payload = {
            "name": "My New Preset",
            "voice_id": "alloy",
            "speed": 1.1,
            "description": "A custom voice preset",
            "prompt": "Speak clearly and confidently",
        }
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, 201)
        data = response.json()

        self.assertEqual(data["name"], "My New Preset")
        self.assertEqual(data["voice_id"], "alloy")
        self.assertEqual(data["speed"], 1.1)
        self.assertEqual(data["description"], "A custom voice preset")
        self.assertEqual(data["prompt"], "Speak clearly and confidently")
        self.assertIn("id", data)
        self.assertIn("created_at", data)

        # Verify it was saved to the database
        preset = UserVoicePreset.objects.get(id=data["id"])
        self.assertEqual(preset.user, self.user)
        self.assertEqual(preset.name, "My New Preset")

    def test_create_preset_minimal_fields(self):
        """Test creating a preset with only required fields."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api-voice-preset-list")
        payload = {
            "name": "Minimal Preset",
            "voice_id": "echo",
            "speed": 1.0,
        }
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "Minimal Preset")
        self.assertEqual(data["voice_id"], "echo")

    def test_create_preset_duplicate_name(self):
        """Test that creating a preset with duplicate name fails."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api-voice-preset-list")
        payload = {
            "name": "News Reader",  # Already exists for this user
            "voice_id": "alloy",
            "speed": 1.0,
        }
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.json())

    def test_create_preset_same_name_different_user(self):
        """Test that different users can have presets with the same name."""
        # Create a new user
        new_user = User.objects.create_user(
            username="newuser", email="new@example.com", password="testpass123"
        )
        self.client.force_authenticate(user=new_user)
        url = reverse("api-voice-preset-list")
        payload = {
            "name": "News Reader",  # Same name as existing preset but different user
            "voice_id": "shimmer",
            "speed": 0.9,
        }
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["name"], "News Reader")

        # Verify it belongs to the new user
        preset = UserVoicePreset.objects.get(id=data["id"])
        self.assertEqual(preset.user, new_user)

    def test_create_preset_missing_required_fields(self):
        """Test that creating a preset without required fields fails."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api-voice-preset-list")

        # Missing name
        response = self.client.post(
            url, {"voice_id": "nova", "speed": 1.0}, format="json"
        )
        self.assertEqual(response.status_code, 400)

        # Missing voice_id
        response = self.client.post(url, {"name": "Test", "speed": 1.0}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_create_preset_invalid_voice_id(self):
        """Test that creating a preset with invalid voice_id fails."""
        self.client.force_authenticate(user=self.user)
        url = reverse("api-voice-preset-list")
        payload = {
            "name": "Invalid Voice",
            "voice_id": "not_a_real_voice",
            "speed": 1.0,
        }
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("voice_id", response.json())
