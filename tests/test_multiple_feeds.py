"""Tests for multiple feeds functionality."""

import uuid

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from text_to_audio.models import Article, Feed


class MultipleFeedsTestCase(TestCase):
    """Test case for multiple feeds per user functionality."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.client.login(username="testuser", password="testpassword")

    def test_create_multiple_feeds(self):
        """Test that a user can create multiple feeds."""
        # Create first feed
        response = self.client.post(reverse("feed-create"), {"name": "Business News"})
        self.assertEqual(response.status_code, 302)

        # Create second feed
        response = self.client.post(reverse("feed-create"), {"name": "Kids Stories"})
        self.assertEqual(response.status_code, 302)

        # Verify both feeds exist
        feeds = Feed.objects.filter(user=self.user)
        self.assertEqual(feeds.count(), 2)
        self.assertEqual(
            set(feeds.values_list("name", flat=True)), {"Business News", "Kids Stories"}
        )

    def test_feed_list_view(self):
        """Test the feed list view shows all user feeds."""
        # Create feeds
        feed1 = Feed.objects.create(user=self.user, name="Tech Articles")
        feed2 = Feed.objects.create(user=self.user, name="Science News")

        # Test feed list view
        response = self.client.get(reverse("feed-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tech Articles")
        self.assertContains(response, "Science News")
        self.assertContains(response, feed1.token)
        self.assertContains(response, feed2.token)

    def test_feed_specific_article_list(self):
        """Test that article lists are feed-specific."""
        # Create two feeds
        feed1 = Feed.objects.create(user=self.user, name="Feed 1")
        feed2 = Feed.objects.create(user=self.user, name="Feed 2")

        # Create articles for each feed
        Article.objects.create(
            feed=feed1,
            title="Article in Feed 1",
            text_content="Content 1",
            audio_uuid=uuid.uuid4(),
        )
        Article.objects.create(
            feed=feed2,
            title="Article in Feed 2",
            text_content="Content 2",
            audio_uuid=uuid.uuid4(),
        )

        # Test feed 1 article list
        response = self.client.get(
            reverse("feed-articles", kwargs={"feed_id": feed1.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Article in Feed 1")
        self.assertNotContains(response, "Article in Feed 2")

        # Test feed 2 article list
        response = self.client.get(
            reverse("feed-articles", kwargs={"feed_id": feed2.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Article in Feed 2")
        self.assertNotContains(response, "Article in Feed 1")

    def test_feed_update(self):
        """Test updating a feed name."""
        feed = Feed.objects.create(user=self.user, name="Original Name")

        response = self.client.post(
            reverse("feed-update", kwargs={"feed_id": feed.pk}),
            {"name": "Updated Name"},
        )
        self.assertEqual(response.status_code, 302)

        # Verify name was updated
        feed.refresh_from_db()
        self.assertEqual(feed.name, "Updated Name")

    def test_feed_delete(self):
        """Test deleting a feed."""
        feed = Feed.objects.create(user=self.user, name="To Delete")

        # Create an article in the feed
        Article.objects.create(
            feed=feed,
            title="Article to be deleted",
            text_content="Content",
            audio_uuid=uuid.uuid4(),
        )

        # Delete the feed
        response = self.client.post(reverse("feed-delete", kwargs={"feed_id": feed.pk}))
        self.assertEqual(response.status_code, 302)

        # Verify feed and articles are deleted
        self.assertEqual(Feed.objects.filter(pk=feed.pk).count(), 0)
        self.assertEqual(Article.objects.filter(feed=feed).count(), 0)

    def test_feed_isolation(self):
        """Test that users can only see their own feeds."""
        # Create another user
        other_user = User.objects.create_user(
            username="otheruser", password="otherpassword"
        )

        # Create feeds for both users
        Feed.objects.create(user=self.user, name="My Feed")
        other_feed = Feed.objects.create(user=other_user, name="Other Feed")

        # Test feed list only shows current user's feeds
        response = self.client.get(reverse("feed-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Feed")
        self.assertNotContains(response, "Other Feed")

        # Test cannot access other user's feed
        response = self.client.get(
            reverse("feed-articles", kwargs={"feed_id": other_feed.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_unique_rss_urls(self):
        """Test that each feed has a unique RSS URL."""
        feed1 = Feed.objects.create(user=self.user, name="Feed 1")
        feed2 = Feed.objects.create(user=self.user, name="Feed 2")

        # Verify tokens are unique
        self.assertNotEqual(feed1.token, feed2.token)

        # Verify RSS URLs are different
        response = self.client.get(reverse("feed-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(feed1.token))
        self.assertContains(response, str(feed2.token))

    def test_old_urls_redirect(self):
        """Test that old URLs redirect to new feed-based system."""
        # Create default feed
        Feed.objects.create(user=self.user, name="Default")

        # Test article-list redirects to feed-list
        response = self.client.get(reverse("article-list"))
        self.assertRedirects(response, reverse("feed-list"))

        # Test article-submit redirects to feed-specific submit
        response = self.client.get(reverse("article-submit"))
        self.assertEqual(response.status_code, 302)
        # Test redirect using assertRedirects which handles both HttpRedirectResponse
        # and StreamingHttpResponse properly
        self.assertTrue(
            response.headers.get("Location", "").find("/feeds/") >= 0,
            "URL should contain '/feeds/'",
        )
        self.assertTrue(
            response.headers.get("Location", "").find("/add/") >= 0,
            "URL should contain '/add/'",
        )

    def test_feed_list_order_and_add_article_button(self):
        """Test that feeds are ordered by ID and have Add Article buttons."""
        # Create feeds in reverse order to verify ordering
        feed2 = Feed.objects.create(user=self.user, name="Feed 2")
        feed1 = Feed.objects.create(user=self.user, name="Feed 1")
        feed3 = Feed.objects.create(user=self.user, name="Feed 3")

        # Test feed list view
        response = self.client.get(reverse("feed-list"))
        self.assertEqual(response.status_code, 200)

        # Check for Add Article buttons for each feed
        for feed in [feed1, feed2, feed3]:
            self.assertContains(
                response,
                f'href="{reverse("feed-article-create", kwargs={"feed_id": feed.pk})}"',
            )
            self.assertContains(response, "Add Article")

        # Verify order by checking the sequence of feeds in the response content
        content = response.content.decode()
        pos_feed1 = content.find(f'"{feed1.name}"')
        pos_feed2 = content.find(f'"{feed2.name}"')
        pos_feed3 = content.find(f'"{feed3.name}"')

        # Check for ascending order by ID
        self.assertLess(pos_feed1, pos_feed2)
        self.assertLess(pos_feed2, pos_feed3)
