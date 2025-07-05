"""Service for generating detailed voice parameters for text-to-speech."""

import logging

from text_to_audio.services.content_analysis import ContentAnalysisService
from text_to_audio.services.genre_classification import GenreClassificationService
from text_to_audio.services.voice_genre_templates import VoiceGenreTemplateService

logger = logging.getLogger(__name__)


def _is_mock_object(obj):
    """Check if an object is a mock (for testing)."""
    return obj is not None and hasattr(obj, "_mock_name")


class VoiceParameterGenerationService:
    """Service for generating detailed voice parameters for text-to-speech."""

    def __init__(self, openai_api_key=None):
        """Initialize with optional API key override and required services."""
        self.openai_api_key = openai_api_key
        self.genre_service = GenreClassificationService(openai_api_key=openai_api_key)
        self.content_service = ContentAnalysisService(openai_api_key=openai_api_key)
        self.template_service = VoiceGenreTemplateService()
        self._client = None

    @property
    def client(self):
        """Lazily initialize OpenAI client."""
        if self._client is None:
            import openai
            from django.conf import settings

            self._client = openai.OpenAI(
                api_key=self.openai_api_key or settings.OPENAI_API_KEY
            )
        return self._client

    def generate_voice_parameters(self, article):
        """
        Generate comprehensive voice parameters for an article.

        This method integrates genre classification, content analysis, and
        template-based parameter generation to create detailed voice
        configuration for optimal TTS performance.

        Args:
            article: Article object with text_content and title

        Returns:
            Dict with comprehensive voice parameters
        """
        # Step 1: Classify the genre
        genre_result = self.genre_service.classify_genre(
            article.text_content, title=article.title
        )
        genre = genre_result["genre"]
        voice_suggestions = genre_result.get("voice_suggestions", {})

        # Step 2: Get template for the genre
        template = self.template_service.get_template_by_genre(genre)

        # Step 3: Reuse existing content analysis or perform new analysis
        # Check if content analysis has already been performed and stored
        content_analysis = None
        if hasattr(article, "multi_voice_data") and article.multi_voice_data:
            # Reuse existing analysis to avoid duplicate LLM calls
            logger.info(f"Reusing existing content analysis for article {article.id}")
            content_analysis = article.multi_voice_data
            # Validate that we got actual data, not a mock
            if _is_mock_object(content_analysis):
                content_analysis = None

        # Only perform new analysis if we don't have valid existing data
        if not content_analysis:
            try:
                logger.info(f"Performing new content analysis for article {article.id}")
                content_analysis = self.content_service.analyze_content(
                    article.text_content, title=article.title
                )
                # Validate that we got actual data, not a mock
                if _is_mock_object(content_analysis):
                    content_analysis = None
            except Exception as e:
                logger.error(f"Content analysis failed: {e}")
                content_analysis = None

        # Step 4: Combine all inputs to generate final voice parameters
        voice_parameters = self._generate_parameters(
            genre=genre,
            template=template,
            voice_suggestions=voice_suggestions,
            content_analysis=content_analysis,
        )

        # Step 5: Save the parameters to the article
        article.detected_genre = genre
        article.voice_parameters = voice_parameters

        # Set the primary voice from the parameters using single source of truth
        if "voice_id" in voice_parameters:
            voice_value = voice_parameters["voice_id"]
            # Determine if this is a standard voice or custom voice
            from text_to_audio.models import VOICE_CHOICES

            standard_voices = [choice[0] for choice in VOICE_CHOICES]

            if voice_value in standard_voices:
                # Use standard voice field for predefined voices
                article.voice = voice_value
                article.voice_id = None  # Clear the custom field
            else:
                # Use voice_id field for custom voices
                article.voice_id = voice_value
                # Don't set voice field - let clean() method handle it

        # Set the speed from the parameters
        if "speed" in voice_parameters:
            article.speed = voice_parameters["speed"]

        # Persist generated parameters on the article
        article.save(
            update_fields=[
                "detected_genre",
                "voice_parameters",
                "voice_id",
                "voice",
                "speed",
            ]
        )

        # Return the complete parameters
        return voice_parameters

    def _generate_parameters(
        self, genre, template, voice_suggestions, content_analysis
    ):
        """
        Generate final voice parameters by combining all inputs.

        Args:
            genre: Detected content genre
            template: Genre-based template parameters
            voice_suggestions: LLM-suggested voice parameters
            content_analysis: Result from content analysis

        Returns:
            Dict with comprehensive voice parameters
        """
        # Start with base parameters from the genre template
        parameters = {}
        if template:
            parameters.update(template)

        # Use the first voice from content analysis as the default narrator
        if (
            content_analysis
            and "voices" in content_analysis
            and content_analysis["voices"]
        ):
            narrator = content_analysis["voices"][0]

            # Extract voice_id and speed from content analysis
            if "tts_model" in narrator:
                parameters["voice_id"] = narrator["tts_model"]
            if "tts_speed" in narrator:
                parameters["speed"] = narrator["tts_speed"]
            if "tone" in narrator:
                parameters["tone"] = narrator["tone"]

        # Apply LLM suggestions for voice parameters
        if voice_suggestions:
            for key, value in voice_suggestions.items():
                if (
                    key not in parameters or value
                ):  # Only override if not set or not empty
                    parameters[key] = value

        # Store the complete multi-voice configuration if available
        if content_analysis:
            parameters["multi_voice_config"] = {
                "voices": content_analysis.get("voices", []),
                "audio_segments": content_analysis.get("audio_segments", []),
            }

        # Validate voice_id and speed (required parameters)
        if "voice_id" not in parameters:
            parameters["voice_id"] = "alloy"  # Default voice

        if "speed" not in parameters:
            parameters["speed"] = 1.0  # Default speed

        # Ensure speed is within allowed range
        parameters["speed"] = max(0.75, min(1.5, float(parameters["speed"])))

        return parameters

    def generate_enhanced_prompt(self, voice_parameters):
        """
        Generate an enhanced TTS prompt based on voice parameters.

        Args:
            voice_parameters: Dict with voice parameters

        Returns:
            String prompt for TTS system
        """
        # Extract key parameters
        affect = voice_parameters.get("affect", "")
        tone = voice_parameters.get("tone", "")
        pacing = voice_parameters.get("pacing", "")
        pitch_variation = voice_parameters.get("pitch_variation", "")
        speaking_style = voice_parameters.get("speaking_style", "")

        # Build the prompt
        prompt_parts = []

        if affect:
            prompt_parts.append(f"Speak with a {affect} affect.")

        if tone:
            prompt_parts.append(f"Use a {tone} tone.")

        if pacing:
            prompt_parts.append(f"Maintain a {pacing} pace.")

        if pitch_variation:
            prompt_parts.append(f"Use {pitch_variation} pitch variation.")

        if speaking_style:
            prompt_parts.append(f"{speaking_style}")

        # Combine all parts
        if prompt_parts:
            return " ".join(prompt_parts)

        # Fallback to a generic prompt
        return "Speak in a clear, engaging manner."
