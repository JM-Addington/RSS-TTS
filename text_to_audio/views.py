from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView

from .forms import ArticleSubmissionForm
from .models import Feed
from .tasks import process_article


class HomeView(TemplateView):
    """Basic home page view."""

    template_name = "index.html"


class ArticleCreateView(LoginRequiredMixin, CreateView):
    """View for submitting new articles."""

    form_class = ArticleSubmissionForm
    template_name = "article_form.html"
    success_url = reverse_lazy("home")

    def form_valid(self, form):
        feed, _ = Feed.objects.get_or_create(user=self.request.user, name="Default")
        article = form.save(commit=False)
        article.feed = feed
        article.save()
        process_article.delay(article.id)
        return super().form_valid(form)
