"""Views for cost tracking and usage statistics."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.views.generic import TemplateView
from .models import OpenAIUsageStats, Article
from .services.cost_calculator import format_cost_display

logger = logging.getLogger(__name__)


class UsageDashboardView(LoginRequiredMixin, TemplateView):
    """View for displaying user's OpenAI usage statistics and costs."""

    template_name = 'text_to_audio/usage_dashboard.html'

    def get_context_data(self, **kwargs):
        """Get usage statistics and cost data for the user."""
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Get date ranges for filtering
        now = timezone.now()
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
        last_30_days = now - timedelta(days=30)

        # Base queryset for user's usage
        user_usage = OpenAIUsageStats.objects.filter(user=user)

        # Current month statistics
        current_month_usage = user_usage.filter(request_timestamp__gte=current_month_start)
        current_month_stats = current_month_usage.aggregate(
            total_cost=Sum('estimated_cost'),
            total_tokens=Sum('tokens_used'),
            total_requests=Count('id'),
            llm_requests=Count('id', filter=Q(operation_type='LLM')),
            tts_requests=Count('id', filter=Q(operation_type='TTS'))
        )

        # Last month statistics
        last_month_usage = user_usage.filter(
            request_timestamp__gte=last_month_start,
            request_timestamp__lt=current_month_start
        )
        last_month_stats = last_month_usage.aggregate(
            total_cost=Sum('estimated_cost'),
            total_tokens=Sum('tokens_used'),
            total_requests=Count('id')
        )

        # Last 30 days statistics
        last_30_days_usage = user_usage.filter(request_timestamp__gte=last_30_days)
        last_30_days_stats = last_30_days_usage.aggregate(
            total_cost=Sum('estimated_cost'),
            total_tokens=Sum('tokens_used'),
            total_requests=Count('id')
        )

        # All-time statistics
        all_time_stats = user_usage.aggregate(
            total_cost=Sum('estimated_cost'),
            total_tokens=Sum('tokens_used'),
            total_requests=Count('id')
        )

        # Recent activity (last 10 usage records)
        recent_usage = user_usage.select_related('article')[:10]

        # Per-article costs (top 10 most expensive)
        article_costs = user_usage.filter(
            article__isnull=False
        ).values(
            'article__id', 'article__title'
        ).annotate(
            total_cost=Sum('estimated_cost'),
            total_tokens=Sum('tokens_used'),
            request_count=Count('id')
        ).order_by('-total_cost')[:10]

        # Model usage breakdown
        model_usage = user_usage.values('model_name').annotate(
            total_cost=Sum('estimated_cost'),
            total_tokens=Sum('tokens_used'),
            request_count=Count('id')
        ).order_by('-total_cost')

        # Operation type breakdown
        operation_usage = user_usage.values('operation_type').annotate(
            total_cost=Sum('estimated_cost'),
            total_tokens=Sum('tokens_used'),
            request_count=Count('id')
        ).order_by('-total_cost')

        # Format costs for display
        def format_stats(stats):
            """Format statistics with proper cost display."""
            return {
                'total_cost': format_cost_display(stats['total_cost'] or Decimal('0')),
                'total_tokens': stats['total_tokens'] or 0,
                'total_requests': stats['total_requests'] or 0,
                'llm_requests': stats.get('llm_requests', 0),
                'tts_requests': stats.get('tts_requests', 0)
            }

        context.update({
            'current_month_stats': format_stats(current_month_stats),
            'last_month_stats': format_stats(last_month_stats),
            'last_30_days_stats': format_stats(last_30_days_stats),
            'all_time_stats': format_stats(all_time_stats),
            'recent_usage': recent_usage,
            'article_costs': [
                {
                    **item,
                    'total_cost': format_cost_display(item['total_cost'] or Decimal('0'))
                }
                for item in article_costs
            ],
            'model_usage': [
                {
                    **item,
                    'total_cost': format_cost_display(item['total_cost'] or Decimal('0'))
                }
                for item in model_usage
            ],
            'operation_usage': [
                {
                    **item,
                    'total_cost': format_cost_display(item['total_cost'] or Decimal('0'))
                }
                for item in operation_usage
            ],
            'current_month_name': current_month_start.strftime('%B %Y'),
            'last_month_name': last_month_start.strftime('%B %Y'),
        })

        return context


class ArticleCostDetailView(LoginRequiredMixin, TemplateView):
    """View for displaying detailed cost breakdown for a specific article."""

    template_name = 'text_to_audio/article_cost_detail.html'

    def get_context_data(self, **kwargs):
        """Get detailed cost breakdown for a specific article."""
        context = super().get_context_data(**kwargs)
        article_id = kwargs.get('article_id')
        user = self.request.user

        # Get the article (ensure user owns it)
        try:
            article = Article.objects.get(id=article_id, feed__user=user)
        except Article.DoesNotExist:
            # Handle this in template or redirect
            context['article'] = None
            context['error'] = 'Article not found or access denied.'
            return context

        # Get all usage records for this article
        usage_records = OpenAIUsageStats.objects.filter(
            article=article
        ).order_by('-request_timestamp')

        # Calculate totals
        totals = usage_records.aggregate(
            total_cost=Sum('estimated_cost'),
            total_tokens=Sum('tokens_used'),
            total_requests=Count('id'),
            llm_requests=Count('id', filter=Q(operation_type='LLM')),
            tts_requests=Count('id', filter=Q(operation_type='TTS'))
        )

        # Group by operation type
        operation_breakdown = usage_records.values('operation_type').annotate(
            total_cost=Sum('estimated_cost'),
            total_tokens=Sum('tokens_used'),
            request_count=Count('id')
        ).order_by('-total_cost')

        # Group by model
        model_breakdown = usage_records.values('model_name').annotate(
            total_cost=Sum('estimated_cost'),
            total_tokens=Sum('tokens_used'),
            request_count=Count('id')
        ).order_by('-total_cost')

        context.update({
            'article': article,
            'usage_records': usage_records,
            'totals': {
                'total_cost': format_cost_display(totals['total_cost'] or Decimal('0')),
                'total_tokens': totals['total_tokens'] or 0,
                'total_requests': totals['total_requests'] or 0,
                'llm_requests': totals['llm_requests'] or 0,
                'tts_requests': totals['tts_requests'] or 0
            },
            'operation_breakdown': [
                {
                    **item,
                    'total_cost': format_cost_display(item['total_cost'] or Decimal('0'))
                }
                for item in operation_breakdown
            ],
            'model_breakdown': [
                {
                    **item,
                    'total_cost': format_cost_display(item['total_cost'] or Decimal('0'))
                }
                for item in model_breakdown
            ]
        })

        return context
