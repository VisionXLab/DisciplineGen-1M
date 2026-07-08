#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/go/download_katago_archive.sh <traininggames|ratinggames|trainingdata|all> <output-root>

Examples:
  bash scripts/go/download_katago_archive.sh traininggames raw_data/go/katago
  bash scripts/go/download_katago_archive.sh all raw_data/go/katago
EOF
}

if [[ $# -ne 2 ]]; then
  usage
  exit 1
fi

subset="$1"
output_root="$2"
base_url="https://katagoarchive.org/kata1"
user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"

if ! command -v wget >/dev/null 2>&1; then
  echo "wget is required but not found in PATH." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but not found in PATH." >&2
  exit 1
fi

common_wget_args=(
  --continue
  --timestamping
  --user-agent="$user_agent"
  --tries=5
  --wait=1
  --random-wait
  --timeout=30
  --read-timeout=30
)

download_subset() {
  local name="$1"
  local subset_dir="${output_root}/${name}"
  local index_url="${base_url}/${name}/index.html"
  local index_path="${subset_dir}/index.html"
  local links_path="${subset_dir}/download_links.txt"

  mkdir -p "$subset_dir"

  echo "[info] Fetching index: ${index_url}"
  wget "${common_wget_args[@]}" -O "$index_path" "$index_url"

  python3 - "$index_path" "$links_path" "$base_url" "$name" <<'PY'
import html
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

index_path = Path(sys.argv[1])
links_path = Path(sys.argv[2])
base_url = sys.argv[3]
name = sys.argv[4]
page_url = f"{base_url}/{name}/"
text = index_path.read_text(encoding="utf-8", errors="replace")
pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
allowed_suffixes = (
    ".tar.bz2",
    ".tar.gz",
    ".zip",
    ".7z",
    ".npz",
    ".sgfs",
    ".sgf",
)
seen = set()
urls = []
for href in pattern.findall(text):
    href = html.unescape(href.strip())
    if not href or href.startswith("#"):
        continue
    lower = href.lower()
    if not lower.endswith(allowed_suffixes):
        continue
    full_url = urljoin(page_url, href)
    if full_url not in seen:
        seen.add(full_url)
        urls.append(full_url)
links_path.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
print(f"Extracted {len(urls)} download links to {links_path}")
PY

  if [[ ! -s "$links_path" ]]; then
    echo "No downloadable archive links were found in ${index_url}." >&2
    exit 1
  fi

  echo "[info] Downloading archives listed in ${links_path}"
  wget \
    "${common_wget_args[@]}" \
    --directory-prefix "$subset_dir" \
    --input-file "$links_path"
}

case "$subset" in
  traininggames|ratinggames|trainingdata)
    download_subset "$subset"
    ;;
  all)
    download_subset traininggames
    download_subset ratinggames
    download_subset trainingdata
    ;;
  *)
    usage
    exit 1
    ;;
esac