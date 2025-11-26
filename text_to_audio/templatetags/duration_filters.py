"""Template filters for formatting duration values."""

from django import template

register = template.Library()


@register.filter
def format_duration(seconds):
    """Format seconds as human-readable duration (e.g., '2h 15m' or '45m').

    Args:
        seconds: Duration in seconds (int or None)

    Returns:
        Human-readable duration string, or empty string if no duration
    """
    if seconds is None or seconds == 0:
        return ""

    try:
        seconds = int(seconds)
    except (ValueError, TypeError):
        return ""

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    if hours > 0:
        if minutes > 0:
            return f"{hours}h {minutes}m"
        return f"{hours}h"
    elif minutes > 0:
        return f"{minutes}m"
    else:
        return "<1m"
