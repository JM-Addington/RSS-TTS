import os
from django.conf import settings
from django.test import Client, TestCase


class TestFrontendTemplates(TestCase):
    """Tests for basic frontend templates and views."""

    def setUp(self):
        self.client = Client()

    def _template_path(self, relative):
        return os.path.join(settings.BASE_DIR, "text_to_audio", "templates", *relative.split("/"))

    def test_base_template_exists(self):
        self.assertTrue(os.path.isfile(self._template_path("base.html")), "base.html not found")

    def test_partial_templates_exist(self):
        for name in ("partials/_nav.html", "partials/_header.html", "partials/_footer.html"):
            self.assertTrue(os.path.isfile(self._template_path(name)), f"{name} not found")

    def test_home_view_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "index.html")
from django.contrib.auth import get_user_model
from text_to_audio.models import Article, Feed


class TestArticleSubmission(TestCase):
    """Tests for the article submission view."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="tester", password="pass123"
        )
        self.feed = Feed.objects.create(user=self.user, name="Default")

    def test_login_required(self):
        response = self.client.get("/articles/submit/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_get_form_authenticated(self):
        self.client.login(username="tester", password="pass123")
        response = self.client.get("/articles/submit/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "article_form.html")

    def test_post_creates_article(self):
        self.client.login(username="tester", password="pass123")
        response = self.client.post(
            "/articles/submit/",
            {"title": "Test", "text_content": "Hello"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Article.objects.filter(title="Test").exists())


class TestLogoutView(TestCase):
    """Tests for the logout functionality."""

    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(
            username="tester2", password="pass123"
        )
        self.client.login(username="tester2", password="pass123")

    def test_logout(self):
        response = self.client.post("/accounts/logout/")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)


class TestSignUpView(TestCase):
    """Tests for the user signup view."""

    def setUp(self):
        self.client = Client()

    def test_signup_page_renders(self):
        response = self.client.get("/accounts/signup/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "registration/signup.html")

    def test_post_creates_user(self):
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
