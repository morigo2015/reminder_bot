#!/bin/bash

# === concat_sources.sh ===
# Recursively concatenates all matching source files into one output file.
#
# Features:
# - Excluded folders are hardcoded and apply at ANY depth.
# - Included file extensions are hardcoded but easy to change.
# - Output file name is REQUIRED as the only argument.
#
# 📘 Usage:
#   ./concat_sources.sh result.txt

# === Hardcoded excluded folders (space-separated array) ===
exclude_folders=("tests" "__pycache__" "logs" "venv" ".git" "venv_med" "zz_old_med" "zip-bin")

# === Hardcoded included file extensions (space-separated array, without dots) ===
include_extensions=("py" "yaml")

# === Check arguments ===
if [[ $# -ne 1 ]]; then
  echo "❌ Usage: $0 <output_file>"
  exit 1
fi

output_file="$1"

# === Build find exclusions (match folder names anywhere in tree) ===
exclude_args=()
for folder in "${exclude_folders[@]}"; do
  exclude_args+=(-name "$folder" -type d -prune -o)
done

# === Build inclusion pattern for extensions ===
include_args=()
first=true
for ext in "${include_extensions[@]}"; do
  if $first; then
    include_args=(-name "*.$ext")
    first=false
  else
    include_args+=(-o -name "*.$ext")
  fi
done

# === Remove previous output ===
rm -f "$output_file"

# === Find and concatenate ===
find . "${exclude_args[@]}" \( "${include_args[@]}" \) -type f -print \
| sort \
| while read -r file; do
  echo "### FILE: $file" >> "$output_file"
  cat "$file" >> "$output_file"
  echo -e "\n" >> "$output_file"
done

echo "✅ Done. Output saved to: $output_file"
