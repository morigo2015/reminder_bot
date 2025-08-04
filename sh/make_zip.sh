#!/bin/bash

if [ -z "$1" ]; then
  echo "Usage: $0 <output_zip_name_without_extension>"
  exit 1
fi

# Strip .zip if included
name="${1%.zip}"
output_zip="${name}.zip"

# Define exclusions
exclusions=(
  "__pycache__/*"
  "*/__pycache__/*"
  "__init__.py"
  "*/__init__.py"
  "*.zip"
  "$output_zip"         # prevent including the just-created archive
)

# Create zip archive
zip -r "$output_zip" . -x "${exclusions[@]}"
