Text to speech
==============

Learn how to turn text into lifelike spoken audio.

The Audio API provides a [`speech`](/docs/api-reference/audio/createSpeech) endpoint based on our [GPT-4o mini TTS (text-to-speech) model](/docs/models/gpt-4o-mini-tts). It comes with 11 built-in voices and can be used to:

*   Narrate a written blog post
*   Produce spoken audio in multiple languages
*   Give realtime audio output using streaming

Here's an example of the `alloy` voice:

Our [usage policies](https://openai.com/policies/usage-policies) require you to provide a clear disclosure to end users that the TTS voice they are hearing is AI-generated and not a human voice.

Quickstart
----------

The `speech` endpoint takes three key inputs:

1.  The [model](/docs/api-reference/audio/createSpeech#audio-createspeech-model) you're using
2.  The [text](/docs/api-reference/audio/createSpeech#audio-createspeech-input) to be turned into audio
3.  The [voice](/docs/api-reference/audio/createSpeech#audio-createspeech-voice) that will speak the output

Here's a simple request example:

Generate spoken audio from input text

```javascript
import fs from "fs";
import path from "path";
import OpenAI from "openai";

const openai = new OpenAI();
const speechFile = path.resolve("./speech.mp3");

const mp3 = await openai.audio.speech.create({
  model: "gpt-4o-mini-tts",
  voice: "coral",
  input: "Today is a wonderful day to build something people love!",
  instructions: "Speak in a cheerful and positive tone.",
});

const buffer = Buffer.from(await mp3.arrayBuffer());
await fs.promises.writeFile(speechFile, buffer);
```

```python
from pathlib import Path
from openai import OpenAI

client = OpenAI()
speech_file_path = Path(__file__).parent / "speech.mp3"

with client.audio.speech.with_streaming_response.create(
    model="gpt-4o-mini-tts",
    voice="coral",
    input="Today is a wonderful day to build something people love!",
    instructions="Speak in a cheerful and positive tone.",
) as response:
    response.stream_to_file(speech_file_path)
```

```bash
curl https://api.openai.com/v1/audio/speech \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini-tts",
    "input": "Today is a wonderful day to build something people love!",
    "voice": "coral",
    "instructions": "Speak in a cheerful and positive tone."
  }' \
  --output speech.mp3
```

By default, the endpoint outputs an MP3 of the spoken audio, but you can configure it to output any [supported format](#supported-output-formats).

### Text-to-speech models

For intelligent realtime applications, use the `gpt-4o-mini-tts` model, our newest and most reliable text-to-speech model. You can prompt the model to control aspects of speech, including:

*   Accent
*   Emotional range
*   Intonation
*   Impressions
*   Speed of speech
*   Tone
*   Whispering

Our other text-to-speech models are `tts-1` and `tts-1-hd`. The `tts-1` model provides lower latency, but at a lower quality than the `tts-1-hd` model.

### Voice options

The TTS endpoint provides 11 built‑in voices to control how speech is rendered from text. **Hear and play with these voices in [OpenAI.fm](https://openai.fm), our interactive demo for trying the latest text-to-speech model in the OpenAI API**. Voices are currently optimized for English.

*   `alloy`
*   `ash`
*   `ballad`
*   `coral`
*   `echo`
*   `fable`
*   `nova`
*   `onyx`
*   `sage`
*   `shimmer`

If you're using the [Realtime API](/docs/guides/realtime), note that the set of available voices is slightly different—see the [realtime conversations guide](/docs/guides/realtime-conversations#voice-options) for current realtime voices.

### Streaming realtime audio

The Speech API provides support for realtime audio streaming using [chunk transfer encoding](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Transfer-Encoding). This means the audio can be played before the full file is generated and made accessible.

Stream spoken audio from input text directly to your speakers

```javascript
import OpenAI from "openai";
import { playAudio } from "openai/helpers/audio";

const openai = new OpenAI();

const response = await openai.audio.speech.create({
  model: "gpt-4o-mini-tts",
  voice: "coral",
  input: "Today is a wonderful day to build something people love!",
  instructions: "Speak in a cheerful and positive tone.",
  response_format: "wav",
});

await playAudio(response);
```

```python
import asyncio

from openai import AsyncOpenAI
from openai.helpers import LocalAudioPlayer

openai = AsyncOpenAI()

async def main() -> None:
    async with openai.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="coral",
        input="Today is a wonderful day to build something people love!",
        instructions="Speak in a cheerful and positive tone.",
        response_format="pcm",
    ) as response:
        await LocalAudioPlayer().play(response)

if __name__ == "__main__":
    asyncio.run(main())
```

```bash
curl https://api.openai.com/v1/audio/speech \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini-tts",
    "input": "Today is a wonderful day to build something people love!",
    "voice": "coral",
    "instructions": "Speak in a cheerful and positive tone.",
    "response_format": "wav"
  }' | ffplay -i -
```

For the fastest response times, we recommend using `wav` or `pcm` as the response format.

Supported output formats
------------------------

The default response format is `mp3`, but other formats like `opus` and `wav` are available.

*   **MP3**: The default response format for general use cases.
*   **Opus**: For internet streaming and communication, low latency.
*   **AAC**: For digital audio compression, preferred by YouTube, Android, iOS.
*   **FLAC**: For lossless audio compression, favored by audio enthusiasts for archiving.
*   **WAV**: Uncompressed WAV audio, suitable for low-latency applications to avoid decoding overhead.
*   **PCM**: Similar to WAV but contains the raw samples in 24kHz (16-bit signed, low-endian), without the header.

Supported languages
-------------------

The TTS model generally follows the Whisper model in terms of language support. Whisper [supports the following languages](https://github.com/openai/whisper#available-models-and-languages) and performs well, despite voices being optimized for English:

Afrikaans, Arabic, Armenian, Azerbaijani, Belarusian, Bosnian, Bulgarian, Catalan, Chinese, Croatian, Czech, Danish, Dutch, English, Estonian, Finnish, French, Galician, German, Greek, Hebrew, Hindi, Hungarian, Icelandic, Indonesian, Italian, Japanese, Kannada, Kazakh, Korean, Latvian, Lithuanian, Macedonian, Malay, Marathi, Maori, Nepali, Norwegian, Persian, Polish, Portuguese, Romanian, Russian, Serbian, Slovak, Slovenian, Spanish, Swahili, Swedish, Tagalog, Tamil, Thai, Turkish, Ukrainian, Urdu, Vietnamese, and Welsh.

You can generate spoken audio in these languages by providing input text in the language of your choice.

RSS-TTS Implementation Notes
---------------------------

The RSS-TTS system automatically includes intelligent `instructions` in all TTS API calls to enhance voice narration quality:

- **ChunkTone Service**: Uses content-aware prompts for optimal expression
- **Multi-voice Segments**: Includes tone-specific instructions based on voice definitions
- **Single-voice Fallback**: Applies enhanced prompts when voice parameters are available

This ensures that all generated audio benefits from smart narration functionality without requiring manual configuration.

### Content Analysis Optimization

For feeds using AUTO voice mode, the RSS-TTS system implements an optimization to reduce API costs and ensure data consistency:

- **Single Analysis Execution**: Content analysis is performed exactly once per article during TTS generation
- **Analysis Result Reuse**: Voice parameter generation services reuse existing analysis results instead of making duplicate API calls
- **Cost Reduction**: This eliminates redundant LLM calls that previously occurred when both the main task and voice parameter services analyzed the same content
- **Data Consistency**: Using a single analysis ensures all voice-related decisions are based on the same content interpretation

The system automatically detects when content analysis has already been performed and stored in `article.multi_voice_data`, preventing unnecessary duplicate API calls while maintaining the same functionality and voice quality.

### Long Article Processing (Legacy Multi-voice Mode)

The RSS-TTS system ensures complete processing of articles regardless of length in the legacy multi-voice path:

- **Full Article Coverage**: Articles longer than MAX_ANALYSIS_WORDS (8,000 words) are automatically processed in chunks to ensure no content is lost
- **Chunked Analysis**: Long articles are split into overlapping chunks, each analyzed separately for optimal voice assignment and segmentation
- **Seamless Combination**: Analysis results from all chunks are merged into a unified multi-voice structure with consistent voice definitions across the entire article
- **Audio Ordering**: The final audio maintains correct chronological order by processing chunks sequentially and concatenating the resulting audio segments
- **No Silent Loss**: Unlike previous behavior that silently dropped content beyond the first 8,000 words, the system now processes 100% of the article text
- **ChunkTone Compatibility**: The newer ChunkTone service is unaffected by this change and continues to process articles as before

This enhancement resolves the long-article loss issue in legacy multi-voice processing while maintaining backward compatibility and ensuring all article content is converted to audio.

### Voice Field Single Source of Truth

The RSS-TTS system implements a single source of truth strategy for voice information to prevent data inconsistencies and validation errors:

- **Standard Voices**: OpenAI predefined voices (`alloy`, `nova`, `echo`, etc.) are stored in the `voice` field only
- **Custom Voices**: Non-standard voice IDs are stored in the `voice_id` field only
- **Mutual Exclusivity**: Only one voice field should be set at a time to maintain data consistency
- **Automatic Resolution**: Services automatically determine the appropriate field based on whether the voice is standard or custom
- **Validation Enforcement**: The `Article.clean()` method prevents both fields from being set simultaneously

**Implementation Details:**

- **VoiceParameterGenerationService**: Automatically routes voice values to the correct field based on standard voice detection
- **UserPreferencesService**: Applies the same single source logic when saving article preferences or voice presets
- **Views**: All form processing follows the single source approach for voice field assignment
- **Migration Support**: Data migration ensures existing articles conform to the single source strategy

This approach eliminates the "single source of truth for voice fields" validation errors while maintaining full compatibility with both standard OpenAI voices and future custom voice implementations.

Customization and ownership
---------------------------

### Custom voices

We do not support custom voices or creating a copy of your own voice.

### Who owns the output?

As with all outputs from our API, the person who created them owns the output. You are still required to inform end users that they are hearing audio generated by AI and not a real person talking to them.

Was this page useful?
