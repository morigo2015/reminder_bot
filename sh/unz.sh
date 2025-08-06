#!/usr/bin/env bash
# update.sh — unzip with overwrite and move archive to ./zip-bin
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <archive.zip>"
  exit 1
fi

ZIPFILE="$1"

# Unzip with -o to overwrite existing files silently
unzip -o "$ZIPFILE"

# Ensure the zip-bin directory exists
mkdir -p zip-bin

# Move the processed zip into zip-bin
mv "$ZIPFILE" zip-bin/

echo "✔ Unzipped $ZIPFILE and moved to ./zip-bin/"
