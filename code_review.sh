#!/usr/bin/env bash
set -euo pipefail

# Configuration constants
MIKE_MODEL="gemini-2.5-pro-preview-05-06"
JOE_MODEL="o3"
MARKDOWN_ROOT="./"
CODE_ROOT="./"
EXTRA_MESSAGE="
You're reviewing some work to make API calls concurrent, here are the notes from the dev:

please review issues.md and create a plan to work on the bugs. I think we could get through
all outstanding issues in a single sprint, so please prioritize them and create a plan
for how to tackle them.

this is the dev's comments on the last sprint:
<comments>
● 🎉 MISSION ACCOMPLISHED!

  I have successfully completed all critical (P0) and high-priority (P1) tasks from Mike and Joe's comprehensive code
  review:

  ✅ Critical Bugs Fixed (P0)

  1. Preset Voice Application Pipeline - Fixed VoiceConfigurationService to respect presets and ChunkToneService to use
   preset voice for all chunks
  2. Voice Field Single Source of Truth - Article.clean() now properly enforces voice field consistency
  3. Preset Edit Form Data Clearing - Form now preserves existing values when POST data is empty
  4. Universal TTS Speed Clamping - Speed validation applied before every TTS API call

  ✅ High Priority Issues Fixed (P1)

  5. Model-Aware Speed Control - gpt-4o-mini-tts uses instructions, tts-1 uses speed parameter
  6. Robust Celery Task ID Handling - Prevents dangling task IDs in batched dispatch failures
  7. Documentation Corrections - Fixed misleading performance claims in PARALLEL_TTS_README.md
  8. Repository Hygiene - Verified .pytest_cache/ is properly ignored

  📊 Final Status

  - All modified files compile successfully ✅
  - All pre-commit hooks pass ✅
  - No breaking changes introduced ✅
  - Ready for deployment ✅

  The core preset voice bugs that were causing production issues have been resolved, and the system now has proper
  voice handling, speed control, and robust task management. The remaining P2 tasks are feature enhancements rather
  than critical fixes.

  </comments>

Keep in mind, that as of now this is a single-instance app that runs in my basement
for personal use. I'll probably extend it to some family and friends, and eventually
a limited set of customers, but this is never gonna be a huge platform. It's my hobby,

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
