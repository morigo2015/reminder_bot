#!/bin/bash

# === concat_sources.sh ===
# Recursively concatenates all *.py and *.yaml files into one output file.
#
# Features:
# - Exclude specific folders using a single `-x` followed by a list of folder names
# - Optional output file name (default: concat_result.txt)
#
# 📘 Usage:
#   ./concat_sources.sh                         # output to concat_result.txt
#   ./concat_sources.sh result.txt              # custom output
#   ./concat_sources.sh -x venv .git __pycache__   # excludes folders, default output
#   ./concat_sources.sh result.txt -x venv .git    # custom output, excluded folders

# === Defaults ===
output_file="concat_result.txt"
exclude_folders=("__pycache__")

# === Parse arguments ===
output_given=false
exclude_mode=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -x)
      exclude_mode=true
      shift
      ;;
    -*)
      echo "❌ Unknown option: $1"
      exit 1
      ;;
    *)
      if $exclude_mode; then
        exclude_folders+=("$1")
        shift
      elif ! $output_given; then
        output_file="$1"
        output_given=true
        shift
      else
        echo "❌ Unexpected argument: $1"
        exit 1
      fi
      ;;
  esac
done

# === Build find exclusions ===
exclude_args=()
for folder in "${exclude_folders[@]}"; do
  exclude_args+=(-path "./$folder" -prune -o)
done

# === Remove previous output ===
rm -f "$output_file"

# === Find and concatenate ===
find . "${exclude_args[@]}" \( -name "*.py" -o -name "*.yaml" \) -type f -print | sort | while read -r file; do
  echo "### FILE: $file" >> "$output_file"
  cat "$file" >> "$output_file"
  echo -e "\n" >> "$output_file"
done

echo "✅ Done. Output saved to: $output_file"

