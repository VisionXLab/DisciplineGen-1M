#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/chess_xiangqi/download_lichess_standard.sh <output-root> [year-from] [year-to]

Examples:
  bash scripts/chess_xiangqi/download_lichess_standard.sh raw_data/chess
  bash scripts/chess_xiangqi/download_lichess_standard.sh raw_data/chess 2023 2025
EOF
}

if [[ $# -lt 1 || $# -gt 3 ]]; then
  usage
  exit 1
fi

output_root="$1"
year_from="${2:-0}"
year_to="${3:-9999}"
base_url="https://database.lichess.org/standard/"
user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
output_dir="${output_root}/lichess_standard"
index_path="${output_dir}/index.html"
links_path="${output_dir}/download_links.txt"

if ! command -v wget >/dev/null 2>&1; then
  echo "wget is required but not found in PATH." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but not found in PATH." >&2
  exit 1
fi

mkdir -p "$output_dir"

echo "[info] Fetching index: ${base_url}"
wget --continue --user-agent="$user_agent" -O "$index_path" "$base_url"

python3 - "$index_path" "$links_path" "$base_url" "$year_from" "$year_to" <<'PY'
import html
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

index_path = Path(sys.argv[1])
links_path = Path(sys.argv[2])
base_url = sys.argv[3]
year_from = int(sys.argv[4])
year_to = int(sys.argv[5])
text = index_path.read_text(encoding="utf-8", errors="replace")
pattern = re.compile(r"href=[\"']([^\"']+\.pgn\.zst)[\"']", re.IGNORECASE)
year_pattern = re.compile(r"(\d{4})-(\d{2})")
seen = set()
urls = []
for href in pattern.findall(text):
    href = html.unescape(href.strip())
    full_url = urljoin(base_url, href)
    name = Path(href).name
    match = year_pattern.search(name)
    if match is None:
        continue
    year = int(match.group(1))
    if year < year_from or year > year_to:
        continue
    if full_url in seen:
        continue
    seen.add(full_url)
    urls.append(full_url)
urls.sort()
links_path.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
print(f"Extracted {len(urls)} archive links to {links_path}")
PY

if [[ ! -s "$links_path" ]]; then
  echo "No Lichess standard archives matched the requested year range ${year_from}-${year_to}." >&2
  exit 1
fi

echo "[info] Downloading archives listed in ${links_path}"
wget \
  --continue \
  --timestamping \
  --user-agent="$user_agent" \
  --directory-prefix "$output_dir" \
  --input-file "$links_path"

echo "[done] Downloaded Lichess standard archives into ${output_dir}"
