"""
Pydantic schemas for ChunkToneService LLM responses.
"""

import re
from typing import List, Optional

from pydantic import BaseModel, field_validator


class TTSVoice(BaseModel):
    """Voice configuration for TTS."""

    voice: str

    @field_validator("voice")
    @classmethod
    def validate_voice(cls, v: str) -> str:
        """Validate voice follows expected format."""
        # Pattern: letters, digits, hyphens, underscores
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "Voice must contain only letters, digits, hyphens, and underscores"
            )
        return v


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
