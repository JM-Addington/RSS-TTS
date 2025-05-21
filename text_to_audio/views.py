from django.views.generic import TemplateView


class HomeView(TemplateView):
    """Basic home page view."""

    template_name = "index.html"
