"""Service for classifying article content into genres."""

import json
import logging

logger = logging.getLogger(__name__)


class GenreClassificationService:
    """Service for classifying article content into genres."""

    # Define the available genres
    AVAILABLE_GENRES = [
        "news",
        "documentary",
        "fiction",
        "technical",
        "academic",
        "conversational",
        "persuasive",
        "instructional",
    ]

    def __init__(self, openai_api_key=None):
        """Initialize with optional API key override."""
        self.openai_api_key = openai_api_key
        self._client = None

    @property
    def client(self):
        """Lazily initialize OpenAI client."""
        if self._client is None:
            import openai

            from appconfig.utils import get_openai_api_key

            self._client = openai.OpenAI(
                api_key=self.openai_api_key or get_openai_api_key()
            )
        return self._client

    def classify_genre(self, text, title=None, max_completion_tokens=100):
        """
        Classify article content into a genre.

        Args:
            text: The article text to analyze
            title: Optional article title for context
            max_completion_tokens: Maximum tokens for the response

        Returns:
            dict with keys:
                - genre: Detected genre of the article
                - confidence: Confidence score for the classification
                - voice_suggestions: Dict with voice parameter suggestions
        """
        # Prepare a sample of the text for analysis (first 1500 chars)
        text_sample = text[:1500]

        # Create the genre classification prompt
        prompt = self._create_classification_prompt(text_sample, title)

        # Call OpenAI API with JSON mode
        response = self.client.chat.completions.create(
            model=self._get_classification_model(),
            messages=[
                {"role": "system", "content": "You are an expert content classifier."},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=max_completion_tokens,
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        # Parse the response
        try:
            content = response.choices[0].message.content
            result = json.loads(content)

            # Validate the structure
            if "genre" not in result:
                raise ValueError("Missing 'genre' in LLM response.")
            if "confidence" not in result:
                raise ValueError("Missing 'confidence' in LLM response.")
            if "voice_suggestions" not in result:
                raise ValueError("Missing 'voice_suggestions' in LLM response.")

            # Ensure the genre is in our allowed list
            genre = result["genre"].lower()
            if genre not in self.AVAILABLE_GENRES:
                # Find the closest match or default to "news"
                logger.warning(f"Genre '{genre}' not in allowed list, using default.")
                genre = "news"
                result["genre"] = genre

            return result
        except (json.JSONDecodeError, AttributeError, IndexError, ValueError) as e:
            logger.error(f"Error parsing genre classification response: {e}")
            # Return a default structure
            return {
                "genre": "news",
                "confidence": 0.5,
                "voice_suggestions": {
                    "affect": "neutral",
                    "tone": "informative",
                    "pacing": "steady",
                    "pitch_variation": "moderate",
                    "speaking_style": "Clear and factual news reporting style",
                },
            }

    def _create_classification_prompt(self, text, title):
        """Create the prompt for genre classification."""
        title_context = f" with title '{title}'" if title else ""
        return f"""
        Analyze the following text{title_context} and classify it into one of these genres:
        - news: Factual, journalistic style content reporting current events
        - documentary: Educational content with a narrative structure
        - fiction: Creative storytelling with characters and plot
        - technical: Detailed explanations of technical concepts or processes
        - academic: Scholarly or scientific content with formal language
        - conversational: Informal, dialog-heavy content
        - persuasive: Content designed to convince or persuade
        - instructional: Step-by-step guidance or tutorials

        Also, suggest appropriate voice parameters for narrating this content,
        considering the content's style, tone, and purpose.

        JSON Output Structure:
        {{
          "genre": "string (one of the genre options listed above)",
          "confidence": float (0.0 to 1.0 representing classification confidence),
          "voice_suggestions": {{
            "affect": "string (emotional quality, e.g., 'neutral', 'enthusiastic')",
            "tone": "string (e.g., 'formal', 'conversational', 'authoritative')",
            "pacing": "string (e.g., 'steady', 'varied', 'deliberate')",
            "pitch_variation": "string (e.g., 'low', 'moderate', 'high')",
            "speaking_style": "string (detailed description of ideal speaking approach)"
          }}
        }}

        Text to analyze:
        {text}
        """

    def _get_classification_model(self):
        """Get the model to use for genre classification."""
        from django.conf import settings

        return getattr(settings, "OPENAI_CLASSIFICATION_MODEL", "o4-mini")
