"""Tests for the FollowedFeed UI (Forms and Views)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from text_to_audio.forms import FollowedFeedForm
from text_to_audio.models import Feed, FollowedFeed

User = get_user_model()


class FollowedFeedUITests(TestCase):
    """Tests for the FollowedFeed UI (Forms and Views)."""

    @classmethod
    def setUpTestData(cls):
        """Set up data for the entire test class."""
        cls.user = User.objects.create_user(
            username="ui_testuser", password="password123"
        )
        cls.other_user = User.objects.create_user(
            username="other_user", password="password123"
        )
        cls.client = Client()

        # User's own feed for destination
        cls.user_destination_feed = Feed.objects.create(
            user=cls.user, name="My Test Podcast"
        )
        # Another feed for the same user
        cls.user_destination_feed_2 = Feed.objects.create(
            user=cls.user, name="My Other Podcast"
        )

    def setUp(self):
        """Log in the user for each test."""
        self.client.login(username="ui_testuser", password="password123")

    def test_followed_feed_list_view(self):
        """Test the FollowedFeedListView."""
        # Create some followed feeds for the logged-in user
        FollowedFeed.objects.create(
            user=self.user,
            url="https://example.com/feed1",
            destination_feed=self.user_destination_feed,
        )
        FollowedFeed.objects.create(
            user=self.user,
            url="https://example.com/feed2",
            destination_feed=self.user_destination_feed,
        )
        # Create a followed feed for another user (should not be visible)
        other_user_feed = Feed.objects.create(
            user=self.other_user, name="Other's Podcast"
        )
        FollowedFeed.objects.create(
            user=self.other_user,
            url="https://example.com/feed_other",
            destination_feed=other_user_feed,
        )

        response = self.client.get(reverse("followedfeed-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "https://example.com/feed1")
        self.assertContains(response, "https://example.com/feed2")
        self.assertNotContains(response, "https://example.com/feed_other")
        self.assertEqual(len(response.context["followed_feeds"]), 2)

    def test_followed_feed_create_view_get(self):
        """Test GET request for FollowedFeedCreateView."""
        response = self.client.get(reverse("followedfeed-create"))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], FollowedFeedForm)

    def test_followed_feed_create_view_post_valid(self):
        """Test POST request with valid data for FollowedFeedCreateView."""
        data = {
            "url": "https://example.com/new_feed_valid",
            "destination_feed": self.user_destination_feed.pk,
            "is_active": True,
        }
        response = self.client.post(reverse("followedfeed-create"), data)
        self.assertRedirects(response, reverse("followedfeed-list"))
        self.assertTrue(
            FollowedFeed.objects.filter(
                user=self.user, url="https://example.com/new_feed_valid"
            ).exists()
        )

    def test_followed_feed_create_view_post_invalid(self):
        """Test POST request with invalid data for FollowedFeedCreateView."""
        data = {
            "url": "not_a_valid_url",  # Invalid URL
            "destination_feed": self.user_destination_feed.pk,
        }
        response = self.client.post(reverse("followedfeed-create"), data)
        self.assertEqual(response.status_code, 200)  # Should re-render form with errors
        # Check form errors in the response context
        form = response.context["form"]
        self.assertIn("url", form.errors)
        self.assertIn("Enter a valid URL.", str(form.errors["url"]))
        self.assertFalse(
            FollowedFeed.objects.filter(user=self.user, url="not_a_valid_url").exists()
        )

    def test_followed_feed_update_view_get(self):
        """Test GET request for FollowedFeedUpdateView."""
        followed_feed = FollowedFeed.objects.create(
            user=self.user,
            url="https://example.com/to_update",
            destination_feed=self.user_destination_feed,
        )
        response = self.client.get(
            reverse("followedfeed-edit", kwargs={"pk": followed_feed.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], FollowedFeedForm)
        self.assertEqual(response.context["object"], followed_feed)

    def test_followed_feed_update_view_post_valid(self):
        """Test POST request with valid data for FollowedFeedUpdateView."""
        followed_feed = FollowedFeed.objects.create(
            user=self.user,
            url="https://example.com/to_update_post",
            destination_feed=self.user_destination_feed,
            is_active=True,
        )
        data = {
            "url": "https://example.com/updated_url",
            "destination_feed": self.user_destination_feed_2.pk,  # Change destination
            "is_active": False,  # Change active status
        }
        response = self.client.post(
            reverse("followedfeed-edit", kwargs={"pk": followed_feed.pk}), data
        )
        self.assertRedirects(response, reverse("followedfeed-list"))

        updated_feed = FollowedFeed.objects.get(pk=followed_feed.pk)
        self.assertEqual(updated_feed.url, "https://example.com/updated_url")
        self.assertEqual(updated_feed.destination_feed, self.user_destination_feed_2)
        self.assertFalse(updated_feed.is_active)

    def test_followed_feed_update_view_other_user(self):
        """Test that a user cannot update another user's followed feed."""
        other_user_feed_dest = Feed.objects.create(
            user=self.other_user, name="Other's Dest"
        )
        other_followed_feed = FollowedFeed.objects.create(
            user=self.other_user,
            url="https://example.com/other_user_feed",
            destination_feed=other_user_feed_dest,
        )
        response = self.client.get(
            reverse("followedfeed-edit", kwargs={"pk": other_followed_feed.pk})
        )
        # Should be 404 as queryset filters by user
        self.assertEqual(response.status_code, 404)

    def test_followed_feed_delete_view_get(self):
        """Test GET request for FollowedFeedDeleteView."""
        followed_feed = FollowedFeed.objects.create(
            user=self.user,
            url="https://example.com/to_delete",
            destination_feed=self.user_destination_feed,
        )
        response = self.client.get(
            reverse("followedfeed-delete", kwargs={"pk": followed_feed.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["object"], followed_feed)

    def test_followed_feed_delete_view_post(self):
        """Test POST request to delete a FollowedFeed."""
        followed_feed = FollowedFeed.objects.create(
            user=self.user,
            url="https://example.com/to_delete_post",
            destination_feed=self.user_destination_feed,
        )
        feed_pk = followed_feed.pk
        response = self.client.post(
            reverse("followedfeed-delete", kwargs={"pk": feed_pk})
        )
        self.assertRedirects(response, reverse("followedfeed-list"))
        self.assertFalse(FollowedFeed.objects.filter(pk=feed_pk).exists())

    def test_followed_feed_delete_view_other_user(self):
        """Test that a user cannot delete another user's followed feed."""
        other_user_feed_dest = Feed.objects.create(
            user=self.other_user, name="Other's Dest Del"
        )
        other_followed_feed = FollowedFeed.objects.create(
            user=self.other_user,
            url="https://example.com/other_user_feed_del",
            destination_feed=other_user_feed_dest,
        )
        response = self.client.post(
            reverse("followedfeed-delete", kwargs={"pk": other_followed_feed.pk})
        )
        self.assertEqual(response.status_code, 404)  # Should be 404
        self.assertTrue(FollowedFeed.objects.filter(pk=other_followed_feed.pk).exists())

    def test_followed_feed_form_validation_valid(self):
        """Test FollowedFeedForm with valid data."""
        data = {
            "url": "https://example.com/valid_form_url",
            "destination_feed": self.user_destination_feed.pk,
            "is_active": True,
        }
        form = FollowedFeedForm(data=data, user=self.user)
        self.assertTrue(form.is_valid())

    def test_followed_feed_form_validation_invalid_url(self):
        """Test FollowedFeedForm with an invalid URL."""
        data = {
            "url": "invalid-url",
            "destination_feed": self.user_destination_feed.pk,
        }
        form = FollowedFeedForm(data=data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("url", form.errors)
        self.assertEqual(form.errors["url"], ["Enter a valid URL."])

    def test_followed_feed_form_missing_destination(self):
        """Test FollowedFeedForm with missing destination_feed."""
        data = {"url": "https://example.com/valid_form_url"}  # Missing destination_feed
        form = FollowedFeedForm(data=data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("destination_feed", form.errors)

    def test_followed_feed_form_destination_feed_queryset(self):
        """Test that destination_feed queryset is correctly filtered for the user."""
        # Create a feed for another user, it should not appear in choices
        other_user_dest_feed = Feed.objects.create(
            user=self.other_user, name="Other User's Feed"
        )

        form = FollowedFeedForm(user=self.user)
        destination_feed_choices = form.fields["destination_feed"].queryset

        self.assertIn(self.user_destination_feed, destination_feed_choices)
        self.assertIn(self.user_destination_feed_2, destination_feed_choices)
        self.assertNotIn(other_user_dest_feed, destination_feed_choices)
        self.assertEqual(destination_feed_choices.count(), 2)

    def test_followed_feed_form_no_destination_feeds_for_user(self):
        """Test form behavior when user has no destination feeds."""
        # Create a new user with no feeds
        no_feeds_user = User.objects.create_user(
            username="nofeedsuser", password="password"
        )

        form = FollowedFeedForm(user=no_feeds_user)
        destination_feed_field = form.fields["destination_feed"]

        self.assertEqual(destination_feed_field.queryset.count(), 0)
        self.assertTrue(destination_feed_field.widget.attrs.get("disabled", False))
        self.assertIn("You don't have any feeds yet.", destination_feed_field.help_text)

    def test_create_followed_feed_no_destination_feeds_get(self):
        """Test GET create view when user has no destination feeds."""
        # Login as a user with no feeds
        User.objects.create_user(
            username="nofeedsuser_get", password="password"
        )
        self.client.login(username="nofeedsuser_get", password="password")

        response = self.client.get(reverse("followedfeed-create"))
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertTrue(form.fields["destination_feed"].widget.attrs.get("disabled"))
        self.assertContains(response, "You don&#x27;t have any feeds yet.")
        self.client.logout()  # Clean up session for next test

    def test_create_followed_feed_no_destination_feeds_post_fails(self):
        """Test POST create view fails if user has no destination feeds (form should be invalid)."""
        no_feeds_user = User.objects.create_user(
            username="nofeedsuser_post", password="password"
        )
        self.client.login(username="nofeedsuser_post", password="password")

        data = {
            "url": "https://example.com/feed_no_dest",
            # No destination_feed provided, and user has none
            "is_active": True,
        }
        response = self.client.post(reverse("followedfeed-create"), data)
        self.assertEqual(response.status_code, 200)  # Should re-render form
        # Check form errors in the response context
        form = response.context["form"]
        self.assertIn("destination_feed", form.errors)
        self.assertIn("This field is required.", str(form.errors["destination_feed"]))
        self.assertFalse(FollowedFeed.objects.filter(user=no_feeds_user).exists())
        self.client.logout()
