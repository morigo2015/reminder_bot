#!/bin/bash

# Delete unused/obsolete files and print actions

echo "🧹 Cleaning up unused files..."

FILES_TO_DELETE=(
  "config/dialogs.yaml"
  "config/__init__.py"
  "services/config.py"
  "services/scheduler.py"
  "services/escalation.py"
  "dialogues/__init__.py"
  "dialogues/med.py"
  "dialogues/pressure.py"
  "dialogues/status.py"
  "events.py"
  "models.py"
  "handlers/common.py"
  "handlers/__init__.py"
  "main.py"
  "utils/__init__.py"
  "utils/logging.py"
  "utils/time.py"
)

for file in "${FILES_TO_DELETE[@]}"; do
  if [ -f "$file" ]; then
    rm "$file"
    echo "✅ Deleted: $file"
  else
    echo "⚠️ Skipped (not found): $file"
  fi
done

echo "🧼 Cleanup complete."
