#!/usr/bin/env bash
set -euo pipefail

# Configuration constants
MIKE_MODEL="gemini-2.5-pro-preview-05-06"
JOE_MODEL="o3"
MARKDOWN_ROOT="./"
CODE_ROOT="./"
EXTRA_MESSAGE="
You're reviewing some work to make API calls concurrent, here are the notes from the dev:

This is what you are to focus your review on.

======
  Parallel TTS Processing Implementation Summary

  I have successfully implemented a comprehensive parallel TTS processing system on the parallel-tts-processing branch.
   Here's what was delivered:

  🚀 Key Features

  1. Parallel Processing Architecture
  - 4x speed improvement for multi-chunk articles (configurable)
  - Celery group/chord pattern for orchestrating parallel tasks
  - Intelligent batching for articles with many chunks
  - Graceful fallback to sequential processing

  2. Distributed Rate Limiting
  - Redis-based sliding window rate limiter
  - Two-level limiting (per-second burst + per-minute sustained)
  - Prevents OpenAI API throttling across multiple workers
  - Configurable limits with sensible defaults

  3. Enhanced Worker Configuration
  - Dedicated TTS worker pool (worker_tts)
  - Separate queues for different task types
  - Configurable concurrency per worker type
  - Task routing for optimal resource utilization

  📁 New Files Created

  1. text_to_audio/rate_limiter.py - Redis-based distributed rate limiting
  2. text_to_audio/parallel_tasks.py - Parallel TTS tasks (chunk generation + stitching)
  3. tests/text_to_audio/test_parallel_tts.py - Comprehensive test coverage
  4. PARALLEL_TTS_README.md - Detailed documentation and deployment guide

  ⚙️ Configuration Options

  # Feature flags
  ENABLE_PARALLEL_TTS=true

  # Concurrency control
  CELERY_TTS_CHUNK_CONCURRENCY=4
  CELERY_TTS_WORKER_CONCURRENCY=2

  # Rate limiting
  OPENAI_TTS_RATE_LIMIT_PER_MINUTE=50
  OPENAI_TTS_RATE_LIMIT_PER_SECOND=3

  🏗️ Architecture Changes

  Docker Compose Updates:
  - Split worker into worker_main and worker_tts
  - Dedicated queues: tts_chunks, audio_processing, article_processing, maintenance
  - Environment-based worker scaling

  Celery Configuration:
  - Task routing by queue type
  - Worker optimization settings
  - Prefetch and task lifecycle management

  🔄 Processing Flow

  process_article → ChunkTone Analysis → Parallel Execution
                                      ↓
      generate_tts_for_chunk × N (parallel) → stitch_audio_and_finalize
                                      ↓
                              Final MP3 + Article Completion

  🛡️ Error Handling & Resilience

  - Chunk-level retries with exponential backoff
  - Partial failure tolerance (continues with successful chunks)
  - Rate limit handling with intelligent retry delays
  - Automatic fallback to sequential processing when needed

  📊 Performance Benefits

  - Multi-chunk articles: Up to 4x faster (default concurrency=4)
  - Single chunks: No performance degradation
  - Configurable scaling: Adjust concurrency based on API limits and hardware
  - Resource efficiency: Dedicated workers prevent blocking

  🧪 Testing Coverage

  - Rate limiter tests: Token acquisition, limits, Redis interactions
  - Task tests: Success/failure scenarios, error handling
  - Integration tests: End-to-end parallel processing
  - Audio stitching tests: Multiple chunks, partial failures

  🔧 Deployment Ready

  The implementation is production-ready with:
  - Backward compatibility - existing articles work unchanged
  - Feature flags - can be disabled for rollback
  - Environment configuration - all settings externalized
  - Monitoring hooks - comprehensive logging and metrics

  Next Steps

  The parallel TTS system is ready for:
  1. Testing in your development environment
  2. Gradual rollout using feature flags
  3. Performance tuning based on your API limits and usage patterns
  4. Monitoring to optimize concurrency settings

  The implementation follows the plan exactly as discussed, providing configurable parallel processing with robust rate
   limiting and error handling while maintaining full backward compatibility.

======


<last_sprint_notes>

Excellent! All 10 action items from the parallel TTS code review have been successfully implemented and committed.
  Here's a summary of what was accomplished:

  ✅ Completed All 10 Code Review Action Items

  CRITICAL FIXES (C1-C5):
  - C1: Added ChunkToneService input size validation with token estimation to prevent context window overflow
  - C2: Implemented batch processing to prevent worker deadlocking with process_large_article_batched
  - C3: Fixed audio ordering to preserve chronological sequence even with failed chunks
  - C4: Corrected speed propagation from VoiceParameterGenerationService with proper precedence
  - C5: Added race-safe database updates using select_for_update() throughout

  MINOR IMPROVEMENTS (M1-M5):
  - M1: Renamed OPENAI_ANALYSIS_MODEL to OPENAI_CHUNK_TONE_MODEL for clarity
  - M2: Normalized function call signatures across services
  - M3: Removed dead code (_prepare_tts_request helper function)
  - M4: Added comprehensive Redis memory usage documentation
  - M5: Implemented per-chunk task timeouts (150s soft, 180s hard limits)

  Key Improvements Implemented

  1. Robust Error Handling: ChunkToneService now validates input size and falls back gracefully
  2. Scalable Architecture: Batch processing prevents overwhelming the task queue for large articles
  3. Data Integrity: Race-safe database updates prevent corruption during parallel processing
  4. Performance Monitoring: Comprehensive timeouts and logging for production readiness
  5. Resource Management: Better memory usage documentation and cleanup strategies

  The parallel TTS system is now production-ready with robust error handling, proper resource management, and
  comprehensive documentation. All changes have been committed to the parallel-tts-processing branch and pushed to the
  remote repository.

</last_sprint_notes>

Keep in mind, that as of now this is a single-instance app that runs in my basement
for personal use. I'll probably extend it to some family and friends, and eventually
a limited set of customers, but this is never gonna be a huge platform. It's my hobby,.

Finally, if you find any legacy code point it out. It needs to be removed.

The latest docs for the TTS API are here: openai-tts-docs.md
"

datestring=$(date +%Y-%m-%d-%H-%M)
final_report="$datestring-final_report.md"

# Initialize the final report file with header
{
  echo "# Final Code Review Report - $datestring"
  echo ""
} > "$final_report"

# intialize review files
echo "<mike1_review>" > mike1_review.md
echo "<joe1_review>" > joe1_review.md
echo "<mike2_review>" > mike2_review.md
echo "<joe2_review>" > joe2_review.md

echo "Starting at `date`"

# Function to emit the project plan and all Python source files
emit_all() {
  echo "<project_plan>"
  cat PROJECT_PLAN.md
  echo "</project_plan>"

  # Output all markdown files first (excluding venv, .git, and other common directories)
  find "$MARKDOWN_ROOT" -name '*.md' -not -name 'PROJECT_PLAN.md' \
    -not -name '*final_report*' \
    -not -name 'mike*_review.md' \
    -not -name 'joe*_review.md' \
    -not -path '*/venv/*' \
    -not -path '*/.venv/*' \
    -not -path '*/env/*' \
    -not -path '*/.env/*' \
    -not -path '*/.git/*' \
    -not -path '*/node_modules/*' \
    -not -path '*/__pycache__/*' \
    -not -path '*/build/*' \
    -not -path '*/dist/*' \
    -exec sh -c '
    echo "# Contents of $1"
    echo "<$1>"
    cat "$1"
    echo "</$1>"
  ' _ {} \;

  # Then output all Python files (excluding venv, .git, and other common directories)
  find "$CODE_ROOT" -name '*.py' \
    -not -path '*/venv/*' \
    -not -path '*/.venv/*' \
    -not -path '*/env/*' \
    -not -path '*/.env/*' \
    -not -path '*/.git/*' \
    -not -path '*/node_modules/*' \
    -not -path '*/__pycache__/*' \
    -not -path '*/build/*' \
    -not -path '*/dist/*' \
    -not -path '*/migrations/*' \
    -exec sh -c '
    echo "# Contents of $1"
    echo "<$1>"
    cat "$1"
    echo "</$1>"
  ' _ {} \;
}

echo "Asking Mike for a code review of the project..."
# 1) Mike's first pass
emit_all | llm -m "$MIKE_MODEL" -s \
"You are Mike, our senior django engineer. Please perform a review on all of this code, looking for bugs and inconsistencies. Include a list of prioritized action items. $EXTRA_MESSAGE" \
>> "mike1_review.md"
echo "</mike1_review>" >> mike1_review.md

echo "Joe will now review Mike's comments and make his own notes..."
# 2) Joe's pass, incorporating Mike's comments

(emit_all && cat mike1_review.md) | \
llm -m "$JOE_MODEL" -s \
"You are Joe, a senior django engineer. Mike did a first pass on a code review and now it is your turn. Please perform a review on all of this code, looking for bugs and inconsistencies. Update Mike's list of action items. $EXTRA_MESSAGE" \
>> joe1_review.md
echo "</joe1_review>" >> joe1_review.md

echo "Mike will now review Joe's comments and make his own notes..."
# 3) Mike's final pass
(
  emit_all &&
  cat mike1_review.md joe1_review.md
) | llm -m "$MIKE_MODEL" -s \
"You are Mike, a senior django engineer. You and Joe have been looking for bugs and inconsistencies in this code. This is your back-and-forth conversation—please make any final notes or replies to Joe. Give a final proposed list of action items." \
>> mike2_review.md
echo "</mike2_review>" >> mike2_review.md

echo "Joe will now review Mike's final comments and make his own notes..."
# 4) Joe's last pass
(emit_all && cat mike1_review.md joe1_review.md mike2_review.md) | \
llm -m "$JOE_MODEL" -s \
"You are Joe, a senior django engineer. Mike did a first pass on a code review and now it is your turn. Please perform a review on all of this code, looking for bugs and inconsistencies. It is your decision to create the FINAL list of action items for the developers to work on next. Go off of the entire discussion." \
>> joe2_review.md
echo "</joe2_review>" >> joe2_review.md

# Append all reviews to the final report
echo "Appending all reviews to the final report..."
{
  echo "## Mike's First Review"
  cat mike1_review.md
  echo "## Joe's First Review"
  cat joe1_review.md
  echo "## Mike's Final Review"
  cat mike2_review.md
  echo "## Joe's Final Review"
  cat joe2_review.md
} >> "$final_report"

echo "Ended at `date`"
