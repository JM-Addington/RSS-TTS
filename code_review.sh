#!/usr/bin/env bash
set -euo pipefail

# Configuration constants
MIKE_MODEL="gemini-2.5-pro-preview-05-06"
JOE_MODEL="o3"
MARKDOWN_ROOT="./"
CODE_ROOT="./"
EXTRA_MESSAGE="
You're reviewing some work to make API calls concurrent, here are the notes from the dev:

After one of the recent commits the worker stopped picking up on any new tasks.
Why? How do we fix that?

Keep in mind, that as of now this is a single-instance app that runs in my basement
for personal use. I'll probably extend it to some family and friends, and eventually
a limited set of customers, but this is never gonna be a huge platform. It's my hobby,

Finally, if you find any legacy code point it out. It needs to be removed.

The latest docs for the TTS API are here: openai-tts-docs.md

Here is full output from the worker:
<output>
root@a4cc1c804e3d:/app# /app/start-worker.sh celery -A rss_tts worker --loglevel=info
Development mode: checking requirements...
WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager, possibly rendering your system unusable. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv. Use the --root-user-action option if you know what you are doing and want to suppress this warning.

[notice] A new release of pip is available: 25.0.1 -> 25.1.1
[notice] To update, run: pip install --upgrade pip
/usr/local/lib/python3.12/site-packages/celery/platforms.py:841: SecurityWarning: You're running the worker with superuser privileges: this is
absolutely not recommended!

Please specify a different user using the --uid option.

User information: uid=0 euid=0 gid=0 egid=0

  warnings.warn(SecurityWarning(ROOT_DISCOURAGED.format(

 -------------- celery@a4cc1c804e3d v5.5.3 (immunity)
--- ***** -----
-- ******* ---- Linux-6.2.0-39-generic-x86_64-with-glibc2.36 2025-06-04 23:21:56
- *** --- * ---
- ** ---------- [config]
- ** ---------- .> app:         rss_tts:0x7f40b186f710
- ** ---------- .> transport:   redis://redis:6379/0
- ** ---------- .> results:     disabled://
- *** --- * --- .> concurrency: 8 (prefork)
-- ******* ---- .> task events: OFF (enable -E to monitor tasks in this worker)
--- ***** -----
 -------------- [queues]
                .> celery           exchange=celery(direct) key=celery


[tasks]
  . text_to_audio.parallel_tasks.generate_tts_for_chunk
  . text_to_audio.parallel_tasks.process_large_article_batched
  . text_to_audio.parallel_tasks.stitch_audio_and_finalize
  . text_to_audio.tasks.check_stale_articles
  . text_to_audio.tasks.process_article

[2025-06-04 23:21:56,679: INFO/MainProcess] Connected to redis://redis:6379/0
[2025-06-04 23:21:56,682: INFO/MainProcess] mingle: searching for neighbors
[2025-06-04 23:21:57,693: INFO/MainProcess] mingle: all alone
[2025-06-04 23:21:57,718: INFO/MainProcess] celery@a4cc1c804e3d ready.
</output>
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
    -not -path '*/tests/*' \
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
    -not -path '*/tests/*' \
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
