"""Tests for text_to_audio.audio_utils module.

This module tests the shared WAV utility functions used by TTS providers.
"""

import io
import wave
from unittest import TestCase

from text_to_audio.audio_utils import is_valid_wav, wrap_pcm_in_wav


class WrapPcmInWavTest(TestCase):
    """Test the wrap_pcm_in_wav function."""

    def test_wrap_pcm_creates_valid_wav(self):
        """Test that wrap_pcm_in_wav creates valid WAV with RIFF header."""
        # Create some fake PCM data (16-bit samples)
        pcm_data = b"\x00\x01\x02\x03" * 100

        wav_bytes = wrap_pcm_in_wav(pcm_data)

        # Verify RIFF header
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        # Verify WAVE format marker at byte 8
        self.assertEqual(wav_bytes[8:12], b"WAVE")

    def test_wrap_pcm_with_custom_sample_rate(self):
        """Test WAV wrapping with custom sample rate."""
        pcm_data = b"\x00\x00" * 48000  # 1 second at 48kHz

        wav_bytes = wrap_pcm_in_wav(pcm_data, sample_rate=48000)

        # Parse the WAV to verify sample rate
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            self.assertEqual(wav_file.getframerate(), 48000)

    def test_wrap_pcm_default_sample_rate(self):
        """Test WAV wrapping uses 24000 Hz sample rate by default (Google TTS)."""
        pcm_data = b"\x00\x00" * 24000  # 1 second at 24kHz

        wav_bytes = wrap_pcm_in_wav(pcm_data)

        # Parse the WAV to verify default sample rate
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            self.assertEqual(wav_file.getframerate(), 24000)
            self.assertEqual(wav_file.getnchannels(), 1)  # Mono
            self.assertEqual(wav_file.getsampwidth(), 2)  # 16-bit

    def test_wrap_pcm_handles_empty_data(self):
        """Test wrap_pcm_in_wav handles empty PCM data gracefully."""
        # Should not raise an exception, but return a valid (empty) WAV
        wav_bytes = wrap_pcm_in_wav(b"")

        # Should still have valid WAV header
        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertEqual(wav_bytes[8:12], b"WAVE")

    def test_wrap_pcm_handles_tiny_data(self):
        """Test wrap_pcm_in_wav handles very small PCM data."""
        # Single sample (2 bytes for 16-bit audio)
        tiny_data = b"\x00\x00"
        wav_bytes = wrap_pcm_in_wav(tiny_data)

        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertEqual(wav_bytes[8:12], b"WAVE")


class IsValidWavTest(TestCase):
    """Test the is_valid_wav function."""

    def test_is_valid_wav_returns_true_for_wav(self):
        """Test is_valid_wav returns True for valid WAV data."""
        wav_data = b"RIFF\x00\x00\x00\x00WAVEfmt data"

        self.assertTrue(is_valid_wav(wav_data))

    def test_is_valid_wav_returns_false_for_raw_pcm(self):
        """Test is_valid_wav returns False for raw PCM data."""
        pcm_data = b"\x00\x00\x01\x00\x02\x00"

        self.assertFalse(is_valid_wav(pcm_data))

    def test_is_valid_wav_returns_false_for_empty_data(self):
        """Test is_valid_wav returns False for empty or short data."""
        self.assertFalse(is_valid_wav(b""))
        self.assertFalse(is_valid_wav(b"RI"))  # Too short
        self.assertFalse(is_valid_wav(b"RIF"))  # Too short

    def test_is_valid_wav_returns_false_for_non_wav_riff(self):
        """Test is_valid_wav returns False for non-WAV RIFF containers (AVI, WebP)."""
        # AVI file header (RIFF but not WAVE)
        avi_data = b"RIFF\x00\x00\x00\x00AVI LIST"
        self.assertFalse(is_valid_wav(avi_data))

        # WebP file header (RIFF but not WAVE)
        webp_data = b"RIFF\x00\x00\x00\x00WEBPVP8 "
        self.assertFalse(is_valid_wav(webp_data))

    def test_is_valid_wav_returns_false_for_short_riff_header(self):
        """Test is_valid_wav returns False when RIFF header is too short for WAVE check."""
        # Has RIFF but not enough bytes to check WAVE marker
        short_riff = b"RIFF\x00\x00\x00\x00WAV"  # 11 bytes, missing last byte of WAVE
        self.assertFalse(is_valid_wav(short_riff))
