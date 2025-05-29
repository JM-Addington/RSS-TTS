#!/usr/bin/env bash
set -euo pipefail

# Configuration constants
MIKE_MODEL="gemini-2.5-pro-preview-05-06"
JOE_MODEL="o3"
MARKDOWN_ROOT="./"
CODE_ROOT="./"
EXTRA_MESSAGE="Pay special attention to see if there are any files (including markdown files) that can be removed."

# Function to emit the project plan and all Python source files
emit_all() {
  echo "<project_plan>"
  cat PROJECT_PLAN.md
  echo "</project_plan>"

  # Output all markdown files first (excluding venv, .git, and other common directories)
  find "$MARKDOWN_ROOT" -name '*.md' -not -name 'PROJECT_PLAN.md' \
    -not -name '*final_report*' \
    -not -path '*/.gitignore' \
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
    -not-path '*/venv/*' \
    -not-path '*/.venv/*' \
    -not-path '*/env/*' \
    -not-path '*/.env/*' \
    -not-path '*/.git/*' \
    -not-path '*/node_modules/*' \
    -not-path '*/__pycache__/*' \
    -not-path '*/build/*' \
    -not-path '*/dist/*' \
    -not-path '*/migrations/*' \
    -exec sh -c '
    echo "# Contents of $1"
    echo "<$1>"
    cat "$1"
    echo "</$1>"
  ' _ {} \;
}

datestring=$(date +%Y-%m-%d-%H-%M)
final_report="$datestring-final_report.txt"

# Initialize the final report file
echo "<final_report>" > "$final_report"

echo "Asking Mike for a code review of the project..."
# 1) Mike's first pass
echo "Mike's first review:" >> "$final_report"
emit_all | \
llm -m "$MIKE_MODEL" -s \
"You are Mike, our senior django engineer. Please perform a review on all of this code, looking for bugs and inconsistencies. $EXTRA_MESSAGE" \
>> "$final_report"

echo "Joe will now review Mike's comments and make his own notes..."
# 2) Joe's pass, incorporating Mike's comments
echo "Joe's reply review:" >> "$final_report"
cat "$final_report" | \
llm -m "$JOE_MODEL" -s \
"You are Joe, a senior django engineer. Mike did a first pass on a code review and now it is your turn. Please perform a review on all of this code, looking for bugs and inconsistencies. $EXTRA_MESSAGE" \
>> "$final_report"

echo "Mike will now review Joe's comments and make his own notes..."
# 3) Mike's final pass
echo "Mike's final review:" >> "$final_report"
cat "$final_report" | \
llm -m "$MIKE_MODEL" -s \
"You are Mike, a senior django engineer. You and Joe have been looking for bugs and inconsistencies in this code. This is your back-and-forth conversation—please make any final notes or replies to Joe." \
>> "$final_report"

echo "Joe will now review Mike's final comments and make his own notes..."
# 4) Joe's last pass
echo "Joe's final review:" >> "$final_report"
cat "$final_report" | \
llm -m "$JOE_MODEL" -s \
"You are Joe, a senior django engineer. Mike did a first pass on a code review and now it is your turn. Please perform a review on all of this code, looking for bugs and inconsistencies." \
>> "$final_report"

# Close the final report
echo "</final_report>" >> "$final_report"
echo "Code review completed. Final report saved to $final_report"
