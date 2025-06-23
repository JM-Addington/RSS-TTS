"""Tests for voice presets functionality."""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from text_to_audio.models import Article, Feed, UserVoicePreset
from text_to_audio.services.user_preferences import UserPreferencesService
from text_to_audio.services.voice_configuration import \
    VoiceConfigurationService


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
        self.assertEqual(self.article.voice_id, "nova")
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
                "speed": 0.8,
                "prompt": "",
                "sample_input": "",
                "description": "Updated via view test",
            },
            follow=True,
        )

        # Check that we're on the list page after redirect
        self.assertContains(response, "Updated View Preset")

        # Verify preset was updated
        preset.refresh_from_db()
        self.assertEqual(preset.name, "Updated View Preset")
        self.assertEqual(preset.voice_id, "fable")
        self.assertEqual(preset.speed, 0.8)

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
