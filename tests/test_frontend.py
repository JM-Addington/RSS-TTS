"""Tests for the frontend templates and views."""

# mypy: disable-error-code="attr-defined"

import os
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from text_to_audio.models import Article, Feed


class TestFrontendTemplates(TestCase):
    """Tests for basic frontend templates and views."""

    def setUp(self):
        """Set up the test environment.

        Initialize a test client for making HTTP requests.
        """
        self.client = Client()

    def _template_path(self, relative):
        """Convert a relative template path to an absolute filesystem path.

        Args:
            relative: Relative path to the template using forward slashes

        Returns:
            Absolute path to the template file
        """
        return os.path.join(
            settings.BASE_DIR, "text_to_audio", "templates", *relative.split("/")
        )

    def test_base_template_exists(self):
        """Test that the base template file exists."""
        self.assertTrue(
            os.path.isfile(self._template_path("base.html")), "base.html not found"
        )

    def test_partial_templates_exist(self):
        """Test that all required partial template files exist."""
        for name in (
            "partials/_nav.html",
            "partials/_header.html",
            "partials/_footer.html",
        ):
            self.assertTrue(
                os.path.isfile(self._template_path(name)), f"{name} not found"
            )

    def test_home_view_renders(self):
        """Test that the home page view renders successfully.

        Verifies the response status and template used.
        """
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "index.html")


class TestArticleSubmission(TestCase):
    """Tests for the article submission view."""

    def setUp(self):
        """Set up the test environment for article submission tests.

        Create a test client, user account, and feed for testing article submission.
        """
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="tester", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Default")

    def test_login_required(self):
        """Test that the article submission view requires authentication."""
        response = self.client.get("/articles/submit/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_get_form_authenticated(self):
        """Test that authenticated users can access the article submission form."""
        self.client.login(username="tester", password="pass123")
        response = self.client.get("/articles/submit/")
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/feeds/{self.feed.pk}/add/", response["Location"])

        follow_response = self.client.get(response["Location"])
        self.assertEqual(follow_response.status_code, 200)
        self.assertTemplateUsed(follow_response, "article_form.html")

    def test_post_creates_article(self):
        """Test that submitting the article form creates a new article."""
        self.client.login(username="tester", password="pass123")
        with patch("text_to_audio.views.process_article.delay") as mock_delay:
            response = self.client.post(
                f"/feeds/{self.feed.pk}/add/",
                {"title": "Test", "text_content": "Hello"},
            )
            self.assertEqual(response.status_code, 302)
            self.assertTrue(Article.objects.filter(title="Test").exists())
            mock_delay.assert_called_once()


class TestLogoutView(TestCase):
    """Tests for the logout functionality."""

    def setUp(self):
        """Set up the test environment for logout tests.

        Create a test client, user account, and login the user.
        """
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="tester2", password="pass123"
        )
        self.client.login(username="tester2", password="pass123")

    def test_logout(self):
        """Test that the logout endpoint successfully logs out the user."""
        response = self.client.post("/accounts/logout/")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)


class TestLoginView(TestCase):
    """Tests for the login functionality."""

    def setUp(self):
        """Set up the test environment for login tests.

        Create a test client and user account for testing login functionality.
        """
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="logintest", password="pass123"
        )

    def test_login_page_renders(self):
        """Test that the login page renders correctly.

        Verifies status code and template used.
        """
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/login.html")

    def test_successful_login(self):
        """Test that a user can successfully log in with correct credentials."""
        response = self.client.post(
            "/accounts/login/",
            {"username": "logintest", "password": "pass123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")  # Default redirect to home
        self.assertIn("_auth_user_id", self.client.session)

    def test_failed_login(self):
        """Test that login fails with incorrect credentials and shows error message."""
        response = self.client.post(
            "/accounts/login/",
            {"username": "logintest", "password": "wrongpassword"},
        )
        self.assertEqual(response.status_code, 200)  # Stays on the login page
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "Please enter a correct username and password")


class TestSignUpView(TestCase):
    """Tests for the user signup view."""

    def setUp(self):
        """Set up the test environment for signup tests.

        Create a test client for testing user registration.
        """
        self.client = Client()

    def test_signup_page_renders(self):
        """Test that the signup page renders correctly with the proper template."""
        response = self.client.get("/accounts/signup/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/signup.html")

    def test_post_creates_user(self):
        """Test user creation through the signup form.

        Verifies new user creation and redirect.
        """
        response = self.client.post(
            "/accounts/signup/",
            {
                "username": "newuser",
                "password1": "ComplexPass123",
                "password2": "ComplexPass123",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])
        User = get_user_model()
        self.assertTrue(User.objects.filter(username="newuser").exists())
