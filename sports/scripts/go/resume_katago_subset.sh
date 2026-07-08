#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/go/resume_katago_subset.sh <subset-dir> [chunk-size] [wait-seconds] [all|one]

Examples:
  bash scripts/go/resume_katago_subset.sh raw_data/go/katago/traininggames
  bash scripts/go/resume_katago_subset.sh raw_data/go/katago/traininggames 20 5
  bash scripts/go/resume_katago_subset.sh raw_data/go/katago/traininggames 10 8 all
  bash scripts/go/resume_katago_subset.sh raw_data/go/katago/traininggames 10 8 one
EOF
}

if [[ $# -lt 1 || $# -gt 4 ]]; then
  usage
  exit 1
fi

subset_dir="$1"
chunk_size="${2:-20}"
wait_seconds="${3:-5}"
mode="${4:-all}"
links_path="${subset_dir}/download_links.txt"
retry_path="${subset_dir}/retry_links.txt"
chunks_prefix="${subset_dir}/chunk_"
user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"

if [[ ! -f "$links_path" ]]; then
  echo "download_links.txt not found: $links_path" >&2
  exit 1
fi

if [[ "$mode" != "all" && "$mode" != "one" ]]; then
  echo "mode must be all or one: $mode" >&2
  exit 1
fi

python3 - "$links_path" "$subset_dir" "$retry_path" <<'PY'
from pathlib import Path
from urllib.parse import urlparse
import sys

links_path = Path(sys.argv[1])
subset_dir = Path(sys.argv[2])
retry_path = Path(sys.argv[3])
urls = [line.strip() for line in links_path.read_text(encoding='utf-8').splitlines() if line.strip()]
todo = []
for url in urls:
    name = Path(urlparse(url).path).name
    target = subset_dir / name
    if not target.exists() or target.stat().st_size == 0:
        todo.append(url)
retry_path.write_text("\n".join(todo) + ("\n" if todo else ""), encoding='utf-8')
print(f"total_urls={len(urls)}")
print(f"retry_urls={len(todo)}")
print(f"retry_list={retry_path}")
PY

if [[ ! -s "$retry_path" ]]; then
  echo "[done] nothing left to download in $subset_dir"
  exit 0
fi

rm -f ${chunks_prefix}*
split -l "$chunk_size" "$retry_path" "$chunks_prefix"

mapfile -t chunks < <(ls ${chunks_prefix}* | sort)
if [[ ${#chunks[@]} -eq 0 ]]; then
  echo "[done] no chunks created for $subset_dir"
  exit 0
fi

if [[ "$mode" == "one" ]]; then
  chunks=("${chunks[0]}")
fi

for chunk in "${chunks[@]}"; do
  echo "[info] downloading chunk: $chunk"
  while read -r url; do
    wget \
      --continue \
      --timestamping \
      --tries=2 \
      --wait="$wait_seconds" \
      --random-wait \
      --timeout=30 \
      --read-timeout=30 \
      --user-agent="$user_agent" \
      --directory-prefix "$subset_dir" \
      "$url" || { echo "[stop] failed at $url"; exit 2; }
    sleep "$wait_seconds"
  done < "$chunk"
  echo "[done] completed chunk: $chunk"
done

echo "[done] completed mode=$mode for $subset_dir"
