"""Service for analyzing article content."""

import json
import logging

logger = logging.getLogger(__name__)


class ContentAnalysisService:
    """Service for analyzing article content."""

    def __init__(self, openai_api_key=None):
        """Initialize with optional API key override."""
        self.openai_api_key = openai_api_key
        self._client = None

    @property
    def client(self):
        """Lazily initialize OpenAI client."""
        if self._client is None:
            from django.conf import settings
            import openai
            self._client = openai.OpenAI(
                api_key=self.openai_api_key or settings.OPENAI_API_KEY
            )
        return self._client

    def analyze_content(self, text, title=None, max_tokens=500):
        """
        Analyze article content to detect tone and generate summary.
        
        Args:
            text: The article text to analyze
            title: Optional article title for context
            max_tokens: Maximum tokens for the response
            
        Returns:
            dict with keys:
                - tone: Detected tone of the article
                - summary: Generated summary
                - voice_recommendation: Recommended voice settings
        """
        # Prepare a sample of the text for analysis (first 2000 chars)
        text_sample = text[:2000]
        
        # Create the unified prompt
        prompt = self._create_analysis_prompt(text_sample, title)
        
        # Call OpenAI API with JSON mode
        response = self.client.chat.completions.create(
            model=self._get_analysis_model(),
            messages=[
                {"role": "system", "content": "You are an expert content analyzer."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        # Parse the response
        try:
            content = response.choices[0].message.content
            result = json.loads(content)
            return {
                "tone": result.get("tone", "neutral"),
                "summary": result.get("summary", ""),
                "voice_recommendation": result.get("voice_recommendation", {})
            }
        except (json.JSONDecodeError, AttributeError, IndexError) as e:
            logger.error(f"Error parsing content analysis response: {e}")
            # Return sensible defaults
            return {
                "tone": "neutral",
                "summary": "",
                "voice_recommendation": {"voice": "alloy", "speed": 1.0}
            }
            
    def _create_analysis_prompt(self, text, title):
        """Create the unified prompt for content analysis."""
        title_context = f" titled '{title}'" if title else ""
        return f"""
        Analyze the following article{title_context} and provide:
        
        1. A concise 2-3 sentence summary of the main points
        2. The overall tone of the article (e.g., formal, casual, technical, storytelling)
        3. A recommendation for voice parameters that would be appropriate for narrating this content
        
        Return your analysis in the following JSON format:
        {{
            "summary": "2-3 sentence summary here",
            "tone": "detected tone (one of: formal, casual, technical, storytelling, narrative, news, conversational)",
            "voice_recommendation": {{
                "voice": "recommended voice (one of: alloy, echo, fable, onyx, nova, shimmer)",
                "speed": recommended speed (float between 0.75 and 1.5)
            }}
        }}
        
        Article:
        {text}
        """
        
    def _get_analysis_model(self):
        """Get the model to use for content analysis."""
        from django.conf import settings
        return getattr(settings, "OPENAI_ANALYSIS_MODEL", "o4-mini")