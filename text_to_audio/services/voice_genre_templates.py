"""Service for managing voice genre templates."""

from text_to_audio.models import VoiceGenreTemplate


class VoiceGenreTemplateService:
    """Service for managing voice genre templates."""

    # Default genre categories with their descriptions
    DEFAULT_GENRES = {
        "news": "Factual, journalistic style content reporting current events",
        "documentary": "Educational content with a narrative structure",
        "fiction": "Creative storytelling with characters and plot",
        "technical": "Detailed explanations of technical concepts or processes",
        "academic": "Scholarly or scientific content with formal language",
        "conversational": "Informal, dialog-heavy content",
        "persuasive": "Content designed to convince or persuade",
        "instructional": "Step-by-step guidance or tutorials",
    }

    # Example template parameters for each genre
    DEFAULT_TEMPLATES = {
        "news": {
            "voice_id": "nova",
            "speed": 1.1,
            "affect": "neutral",
            "tone": "clear, factual",
            "pacing": "steady",
            "pitch_variation": "moderate",
            "speaking_style": "NPR reporter style, professional, straightforward",
        },
        "documentary": {
            "voice_id": "onyx",
            "speed": 0.95,
            "affect": "thoughtful",
            "tone": "authoritative, engaging",
            "pacing": "measured",
            "pitch_variation": "moderate",
            "speaking_style": "nature documentary narrator, deliberate, informative",
        },
        "fiction": {
            "voice_id": "echo",
            "speed": 0.9,
            "affect": "expressive",
            "tone": "narrative, emotive",
            "pacing": "varied",
            "pitch_variation": "high",
            "speaking_style": "audiobook narrator, character-driven, dramatic at times",
        },
        "technical": {
            "voice_id": "alloy",
            "speed": 0.95,
            "affect": "focused",
            "tone": "precise, detailed",
            "pacing": "deliberate",
            "pitch_variation": "low",
            "speaking_style": "expert explaining a complex topic, clear enunciation",
        },
        "academic": {
            "voice_id": "onyx",
            "speed": 0.9,
            "affect": "analytical",
            "tone": "formal, scholarly",
            "pacing": "methodical",
            "pitch_variation": "low",
            "speaking_style": "university lecturer, thoughtful, emphasizing key points",
        },
        "conversational": {
            "voice_id": "nova",
            "speed": 1.15,
            "affect": "friendly",
            "tone": "warm, personal",
            "pacing": "natural",
            "pitch_variation": "high",
            "speaking_style": "podcast host, engaging, with natural rhythm",
        },
        "persuasive": {
            "voice_id": "shimmer",
            "speed": 1.05,
            "affect": "confident",
            "tone": "compelling, enthusiastic",
            "pacing": "dynamic",
            "pitch_variation": "high",
            "speaking_style": "TED talk presenter, passionate, emphasizing key points",
        },
        "instructional": {
            "voice_id": "fable",
            "speed": 1.0,
            "affect": "helpful",
            "tone": "clear, supportive",
            "pacing": "steady",
            "pitch_variation": "moderate",
            "speaking_style": "tutorial guide, patient, with clear transitions",
        },
    }

    def __init__(self, templates=None):
        """Initialize with optional templates override."""
        self.templates = templates or self.DEFAULT_TEMPLATES

    def get_template_by_genre(self, genre):
        """
        Get voice template for a specific genre.

        Args:
            genre: The content genre

        Returns:
            Dict with voice template parameters or None if genre not found
        """
        return self.templates.get(genre.lower())

    def get_all_templates(self):
        """
        Get all available templates.

        Returns:
            Dict of genre -> template mappings
        """
        return self.templates

    def get_available_genres(self):
        """
        Get list of available genres with descriptions.

        Returns:
            List of tuples: [(genre_name, description), ...]
        """
        return [
            (genre, self.DEFAULT_GENRES.get(genre, ""))
            for genre in self.templates.keys()
        ]

    def create_template_from_genre(self, genre):
        """
        Create a VoiceGenreTemplate object from a predefined genre.

        Args:
            genre: Genre name to use as template

        Returns:
            Dict with template parameters or None if genre not found
        """
        template_params = self.get_template_by_genre(genre)
        if not template_params:
            return None

        return template_params

    def load_templates_from_db(self):
        """
        Load templates from database and merge with defaults.

        Returns:
            Dict of genre -> template mappings
        """
        db_templates = {}

        for template in VoiceGenreTemplate.objects.filter(is_active=True):
            db_templates[template.genre] = {
                "voice_id": template.voice_id,
                "speed": template.speed,
                "affect": template.affect,
                "tone": template.tone,
                "pacing": template.pacing,
                "pitch_variation": template.pitch_variation,
                "speaking_style": template.speaking_style,
            }

        # Merge with defaults, prioritizing DB templates
        merged = self.DEFAULT_TEMPLATES.copy()
        merged.update(db_templates)

        return merged
