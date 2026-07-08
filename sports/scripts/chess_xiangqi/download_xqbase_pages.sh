#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 urls.txt output_dir"
  exit 1
fi

URLS_FILE="$1"
OUT_DIR="$2"
mkdir -p "$OUT_DIR"

wget \
  --continue \
  --timestamping \
  --tries=5 \
  --wait=1 \
  --random-wait \
  --timeout=30 \
  --read-timeout=30 \
  --user-agent="Mozilla/5.0" \
  -i "$URLS_FILE" \
  -P "$OUT_DIR"
