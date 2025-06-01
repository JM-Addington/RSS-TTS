"""
Pydantic schemas for ChunkToneService LLM responses.
"""

import re
from typing import List, Optional

from pydantic import BaseModel, field_validator


class TTSVoice(BaseModel):
    """Voice configuration for TTS."""

    voice: str

    # Valid OpenAI TTS voice names
    VALID_VOICES = {
        "alloy", "echo", "fable", "onyx", "nova", "shimmer", "ash", "sage", "coral"
    }

    # Mapping for common logical names to OpenAI voices
    VOICE_MAPPING = {
        "narrator": "nova",
        "male_narrator": "onyx",
        "female_narrator": "nova",
        "expert": "echo",
        "expert_quote": "echo",
        "character": "fable",
        "quote": "shimmer",
        "dialogue": "fable",
        "announcer": "alloy",
        "formal": "echo",
        "casual": "shimmer",
        "elderly": "sage",
        "young": "coral",
        "serious": "onyx",
        "friendly": "nova"
    }

    @field_validator("voice")
    @classmethod
    def validate_voice(cls, v: str) -> str:
        """Validate and map voice to valid OpenAI voice names."""
        v = v.lower().strip()

        # If it's already a valid OpenAI voice, use it
        if v in cls.VALID_VOICES:
            return v

        # If it's a mapped logical name, use the mapping
        if v in cls.VOICE_MAPPING:
            mapped_voice = cls.VOICE_MAPPING[v]
            return mapped_voice

        # If it contains known keywords, try to map based on keywords
        for keyword, mapped_voice in cls.VOICE_MAPPING.items():
            if keyword in v:
                return mapped_voice

        # Default fallback to nova for any unrecognized voice
        return "nova"


class ChunkData(BaseModel):
    """Individual chunk of text with voice configuration."""

    text: str
    voice: TTSVoice
    character_name: Optional[str] = None


class ChunkTonePayload(BaseModel):
    """Complete payload from ChunkToneService containing all chunks."""

    chunks: List[ChunkData]

    @field_validator("chunks")
    @classmethod
    def validate_chunks_not_empty(cls, v: List[ChunkData]) -> List[ChunkData]:
        """Ensure at least one chunk is present."""
        if not v:
            raise ValueError("Chunks list cannot be empty")
        return v
