# ChunkToneService Documentation

## Overview

The ChunkToneService is a new LLM-driven approach to text chunking and tone analysis that replaces the traditional chunking + autotone pipeline. It uses OpenAI's GPT models to intelligently break text into chunks while simultaneously assigning appropriate voices and character names for multi-voice narration.

## Architecture

The service consists of three main components:

1. **Pydantic Schemas** (`text_to_audio/schemas/chunk_tone.py`)
   - `TTSVoice`: Voice configuration with validation
   - `ChunkData`: Individual text chunk with voice assignment
   - `ChunkTonePayload`: Complete response containing all chunks

2. **ChunkToneService** (`text_to_audio/services/chunk_tone_service.py`)
   - Main service class that handles LLM communication
   - Retry logic for invalid responses
   - Fallback generation for error cases

3. **Integration Layer** (`text_to_audio/tasks.py`)
   - Feature flag-controlled integration
   - Seamless fallback to legacy pipeline

## Feature Flag

The service is controlled by the `ENABLE_CHUNK_TONE_LLM` environment variable:

```bash
# Enable the new service
ENABLE_CHUNK_TONE_LLM=true

# Disable (default) - uses legacy pipeline
ENABLE_CHUNK_TONE_LLM=false
```

## Service Flow

### 1. Input Processing
- Receives article text, title, and max_chars parameter
- Builds a structured prompt for the LLM
- Includes instructions for voice assignment and character naming

### 2. LLM Analysis
- Calls OpenAI API with structured prompt
- Expects JSON response with chunks and voice assignments
- Uses retry logic for invalid responses (up to 2 attempts)

### 3. Response Validation
- Validates JSON structure using Pydantic schemas
- Ensures voice names follow expected format (`^[a-zA-Z0-9_-]+$`)
- Verifies at least one chunk is present

### 4. Fallback Handling
- If both LLM attempts fail, creates fallback payload
- Uses single narrator voice (`alloy`) for entire text
- Ensures processing never completely fails

## Prompt Template

The service uses a structured prompt that includes:

```
You are a text-to-speech specialist. Analyze the following article and break it into logical chunks for multi-voice narration.

Article Title: {title}

Article Text:
{text}

Requirements:
1. Break the text into logical chunks (maximum {max_chars} characters each)
2. Assign appropriate voices and character names for different speakers/narrators
3. Use these available voices: alloy, echo, fable, onyx, nova, shimmer
4. For narrative text, use character_name "narrator"
5. For dialogue or quotes, use appropriate character names

Return ONLY a JSON object with this exact structure:
{
  "chunks": [
    {
      "text": "chunk text here",
      "voice": {"voice": "voice_name"},
      "character_name": "narrator_or_character_name"
    }
  ]
}
```

## Expected Response Format

```json
{
  "chunks": [
    {
      "text": "Once upon a time, there was a brave knight.",
      "voice": {"voice": "alloy"},
      "character_name": "narrator"
    },
    {
      "text": "I shall save the kingdom!",
      "voice": {"voice": "onyx"},
      "character_name": "knight"
    }
  ]
}
```

## Integration with Tasks

When `ENABLE_CHUNK_TONE_LLM=true`, the service integrates into the article processing pipeline:

1. **Text Preparation**: Combines article title and content
2. **Chunk Generation**: Calls ChunkToneService to get structured chunks
3. **TTS Processing**: Processes each chunk with assigned voice
4. **Audio Assembly**: Combines all audio chunks into final file
5. **Fallback**: If ChunkToneService fails, falls back to legacy multi-voice or single-voice processing

## Voice Assignment

The service supports these OpenAI TTS voices:
- `alloy` - Default narrator voice
- `echo` - Character dialogue
- `fable` - Storytelling
- `onyx` - Bold/dramatic characters
- `nova` - Casual/conversational
- `shimmer` - News/formal content

## Error Handling

The service implements multiple layers of error handling:

1. **Validation Retry**: If first LLM response is invalid, retry once
2. **JSON Parsing**: Handles malformed JSON responses
3. **API Errors**: Catches OpenAI API failures
4. **Fallback Generation**: Always produces a valid payload, even on complete failure

## Testing

The service includes comprehensive test coverage:

- Valid JSON response (first attempt)
- Invalid then valid response (retry mechanism)
- Invalid responses twice (fallback)
- OpenAI API errors (fallback)
- Invalid JSON responses (fallback)
- Schema validation tests

Run tests with:
```bash
pytest tests/text_to_audio/test_chunk_tone_service.py -v
```

## Migration Strategy

The implementation allows for gradual rollout:

1. **Development**: Test with `ENABLE_CHUNK_TONE_LLM=true` in dev environment
2. **Staging**: Validate with real content in staging
3. **Production**: Enable feature flag for production deployment
4. **Rollback**: Can instantly revert by setting flag to `false`

## Performance Considerations

- **API Calls**: One additional OpenAI API call per article (chunking/analysis)
- **Token Usage**: Varies based on article length, typically 100-500 tokens
- **Processing Time**: Adds ~1-3 seconds per article for LLM analysis
- **Fallback Performance**: No performance impact when falling back to legacy

## Monitoring

Key metrics to monitor:
- ChunkToneService success rate
- Fallback frequency
- Average chunks per article
- Token usage for chunking calls
- Processing time impact

## Future Enhancements

Potential improvements:
- Voice style parameters (speed, tone adjustments)
- Content-aware voice selection
- Custom voice mapping configurations
- Caching for repeated content patterns
