#!/usr/bin/env bash
set -euo pipefail

# Configuration constants
MIKE_MODEL="gemini-2.5-pro-preview-05-06"
JOE_MODEL="o3"
MARKDOWN_ROOT="./"
CODE_ROOT="./"
EXTRA_MESSAGE="Pay special attention to see if automatic voice tones are properly generating and being sent to the TTS API"

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
