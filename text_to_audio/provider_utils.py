"""Utility functions for provider selection and management."""

import logging

from text_to_audio.models import Feed

logger = logging.getLogger(__name__)


def get_content_analysis_client(feed: Feed):
    """Get the appropriate content analysis client based on feed preferences.

    Args:
        feed: The Feed instance to get provider preferences from

    Returns:
        Either an OpenAI client or Anthropic client based on feed.llm_provider

    Raises:
        ValueError: If provider is not supported or API key is missing
    """
    if feed.llm_provider == Feed.PROVIDER_ANTHROPIC:
        # Try Anthropic first
        try:
            import anthropic

            from appconfig.utils import get_anthropic_api_key

            api_key = get_anthropic_api_key()
            if not api_key:
                logger.warning(
                    f"No Anthropic API key configured for feed {feed.id}, falling back to OpenAI"
                )
                return _get_openai_client()

            logger.info(
                f"Using Anthropic Claude for content analysis on feed {feed.id}"
            )
            return anthropic.Anthropic(api_key=api_key)

        except ImportError:
            logger.warning("Anthropic SDK not installed, falling back to OpenAI")
            return _get_openai_client()
        except Exception as e:
            logger.warning(
                f"Failed to initialize Anthropic client: {e}, falling back to OpenAI"
            )
            return _get_openai_client()

    # Default to OpenAI
    return _get_openai_client()


def _get_openai_client():
    """Get OpenAI client with error handling."""
    import openai

    from appconfig.utils import get_openai_api_key

    api_key = get_openai_api_key()
    if not api_key:
        raise ValueError("No OpenAI API key configured")

    return openai.OpenAI(api_key=api_key)


def get_anthropic_model_name(feed: Feed) -> str:
    """Get the Anthropic model name for the given feed."""
    from appconfig.utils import get_anthropic_model

    return get_anthropic_model()


def get_openai_analysis_model(feed: Feed) -> str:
    """Get the OpenAI analysis model name for the given feed."""
    from appconfig.utils import get_openai_analysis_model

    return get_openai_analysis_model()
