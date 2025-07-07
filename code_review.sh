#!/usr/bin/env bash
set -euo pipefail

# Configuration constants
MIKE_MODEL="gemini-2.5-pro"
JOE_MODEL="o3"
MARKDOWN_ROOT="./"
CODE_ROOT="./"
INCLUDE_TESTS=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --include-tests)
      INCLUDE_TESTS=true
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [--include-tests] [--help]"
      echo "  --include-tests  Include test files in the code review"
      echo "  --help          Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

EXTRA_MESSAGE="
Keep in mind, that as of now this is a single-instance app that runs in my basement
for personal use. I'll probably extend it to some family and friends, and eventually
a limited set of customers, but this is never gonna be a huge platform. It's my hobby,.

For today's review please focus on checking for bugs and inconsistencies.

The latest docs for the TTS API are here: openai-tts-docs.md
$(if [ "$INCLUDE_TESTS" = true ]; then echo "NOTE: Test files are included in this review."; fi)
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
echo "Configuration:"
echo "  Include tests: $INCLUDE_TESTS"
echo "  Mike model: $MIKE_MODEL"
echo "  Joe model: $JOE_MODEL"
echo ""

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
    -not -name '*_review.md' \
    -not -path '*/venv/*' \
    -not -path '*/.venv/*' \
    -not -path '*/env/*' \
    -not -path '*/.env/*' \
    -not -path '*/.git/*' \
    -not -path '*/node_modules/*' \
    -not -path '*/__pycache__/*' \
    -not -path '*/build/*' \
    -not -path '*/dist/*' \
    -not -path '*/logs/*' \
    -not -path '*/media/*' \
    -not -path '*/articles/*' \
    -not -path '*/mypy_stubs/*' \
    -not -path '*/data/*' \
    -exec sh -c '
    echo "# Contents of $1"
    echo "<$1>"
    cat "$1"
    echo "</$1>"
  ' _ {} \;

  # Then output all Python files (excluding venv, .git, and other common directories)
  # Build the find command dynamically based on INCLUDE_TESTS flag
  FIND_CMD="find \"$CODE_ROOT\" -name '*.py' \
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
    -not -path '.devcontainer/*' \
    -not -path '*/logs/*' \
    -not -path '*/media/*' \
    -not -path '*/articles/*' \
    -not -path '*/mypy_stubs/*' \
    -not -path '*/data/*'"

  # Add test exclusions if INCLUDE_TESTS is false
  if [ "$INCLUDE_TESTS" = false ]; then
    FIND_CMD="$FIND_CMD \
    -not -path '*/tests/*' \
    -not -name 'test_*.py' \
    -not -name '*_test.py'"
  fi

  # Add the exec part
  FIND_CMD="$FIND_CMD \
    -exec sh -c '
    echo \"# Contents of \$1\"
    echo \"<\$1>\"
    cat \"\$1\"
    echo \"</\$1>\"
  ' _ {} \\;"

  # Execute the command
  eval "$FIND_CMD"
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
