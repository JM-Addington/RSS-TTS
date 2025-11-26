"""Integration tests for multivoice TTS pipeline.

These tests use actual API calls to test the complete multivoice pipeline:
1. Content analysis (GPT) to identify voices and segments
2. TTS generation for each segment with different voices
3. Audio stitching

Uses public domain text from Project Gutenberg.

Run with: pytest tests/text_to_audio/test_multivoice_integration.py -v -s
"""

import os
import tempfile
import unittest
from pathlib import Path

from django.test import TestCase

# Skip all tests if no API keys configured
SKIP_OPENAI = not os.getenv("OPENAI_API_KEY")
SKIP_GOOGLE = not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_TTS_API_KEY"))

# Project Gutenberg excerpt - Sherlock Holmes dialogue (public domain)
SHERLOCK_HOLMES_TEXT = """
"To Sherlock Holmes she is always the woman. I have seldom heard him mention her
under any other name. In his eyes she eclipses and predominates the whole of her sex."

Holmes looked up from his chemical experiments. "Watson, you have come at an opportune moment."

"What is it, Holmes?" I asked, setting down my hat.

"A most singular case," he replied, his keen eyes gleaming. "I received this letter
this morning from the King of Bohemia himself. He is in desperate need of our assistance."

I took the letter from his outstretched hand. "Good heavens, Holmes! This is extraordinary!"

"Indeed it is, my dear Watson. The King fears that a certain photograph, if made public,
would cause a scandal of the most serious nature. The woman who possesses it is none other
than Irene Adler, the well-known adventuress."

"What do you propose to do?" I inquired.

Holmes smiled that thin-lipped smile of his. "I have already set several plans in motion.
Tonight, Watson, we shall pay a visit to Briony Lodge, where Miss Adler resides.
I shall need your assistance."

"You can count on me, Holmes," I said firmly.

"Excellent!" he exclaimed. "Now then, let us review the facts of this most intriguing affair."
"""

# Pride and Prejudice excerpt - dialogue between Elizabeth and Darcy (public domain)
PRIDE_AND_PREJUDICE_TEXT = """
"In vain have I struggled. It will not do. My feelings will not be repressed.
You must allow me to tell you how ardently I admire and love you."

Elizabeth's astonishment was beyond expression. She stared, coloured, doubted,
and was silent. This he considered sufficient encouragement.

"In declaring myself thus I am aware that I shall be going expressly against the
wishes of my family, my friends, and, I hardly need add, my own better judgment.
The relative situation of our families makes any alliance between us a degradation."

"I am all astonishment," said Elizabeth coldly.

Mr. Darcy continued: "Almost from the earliest moments of our acquaintance, I have
come to feel for you a passionate admiration and regard, which despite all my endeavours,
I find myself wholly unable to overcome."

"If I could feel gratitude, I would now thank you," replied Elizabeth with barely
concealed contempt. "But I cannot. I have never desired your good opinion, and you
have certainly bestowed it most unwillingly."

Darcy's complexion became pale with anger. "And this is all the reply I am to have
the honour of expecting! I might perhaps wish to be informed why, with so little
endeavour at civility, I am thus rejected."

"I might as well enquire," retorted Elizabeth, "why with so evident a design of
offending and insulting me, you chose to tell me that you liked me against your will,
against your reason, and even against your character?"
"""

# Shorter excerpt for faster tests
SHORT_DIALOGUE_TEXT = """
"Good morning, Doctor Watson," said Holmes, looking up from his newspaper.

"Holmes! I didn't expect to find you awake at this hour," I replied with surprise.

"The game is afoot, Watson! I have not slept these three days," he announced dramatically.
"A most curious case has presented itself."

"What manner of case?" I inquired, taking my usual chair.

Holmes leaned forward, his eyes alight with interest. "Murder, my dear Watson.
A locked room, an impossible crime, and a client who insists the culprit was a ghost!"
"""


@unittest.skipIf(SKIP_OPENAI, "OpenAI API key not configured")
class OpenAIMultivoiceIntegrationTest(TestCase):
    """Integration tests for OpenAI multivoice pipeline."""

    def test_content_analysis_identifies_voices(self):
        """Test that ContentAnalysisService identifies distinct voices."""
        from text_to_audio.services.content_analysis import ContentAnalysisService

        service = ContentAnalysisService()

        result = service.analyze_content(
            text=SHORT_DIALOGUE_TEXT,
            title="A Sherlock Holmes Adventure",
            tts_provider="openai",
        )

        # Should return valid multivoice structure
        self.assertIn("voices", result)
        self.assertIn("audio_segments", result)

        # Should identify at least 2 voices (narrator + characters)
        self.assertGreaterEqual(len(result["voices"]), 2)

        # Each voice should have required fields
        for voice in result["voices"]:
            self.assertIn("name", voice)
            self.assertIn("tts_model", voice)
            self.assertIn("tts_speed", voice)

        # Each segment should reference a valid voice
        voice_names = {v["name"] for v in result["voices"]}
        for segment in result["audio_segments"]:
            self.assertIn("text", segment)
            self.assertIn("voice_name", segment)
            self.assertIn(segment["voice_name"], voice_names)

        print("\n=== OpenAI Content Analysis Result ===")
        print(f"Identified {len(result['voices'])} voices:")
        for v in result["voices"]:
            print(
                f"  - {v['name']}: {v.get('tts_model', 'N/A')} @ {v.get('tts_speed', 1.0)}x"
            )
        print(f"Split into {len(result['audio_segments'])} segments")

    def test_multivoice_tts_generation(self):
        """Test generating audio for multivoice segments with OpenAI."""
        from text_to_audio.services.content_analysis import ContentAnalysisService
        from text_to_audio.services.tts_service import TTSService

        # First, analyze content
        analysis_service = ContentAnalysisService()
        multivoice_data = analysis_service.analyze_content(
            text=SHORT_DIALOGUE_TEXT,
            title="Holmes Test",
            tts_provider="openai",
        )

        # Build voice lookup
        voice_lookup = {v["name"]: v for v in multivoice_data["voices"]}

        # Generate audio for first 3 segments (to save API costs)
        tts_service = TTSService(provider="openai")
        segments_to_test = multivoice_data["audio_segments"][:3]

        audio_results = []
        for i, segment in enumerate(segments_to_test):
            voice_config = voice_lookup[segment["voice_name"]]
            voice_id = voice_config.get("tts_model", "alloy")
            speed = voice_config.get("tts_speed", 1.0)

            audio_bytes = tts_service.generate_speech(
                text=segment["text"],
                voice=voice_id,
                speed=speed,
                response_format="mp3",
            )

            self.assertIsInstance(audio_bytes, bytes)
            self.assertGreater(len(audio_bytes), 1000)
            audio_results.append((segment["voice_name"], len(audio_bytes)))

        print("\n=== OpenAI Multivoice TTS Results ===")
        for voice_name, size in audio_results:
            print(f"  - {voice_name}: {size} bytes")

    def test_full_multivoice_pipeline_with_stitching(self):
        """Test complete multivoice pipeline including audio stitching."""
        from pydub import AudioSegment

        from text_to_audio.services.content_analysis import ContentAnalysisService
        from text_to_audio.services.tts_service import TTSService

        # Analyze content
        analysis_service = ContentAnalysisService()
        multivoice_data = analysis_service.analyze_content(
            text=SHORT_DIALOGUE_TEXT,
            title="Holmes Full Pipeline",
            tts_provider="openai",
        )

        # Build voice lookup
        voice_lookup = {v["name"]: v for v in multivoice_data["voices"]}

        # Generate all audio segments
        tts_service = TTSService(provider="openai")
        audio_segments = []

        with tempfile.TemporaryDirectory() as tmpdir:
            for i, segment in enumerate(multivoice_data["audio_segments"]):
                voice_config = voice_lookup[segment["voice_name"]]
                voice_id = voice_config.get("tts_model", "alloy")
                speed = voice_config.get("tts_speed", 1.0)

                audio_bytes = tts_service.generate_speech(
                    text=segment["text"],
                    voice=voice_id,
                    speed=speed,
                    response_format="mp3",
                )

                # Save to temp file
                temp_path = Path(tmpdir) / f"segment_{i}.mp3"
                with open(temp_path, "wb") as f:
                    f.write(audio_bytes)

                # Load with pydub
                audio_segment = AudioSegment.from_mp3(temp_path)
                audio_segments.append(audio_segment)

            # Stitch together
            combined = AudioSegment.empty()
            silence = AudioSegment.silent(duration=300)  # 300ms pause

            for i, seg in enumerate(audio_segments):
                combined += seg
                if i < len(audio_segments) - 1:
                    combined += silence

            # Export final audio
            output_path = Path(tmpdir) / "combined_openai.mp3"
            combined.export(output_path, format="mp3")

            # Verify output
            self.assertTrue(output_path.exists())
            file_size = output_path.stat().st_size
            self.assertGreater(file_size, 10000)  # Should be substantial

            duration_seconds = len(combined) / 1000
            print("\n=== OpenAI Full Pipeline Result ===")
            print(f"Generated {len(audio_segments)} segments")
            print(f"Combined duration: {duration_seconds:.1f} seconds")
            print(f"Output file size: {file_size} bytes")


@unittest.skipIf(SKIP_GOOGLE, "Google/Gemini API key not configured")
class GoogleMultivoiceIntegrationTest(TestCase):
    """Integration tests for Google TTS multivoice pipeline."""

    def test_content_analysis_for_google_voices(self):
        """Test that ContentAnalysisService selects Google/Gemini voices."""
        from text_to_audio.services.content_analysis import ContentAnalysisService

        service = ContentAnalysisService()

        result = service.analyze_content(
            text=SHORT_DIALOGUE_TEXT,
            title="A Sherlock Holmes Adventure",
            tts_provider="google",
        )

        # Should return valid multivoice structure
        self.assertIn("voices", result)
        self.assertIn("audio_segments", result)

        # Should identify at least 2 voices
        self.assertGreaterEqual(len(result["voices"]), 2)

        # Voices should be Gemini voice names (short names like "Kore", "Charon")
        gemini_voices = {
            "Achernar",
            "Aoede",
            "Autonoe",
            "Callirrhoe",
            "Despina",
            "Erinome",
            "Gacrux",
            "Kore",
            "Laomedeia",
            "Leda",
            "Pulcherrima",
            "Sulafat",
            "Vindemiatrix",
            "Zephyr",
            "Achird",
            "Algenib",
            "Algieba",
            "Alnilam",
            "Charon",
            "Enceladus",
            "Fenrir",
            "Iapetus",
            "Orus",
            "Puck",
            "Rasalgethi",
            "Sadachbia",
            "Sadaltager",
            "Schedar",
            "Umbriel",
            "Zubenelgenubi",
        }

        for voice in result["voices"]:
            tts_model = voice.get("tts_model", "")
            # Should be a Gemini short name (not en-US-Chirp3-HD-*)
            self.assertIn(
                tts_model,
                gemini_voices,
                f"Voice {tts_model} should be a Gemini short name",
            )

        print("\n=== Google Content Analysis Result ===")
        print(f"Identified {len(result['voices'])} voices:")
        for v in result["voices"]:
            print(f"  - {v['name']}: {v.get('tts_model', 'N/A')}")
        print(f"Split into {len(result['audio_segments'])} segments")

    def test_multivoice_tts_with_gemini_prompts(self):
        """Test generating audio with Gemini TTS using prompt styling."""
        from text_to_audio.services.content_analysis import ContentAnalysisService
        from text_to_audio.services.tts_service import TTSService

        # Analyze content
        analysis_service = ContentAnalysisService()
        multivoice_data = analysis_service.analyze_content(
            text=SHORT_DIALOGUE_TEXT,
            title="Holmes Test",
            tts_provider="google",
        )

        # Build voice lookup
        voice_lookup = {v["name"]: v for v in multivoice_data["voices"]}

        # Generate audio for first 3 segments
        tts_service = TTSService(provider="google")
        segments_to_test = multivoice_data["audio_segments"][:3]

        audio_results = []
        for i, segment in enumerate(segments_to_test):
            voice_config = voice_lookup[segment["voice_name"]]
            voice_id = voice_config.get("tts_model", "Kore")
            tone = voice_config.get("tone", None)

            # Use tone as the styling prompt
            audio_bytes = tts_service.generate_speech(
                text=segment["text"],
                voice=voice_id,
                instructions=tone,  # This becomes the Gemini prompt
                response_format="wav",
            )

            self.assertIsInstance(audio_bytes, bytes)
            self.assertGreater(len(audio_bytes), 1000)
            audio_results.append((segment["voice_name"], voice_id, len(audio_bytes)))

        print("\n=== Google/Gemini Multivoice TTS Results ===")
        for voice_name, voice_id, size in audio_results:
            print(f"  - {voice_name} ({voice_id}): {size} bytes")

    def test_full_multivoice_pipeline_with_google(self):
        """Test complete multivoice pipeline with Google TTS including stitching."""
        from pydub import AudioSegment

        from text_to_audio.services.content_analysis import ContentAnalysisService
        from text_to_audio.services.tts_service import TTSService

        # Analyze content
        analysis_service = ContentAnalysisService()
        multivoice_data = analysis_service.analyze_content(
            text=SHORT_DIALOGUE_TEXT,
            title="Holmes Full Pipeline - Google",
            tts_provider="google",
        )

        # Build voice lookup
        voice_lookup = {v["name"]: v for v in multivoice_data["voices"]}

        # Generate all audio segments
        tts_service = TTSService(provider="google")
        audio_segments = []

        with tempfile.TemporaryDirectory() as tmpdir:
            for i, segment in enumerate(multivoice_data["audio_segments"]):
                voice_config = voice_lookup[segment["voice_name"]]
                voice_id = voice_config.get("tts_model", "Kore")
                tone = voice_config.get("tone", None)

                # Request MP3 format for better compatibility
                audio_bytes = tts_service.generate_speech(
                    text=segment["text"],
                    voice=voice_id,
                    instructions=tone,
                    response_format="mp3",
                )

                # Save to temp file
                temp_path = Path(tmpdir) / f"segment_{i}.mp3"
                with open(temp_path, "wb") as f:
                    f.write(audio_bytes)

                # Load with pydub - Gemini returns PCM audio, convert via raw
                try:
                    audio_segment = AudioSegment.from_mp3(temp_path)
                except Exception:
                    # Gemini returns raw PCM audio, try loading as raw
                    audio_segment = AudioSegment.from_raw(
                        temp_path, sample_width=2, frame_rate=24000, channels=1
                    )
                audio_segments.append(audio_segment)

            # Stitch together
            combined = AudioSegment.empty()
            silence = AudioSegment.silent(duration=300)  # 300ms pause

            for i, seg in enumerate(audio_segments):
                combined += seg
                if i < len(audio_segments) - 1:
                    combined += silence

            # Export final audio
            output_path = Path(tmpdir) / "combined_google.mp3"
            combined.export(output_path, format="mp3")

            # Verify output
            self.assertTrue(output_path.exists())
            file_size = output_path.stat().st_size
            self.assertGreater(file_size, 10000)

            duration_seconds = len(combined) / 1000
            print("\n=== Google Full Pipeline Result ===")
            print(f"Generated {len(audio_segments)} segments")
            print(f"Combined duration: {duration_seconds:.1f} seconds")
            print(f"Output file size: {file_size} bytes")


@unittest.skipIf(SKIP_OPENAI and SKIP_GOOGLE, "No TTS API keys configured")
class LongerTextMultivoiceTest(TestCase):
    """Test multivoice with longer Project Gutenberg excerpts."""

    @unittest.skipIf(SKIP_OPENAI, "OpenAI API key not configured")
    def test_sherlock_holmes_full_dialogue_openai(self):
        """Test multivoice with full Sherlock Holmes dialogue (OpenAI)."""
        from pydub import AudioSegment

        from text_to_audio.services.content_analysis import ContentAnalysisService
        from text_to_audio.services.tts_service import TTSService

        # Analyze the longer text
        analysis_service = ContentAnalysisService()
        multivoice_data = analysis_service.analyze_content(
            text=SHERLOCK_HOLMES_TEXT,
            title="A Scandal in Bohemia - Sherlock Holmes",
            tts_provider="openai",
        )

        voice_lookup = {v["name"]: v for v in multivoice_data["voices"]}
        tts_service = TTSService(provider="openai")

        print("\n=== Sherlock Holmes OpenAI Test ===")
        print(f"Text length: {len(SHERLOCK_HOLMES_TEXT)} chars")
        print(f"Voices identified: {len(multivoice_data['voices'])}")
        for v in multivoice_data["voices"]:
            print(
                f"  - {v['name']}: {v.get('tts_model')} ({v.get('tone', 'N/A')[:50]}...)"
            )
        print(f"Segments: {len(multivoice_data['audio_segments'])}")

        # Generate audio for all segments
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_segments = []
            total_chars = 0

            for i, segment in enumerate(multivoice_data["audio_segments"]):
                voice_config = voice_lookup[segment["voice_name"]]
                voice_id = voice_config.get("tts_model", "alloy")
                speed = voice_config.get("tts_speed", 1.0)

                audio_bytes = tts_service.generate_speech(
                    text=segment["text"],
                    voice=voice_id,
                    speed=speed,
                    response_format="mp3",
                )

                temp_path = Path(tmpdir) / f"segment_{i}.mp3"
                with open(temp_path, "wb") as f:
                    f.write(audio_bytes)

                audio_segment = AudioSegment.from_mp3(temp_path)
                audio_segments.append(audio_segment)
                total_chars += len(segment["text"])

            # Stitch
            combined = AudioSegment.empty()
            silence = AudioSegment.silent(duration=400)
            for i, seg in enumerate(audio_segments):
                combined += seg
                if i < len(audio_segments) - 1:
                    combined += silence

            output_path = Path(tmpdir) / "sherlock_openai.mp3"
            combined.export(output_path, format="mp3")

            duration_seconds = len(combined) / 1000
            print("\nResult:")
            print(f"  Total characters processed: {total_chars}")
            print(f"  Combined duration: {duration_seconds:.1f} seconds")
            print(f"  File size: {output_path.stat().st_size} bytes")

            self.assertGreater(duration_seconds, 10)  # Should be at least 10 seconds

    @unittest.skipIf(SKIP_GOOGLE, "Google/Gemini API key not configured")
    def test_pride_and_prejudice_dialogue_google(self):
        """Test multivoice with Pride and Prejudice dialogue (Google)."""
        from pydub import AudioSegment

        from text_to_audio.services.content_analysis import ContentAnalysisService
        from text_to_audio.services.tts_service import TTSService

        # Analyze
        analysis_service = ContentAnalysisService()
        multivoice_data = analysis_service.analyze_content(
            text=PRIDE_AND_PREJUDICE_TEXT,
            title="Pride and Prejudice - The Proposal Scene",
            tts_provider="google",
        )

        voice_lookup = {v["name"]: v for v in multivoice_data["voices"]}
        tts_service = TTSService(provider="google")

        print("\n=== Pride and Prejudice Google Test ===")
        print(f"Text length: {len(PRIDE_AND_PREJUDICE_TEXT)} chars")
        print(f"Voices identified: {len(multivoice_data['voices'])}")
        for v in multivoice_data["voices"]:
            print(
                f"  - {v['name']}: {v.get('tts_model')} ({v.get('tone', 'N/A')[:50]}...)"
            )
        print(f"Segments: {len(multivoice_data['audio_segments'])}")

        # Generate audio
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_segments = []
            total_chars = 0

            for i, segment in enumerate(multivoice_data["audio_segments"]):
                voice_config = voice_lookup[segment["voice_name"]]
                voice_id = voice_config.get("tts_model", "Kore")
                tone = voice_config.get("tone", None)

                # Request MP3 for better compatibility
                audio_bytes = tts_service.generate_speech(
                    text=segment["text"],
                    voice=voice_id,
                    instructions=tone,
                    response_format="mp3",
                )

                temp_path = Path(tmpdir) / f"segment_{i}.mp3"
                with open(temp_path, "wb") as f:
                    f.write(audio_bytes)

                # Try MP3 first, fallback to raw PCM
                try:
                    audio_segment = AudioSegment.from_mp3(temp_path)
                except Exception:
                    audio_segment = AudioSegment.from_raw(
                        temp_path, sample_width=2, frame_rate=24000, channels=1
                    )
                audio_segments.append(audio_segment)
                total_chars += len(segment["text"])

            # Stitch
            combined = AudioSegment.empty()
            silence = AudioSegment.silent(duration=400)
            for i, seg in enumerate(audio_segments):
                combined += seg
                if i < len(audio_segments) - 1:
                    combined += silence

            output_path = Path(tmpdir) / "pride_prejudice_google.mp3"
            combined.export(output_path, format="mp3")

            duration_seconds = len(combined) / 1000
            print("\nResult:")
            print(f"  Total characters processed: {total_chars}")
            print(f"  Combined duration: {duration_seconds:.1f} seconds")
            print(f"  File size: {output_path.stat().st_size} bytes")

            self.assertGreater(duration_seconds, 10)


@unittest.skipIf(SKIP_OPENAI or SKIP_GOOGLE, "Need both OpenAI and Google API keys")
class CrossProviderComparisonTest(TestCase):
    """Compare multivoice output between OpenAI and Google providers."""

    def test_same_text_different_providers(self):
        """Test same text processed by both OpenAI and Google TTS."""
        from pydub import AudioSegment

        from text_to_audio.services.content_analysis import ContentAnalysisService
        from text_to_audio.services.tts_service import TTSService

        results = {}

        for provider in ["openai", "google"]:
            analysis_service = ContentAnalysisService()
            multivoice_data = analysis_service.analyze_content(
                text=SHORT_DIALOGUE_TEXT,
                title="Holmes Comparison Test",
                tts_provider=provider,
            )

            voice_lookup = {v["name"]: v for v in multivoice_data["voices"]}
            tts_service = TTSService(provider=provider)

            with tempfile.TemporaryDirectory() as tmpdir:
                audio_segments = []

                for i, segment in enumerate(multivoice_data["audio_segments"]):
                    voice_config = voice_lookup[segment["voice_name"]]

                    if provider == "openai":
                        voice_id = voice_config.get("tts_model", "alloy")
                        audio_bytes = tts_service.generate_speech(
                            text=segment["text"],
                            voice=voice_id,
                            speed=voice_config.get("tts_speed", 1.0),
                            response_format="mp3",
                        )
                        fmt = "mp3"
                    else:
                        voice_id = voice_config.get("tts_model", "Kore")
                        audio_bytes = tts_service.generate_speech(
                            text=segment["text"],
                            voice=voice_id,
                            instructions=voice_config.get("tone"),
                            response_format="mp3",
                        )
                        fmt = "mp3"

                    temp_path = Path(tmpdir) / f"segment_{i}.{fmt}"
                    with open(temp_path, "wb") as f:
                        f.write(audio_bytes)

                    # Try MP3 format first, fallback to raw PCM for Gemini
                    try:
                        audio_segment = AudioSegment.from_mp3(temp_path)
                    except Exception:
                        audio_segment = AudioSegment.from_raw(
                            temp_path, sample_width=2, frame_rate=24000, channels=1
                        )
                    audio_segments.append(audio_segment)

                # Stitch
                combined = AudioSegment.empty()
                silence = AudioSegment.silent(duration=300)
                for i, seg in enumerate(audio_segments):
                    combined += seg
                    if i < len(audio_segments) - 1:
                        combined += silence

                results[provider] = {
                    "voices": len(multivoice_data["voices"]),
                    "segments": len(multivoice_data["audio_segments"]),
                    "duration_seconds": len(combined) / 1000,
                }

        print("\n=== Cross-Provider Comparison ===")
        for provider, data in results.items():
            print(f"{provider.upper()}:")
            print(f"  Voices: {data['voices']}")
            print(f"  Segments: {data['segments']}")
            print(f"  Duration: {data['duration_seconds']:.1f}s")

        # Both should produce valid output
        self.assertGreater(results["openai"]["duration_seconds"], 5)
        self.assertGreater(results["google"]["duration_seconds"], 5)
