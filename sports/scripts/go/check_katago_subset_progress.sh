#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/go/check_katago_subset_progress.sh <subset-dir>

Examples:
  bash scripts/go/check_katago_subset_progress.sh raw_data/go/katago/traininggames
  bash scripts/go/check_katago_subset_progress.sh raw_data/go/katago/ratinggames
EOF
}

if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi

subset_dir="$1"
links_path="${subset_dir}/download_links.txt"

if [[ ! -f "$links_path" ]]; then
  echo "download_links.txt not found: $links_path" >&2
  exit 1
fi

python3 - "$links_path" "$subset_dir" <<'PY'
from pathlib import Path
from urllib.parse import urlparse
import sys

links_path = Path(sys.argv[1])
subset_dir = Path(sys.argv[2])
urls = [line.strip() for line in links_path.read_text(encoding='utf-8').splitlines() if line.strip()]
missing = []
present = []
for url in urls:
    name = Path(urlparse(url).path).name
    target = subset_dir / name
    if target.exists() and target.stat().st_size > 0:
        present.append((name, target.stat().st_size))
    else:
        missing.append(name)

total = len(urls)
done = len(present)
left = len(missing)
bytes_done = sum(size for _, size in present)

print(f"subset_dir={subset_dir}")
print(f"total_urls={total}")
print(f"downloaded={done}")
print(f"missing={left}")
print(f"downloaded_bytes={bytes_done}")
if total > 0:
    print(f"completion_ratio={done / total:.4f}")
if missing:
    print("first_missing=")
    for name in missing[:20]:
        print(name)
PY
