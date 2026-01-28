"""Audio utility functions for WAV file handling.

This module provides utilities for WAV file validation and PCM audio wrapping.
"""

import io
import logging
import wave

logger = logging.getLogger(__name__)

# AIDEV-NOTE: Minimum WAV header size: RIFF (4) + size (4) + WAVE (4) = 12 bytes
MIN_WAV_HEADER_SIZE = 12


def wrap_pcm_in_wav(
    pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2
) -> bytes:
    """Wrap raw PCM data in a WAV container with proper RIFF header.

    IMPORTANT: The sample_rate parameter MUST match the actual sample rate of the
    PCM data. Using an incorrect sample rate will result in audio playing at the
    wrong speed/pitch. Google/Gemini TTS typically uses 24000 Hz.

    Args:
        pcm_data: Raw PCM audio bytes (LINEAR16 format). Can be empty.
        sample_rate: Sample rate in Hz. Must match the actual PCM data rate.
            Defaults to 24000 Hz (Google/Gemini TTS default).
        channels: Number of audio channels (1 for mono)
        sample_width: Bytes per sample (2 for 16-bit audio)

    Returns:
        WAV file bytes with proper RIFF header

    Raises:
        ValueError: If WAV container creation fails
    """
    # AIDEV-NOTE: LINEAR16 from Google TTS is 24kHz mono 16-bit signed little-endian
    try:
        wav_buffer = io.BytesIO()

        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)

        return wav_buffer.getvalue()
    except (wave.Error, OSError, IOError) as e:
        # Catch wave.Error for WAV-specific issues and OSError/IOError for I/O problems
        raise ValueError(f"Failed to create WAV container: {e}") from e


def is_valid_wav(data: bytes) -> bool:
    """Check if data has a valid WAV/RIFF header.

    A valid WAV file must have:
    - Bytes 0-3: "RIFF" (RIFF container marker)
    - Bytes 8-11: "WAVE" (format identifier)

    This distinguishes WAV files from other RIFF containers like AVI or WebP.

    Args:
        data: Audio bytes to check

    Returns:
        True if data is a valid WAV file (has both RIFF and WAVE markers)
    """
    # AIDEV-NOTE: Must check both RIFF (bytes 0-3) AND WAVE (bytes 8-11) markers
    # to distinguish WAV from other RIFF containers (AVI, WebP, etc.)
    return (
        len(data) >= MIN_WAV_HEADER_SIZE
        and data[:4] == b"RIFF"
        and data[8:12] == b"WAVE"
    )
