#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/chess_xiangqi/download_xqbase_full.sh <output-root> [start-gameid] [stop-empty-run]

Examples:
  bash scripts/chess_xiangqi/download_xqbase_full.sh raw_data/xiangqi
  bash scripts/chess_xiangqi/download_xqbase_full.sh raw_data/xiangqi 1 5000
EOF
}

if [[ $# -lt 1 || $# -gt 3 ]]; then
  usage
  exit 1
fi

output_root="$1"
start_gameid="${2:-1}"
stop_empty_run="${3:-5000}"
urls_path="${output_root}/xqbase_game_urls.txt"
log_path="${output_root}/xqbase_scan_log.tsv"
html_dir="${output_root}/games"

mkdir -p "$output_root"

python3 scripts/chess_xiangqi/scan_xqbase_gameids.py \
  --start-gameid "$start_gameid" \
  --stop-empty-run "$stop_empty_run" \
  --output-urls "$urls_path" \
  --output-log "$log_path" \
  --timeout 40 \
  --retries 4 \
  --prefer-wget \
  --delay 0.5

bash scripts/chess_xiangqi/download_xqbase_pages.sh "$urls_path" "$html_dir"

echo "[done] XQBase full scan artifacts written to ${output_root}"
