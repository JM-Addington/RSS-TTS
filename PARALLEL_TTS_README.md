# Parallel TTS Processing Implementation

This document describes the parallel TTS processing implementation that enables multiple TTS chunks to be processed concurrently, significantly improving performance for long articles.

## Overview

The parallel TTS system replaces sequential chunk processing with a distributed task architecture using Celery groups and chords. This allows multiple audio chunks to be generated simultaneously while maintaining proper ordering and error handling.

## Architecture

### Core Components

1. **TTSRateLimiter** (`text_to_audio/rate_limiter.py`)
   - Redis-based distributed rate limiting
   - Two-level rate limiting (per-second and per-minute)
   - Prevents OpenAI API throttling across multiple workers

2. **Parallel Tasks** (`text_to_audio/parallel_tasks.py`)
   - `generate_tts_for_chunk`: Processes individual text chunks
   - `stitch_audio_and_finalize`: Combines chunks and finalizes articles

3. **Enhanced process_article** (`text_to_audio/tasks.py`)
   - Coordinator task that orchestrates parallel processing
   - Falls back to sequential processing when appropriate

### Task Flow

```mermaid
graph TD
    A[process_article] --> B{Parallel Enabled?}
    B -->|Yes| C[Create chunk tasks]
    B -->|No| D[Sequential processing]
    C --> E[group/chord execution]
    E --> F[generate_tts_for_chunk × N]
    F --> G[stitch_audio_and_finalize]
    G --> H[Article completed]
    D --> H
```

## Configuration

### Environment Variables

```bash
# Enable/disable parallel processing
ENABLE_PARALLEL_TTS=true

# Maximum concurrent chunks per article
CELERY_TTS_CHUNK_CONCURRENCY=4

# Rate limiting settings
OPENAI_TTS_RATE_LIMIT_PER_MINUTE=50
OPENAI_TTS_RATE_LIMIT_PER_SECOND=3

# Worker configuration
CELERY_TTS_WORKER_CONCURRENCY=2
```

### Django Settings

The following settings are automatically configured from environment variables:

- `ENABLE_PARALLEL_TTS`: Feature flag for parallel processing
- `CELERY_TTS_CHUNK_CONCURRENCY`: Max concurrent chunks
- `OPENAI_TTS_RATE_LIMIT_PER_MINUTE`: API rate limit per minute
- `OPENAI_TTS_RATE_LIMIT_PER_SECOND`: API rate limit per second
- `CELERY_TTS_WORKER_CONCURRENCY`: TTS worker pool size

## Deployment

### Docker Compose

The system includes dedicated worker pools:

- **worker_main**: Handles article processing, maintenance, and audio finalization
- **worker_tts**: Dedicated pool for TTS chunk generation

```yaml
worker_main:
  command: celery -A rss_tts worker -Q article_processing,maintenance,audio_processing -c 2

worker_tts:
  command: celery -A rss_tts worker -Q tts_chunks -c ${CELERY_TTS_WORKER_CONCURRENCY:-2}
```

### Queue Configuration

Tasks are routed to specific queues:

- `tts_chunks`: TTS chunk generation
- `audio_processing`: Audio stitching and finalization
- `article_processing`: Main article processing
- `maintenance`: Background maintenance tasks

## Rate Limiting

### Implementation

The rate limiter uses Redis sliding window counters to enforce limits:

- **Per-second limiting**: Prevents burst API calls
- **Per-minute limiting**: Enforces sustained rate limits
- **Distributed**: Works across multiple worker instances

### Usage

```python
from text_to_audio.rate_limiter import get_rate_limiter

rate_limiter = get_rate_limiter()
if rate_limiter.acquire_tts_token(timeout=60.0):
    # Make TTS API call
    pass
```

## Error Handling

### Chunk-Level Failures

- Individual chunk failures don't stop processing
- Retries with exponential backoff for transient errors
- Rate limit errors trigger longer delays

### Article-Level Failures

- If majority of chunks fail: Article marked as FAILED
- If minority fail: Article completes with warnings
- All chunks fail: Article marked as FAILED

### Graceful Degradation

- Falls back to sequential processing for single chunks
- Disables parallel processing via `ENABLE_PARALLEL_TTS=false`
- Continues with available chunks if some fail

## Performance Benefits

### Speed Improvements

- **4x faster** for articles with 4+ chunks (with default concurrency=4)
- Scales with `CELERY_TTS_CHUNK_CONCURRENCY` setting
- Maintains sequential performance for short articles

### Resource Usage

- Dedicated TTS worker pool prevents blocking other tasks
- Redis-based rate limiting prevents API quota exhaustion
- Configurable concurrency limits resource consumption

## Monitoring

### Metrics to Track

1. **Task Metrics**
   - TTS chunk success/failure rates
   - Average chunk processing time
   - Queue depth for `tts_chunks` queue

2. **Rate Limiting Metrics**
   - Rate limit hits per minute
   - Token acquisition wait times
   - API quota utilization

3. **Performance Metrics**
   - End-to-end article processing time
   - Parallel vs sequential processing time comparison
   - Worker utilization rates

### Logging

Enhanced logging provides visibility into parallel processing:

```
INFO: Starting parallel TTS processing for 8 chunks
INFO: TTS Chunk 0 API Call - Article 123, model=tts-1, voice=alloy
INFO: TTS chunk 0 completed successfully in 1234ms
INFO: Parallel TTS completed: Article 123 finalized successfully
```

## Testing

### Test Coverage

The implementation includes comprehensive tests:

- `test_parallel_tts.py`: Unit tests for all components
- Rate limiter functionality
- Chunk generation and error handling
- Audio stitching with various failure scenarios
- Integration tests for parallel processing

### Running Tests

```bash
# Run parallel TTS tests
python manage.py test tests.text_to_audio.test_parallel_tts

# Run all tests
python manage.py test
```

## Troubleshooting

### Common Issues

1. **Rate Limiting**
   - Check Redis connectivity
   - Verify `OPENAI_TTS_RATE_LIMIT_*` settings
   - Monitor API usage in OpenAI dashboard

2. **Worker Issues**
   - Ensure `worker_tts` container is running
   - Check worker logs for errors
   - Verify queue routing configuration

3. **Performance Issues**
   - Adjust `CELERY_TTS_CHUNK_CONCURRENCY`
   - Monitor Redis performance
   - Check network latency to OpenAI API

### Debug Mode

To disable parallel processing for debugging:

```bash
export ENABLE_PARALLEL_TTS=false
```

This forces sequential processing while maintaining the same code path.

## Migration Notes

### Backward Compatibility

- Existing articles continue to work unchanged
- No database migrations required
- Can be deployed incrementally

### Rollback

To rollback to sequential processing:

1. Set `ENABLE_PARALLEL_TTS=false`
2. Remove `worker_tts` from docker-compose.yml
3. Revert `worker` to handle all queues

## Future Enhancements

### Planned Improvements

1. **Auto-scaling**: Dynamic worker scaling based on queue depth
2. **Priority queues**: High-priority articles processed first
3. **Batch optimization**: Intelligent batching for optimal performance
4. **Metrics dashboard**: Real-time monitoring and alerting

### Configuration Options

1. **Per-feed concurrency**: Different limits per feed
2. **Time-based limits**: Quieter processing during peak hours
3. **Cost optimization**: Balance speed vs API costs

## Security Considerations

### API Key Protection

- Rate limiting prevents API key abuse
- Redis authentication in production
- Secure inter-service communication

### Resource Limits

- Worker memory limits prevent resource exhaustion
- Queue size limits prevent unbounded growth
- Timeout configurations prevent hanging tasks
