from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.views.generic import TemplateView, CreateView

from .forms import ArticleSubmissionForm
from .models import Feed


class HomeView(TemplateView):
    """Basic home page view."""

    template_name = "index.html"


class ArticleCreateView(LoginRequiredMixin, CreateView):
    """View for submitting new articles."""

    form_class = ArticleSubmissionForm
    template_name = "article_form.html"
    success_url = reverse_lazy("home")

    def form_valid(self, form):
        feed, _ = Feed.objects.get_or_create(
            user=self.request.user, name="Default"
        )
        article = form.save(commit=False)
        article.feed = feed
        article.save()
        return super().form_valid(form)


class SignUpView(CreateView):
    """View for registering a new user."""

    form_class = UserCreationForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("login")
