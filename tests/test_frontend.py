"""Tests for the frontend templates and views."""

# mypy: disable-error-code="attr-defined"

import os
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup
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

    def test_footer_contains_current_year(self):
        """Test that the footer displays the current year dynamically."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        current_year = datetime.now().year
        self.assertContains(response, f"&copy; {current_year} RSS-TTS")


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

    def test_article_form_has_file_upload(self):
        """Article submission form should include a file upload field."""
        self.client.login(username="tester", password="pass123")
        response = self.client.get(f"/feeds/{self.feed.pk}/add/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'name="document_file"')

    def test_post_creates_article(self):
        """Test that submitting the article form creates a new article."""
        self.client.login(username="tester", password="pass123")
        with patch("text_to_audio.views.process_article.delay") as mock_delay:
            # Configure mock to return a task with an ID
            mock_task = MagicMock()
            mock_task.id = "mock-task-id-frontend"
            mock_delay.return_value = mock_task

            response = self.client.post(
                f"/feeds/{self.feed.pk}/add/",
                {"title": "Test", "text_content": "Hello"},
            )
            self.assertEqual(response.status_code, 302)
            self.assertTrue(Article.objects.filter(title="Test").exists())

            # Verify task ID was saved to the article
            article = Article.objects.get(title="Test")
            self.assertEqual(article.celery_task_id, "mock-task-id-frontend")
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

    def test_login_form_has_accessible_labels(self):
        """Test that login form inputs have proper <label for> elements and Bootstrap classes."""
        response = self.client.get("/accounts/login/")
        content = response.content.decode()
        # Explicit labels with for attribute
        self.assertIn('<label for="id_username"', content)
        self.assertIn('<label for="id_password"', content)
        # Inputs with matching ids
        self.assertIn('id="id_username"', content)
        self.assertIn('id="id_password"', content)
        # Bootstrap form-control class on inputs
        self.assertContains(response, 'class="form-control"')

    def test_login_form_shows_field_errors(self):
        """Test that login form renders error messages on invalid POST."""
        response = self.client.post(
            "/accounts/login/",
            {"username": "", "password": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")


class TestSignUpView(TestCase):
    """Tests for the user signup view."""

    def setUp(self):
        """Set up the test environment for signup tests.

        Create a test client for testing user registration.
        """
        self.client = Client()

    def test_signup_page_renders_when_no_users_exist(self):
        """Sign up page should render when no users are present."""
        response = self.client.get("/accounts/signup/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/signup.html")

    def test_first_user_becomes_superadmin(self):
        """First signup should create a superadmin account."""
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
        user = User.objects.get(username="newuser")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)

    def test_signup_form_has_accessible_labels(self):
        """Test that signup form inputs have proper <label for> elements and Bootstrap classes."""
        response = self.client.get("/accounts/signup/")
        content = response.content.decode()
        # Explicit labels with for attribute
        self.assertIn('<label for="id_username"', content)
        self.assertIn('<label for="id_password1"', content)
        self.assertIn('<label for="id_password2"', content)
        # Inputs with matching ids
        self.assertIn('id="id_username"', content)
        self.assertIn('id="id_password1"', content)
        self.assertIn('id="id_password2"', content)
        # Bootstrap form-control class on inputs
        self.assertContains(response, 'class="form-control"')

    def test_signup_form_shows_field_errors(self):
        """Test that signup form renders error messages on invalid POST."""
        response = self.client.post(
            "/accounts/signup/",
            {
                "username": "newuser",
                "password1": "short",
                "password2": "mismatch",
            },
        )
        self.assertEqual(response.status_code, 200)
        # Should show password mismatch error
        self.assertContains(response, "password")

    def test_signup_password_help_text_escapes_html(self):
        """Password help_text must be HTML-escaped to prevent XSS."""
        response = self.client.get("/accounts/signup/")
        self.assertEqual(response.status_code, 200)
        # Temporarily override help_text with a malicious script tag
        from django.contrib.auth.forms import UserCreationForm

        form = UserCreationForm()
        form.fields["password1"].help_text = '<script>alert("xss")</script>'
        # Re-render the template with the malicious form
        from django.template.loader import render_to_string

        html = render_to_string("registration/signup.html", {"form": form})
        # The raw <script> tag must NOT appear — it should be escaped
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_signup_password_help_text_displays_requirements(self):
        """Password requirements should still be visible on the signup page."""
        response = self.client.get("/accounts/signup/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Django's default password validators produce text about requirements
        self.assertIn("password", content.lower())

    def test_signup_disabled_when_user_exists(self):
        """Additional signups should redirect to login and not create users."""
        User = get_user_model()
        User.objects.create_user(username="existing", password="pass")

        response = self.client.get("/accounts/signup/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/accounts/login/")

        response = self.client.post(
            "/accounts/signup/",
            {
                "username": "other",
                "password1": "ComplexPass123",
                "password2": "ComplexPass123",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/accounts/login/")
        self.assertFalse(User.objects.filter(username="other").exists())


class TestFeedArticleAutoUpdate(TestCase):
    """Tests for automatic feed updates via JavaScript polling."""

    def setUp(self):
        """Create user, feed and sample article."""
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="autoupdate", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Default")
        Article.objects.create(
            feed=self.feed,
            title="Update Test",
            text_content="sample",
            status=Article.PROCESSING,
        )

    def test_article_list_contains_update_script(self):
        """Verify external JS file is referenced and data attributes are in the HTML."""
        self.client.login(username="autoupdate", password="pass123")
        response = self.client.get(f"/feeds/{self.feed.pk}/")
        self.assertContains(response, "text_to_audio/js/article_list.js")
        self.assertContains(response, "data-article-id")
        self.assertContains(response, "status-badge")
        self.assertContains(response, "action-cell")


class TestPlayButtonToggle(TestCase):
    """Tests for play button pause functionality."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="playuser", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Default")
        Article.objects.create(
            feed=self.feed,
            title="Toggle Test",
            text_content="sample",
            status=Article.COMPLETED,
            audio_uuid=str(uuid.uuid4()),
        )

    def test_article_list_contains_pause_script(self):
        self.client.login(username="playuser", password="pass123")
        response = self.client.get(f"/feeds/{self.feed.pk}/")
        self.assertContains(response, "text_to_audio/js/article_list.js")


class TestArticleListAccessibility(TestCase):
    """Tests for accessibility of SVG icons and buttons in article_list.html."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="a11yuser", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="A11y Feed")
        # Create a completed article so all action buttons render
        self.article = Article.objects.create(
            feed=self.feed,
            title="Accessibility Test Article",
            text_content="sample content",
            status=Article.COMPLETED,
            audio_uuid=str(uuid.uuid4()),
        )
        # Create a failed article to get retry/delete buttons for that state
        self.failed_article = Article.objects.create(
            feed=self.feed,
            title="Failed Article",
            text_content="sample",
            status=Article.FAILED,
            error_message="Test error",
        )
        self.client.login(username="a11yuser", password="pass123")

    def _get_soup(self):
        """Get BeautifulSoup parsed response from article list page."""
        response = self.client.get(f"/feeds/{self.feed.pk}/")
        self.assertEqual(response.status_code, 200)
        return BeautifulSoup(response.content.decode(), "html.parser")

    def test_article_list_svg_icons_have_aria_hidden(self):
        """All server-rendered SVG elements should have aria-hidden='true'."""
        soup = self._get_soup()
        svgs = soup.find_all("svg")
        self.assertGreater(len(svgs), 0, "Expected SVG elements in article list")
        for svg in svgs:
            self.assertEqual(
                svg.get("aria-hidden"),
                "true",
                f"SVG with class='{svg.get('class')}' missing aria-hidden='true'",
            )

    def test_article_list_copy_buttons_have_aria_labels(self):
        """Copy buttons should have descriptive aria-label attributes."""
        soup = self._get_soup()
        copy_button = soup.find("button", id="copy-button")
        if copy_button:
            self.assertTrue(
                copy_button.get("aria-label"),
                "Copy Feed URL button missing aria-label",
            )
        copy_api_button = soup.find("button", id="copy-api-button")
        if copy_api_button:
            self.assertTrue(
                copy_api_button.get("aria-label"),
                "Copy API URL button missing aria-label",
            )
        copy_email_button = soup.find("button", id="copy-email-button")
        if copy_email_button:
            self.assertTrue(
                copy_email_button.get("aria-label"),
                "Copy Email button missing aria-label",
            )

    def test_article_list_action_buttons_have_accessible_text(self):
        """Buttons with SVGs should also contain visible text labels."""
        soup = self._get_soup()
        # Check action buttons that contain SVGs have text content
        action_cells = soup.find_all("td", class_="action-cell")
        for cell in action_cells:
            buttons_and_links = cell.find_all(["button", "a"])
            for element in buttons_and_links:
                svg = element.find("svg")
                if svg:
                    # Get text content excluding SVG
                    text = element.get_text(strip=True)
                    # Remove any SVG text content
                    svg_text = svg.get_text(strip=True)
                    visible_text = text.replace(svg_text, "").strip()
                    self.assertTrue(
                        visible_text,
                        f"Button/link with SVG has no visible text label: {element.get('class')}",
                    )
