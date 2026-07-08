#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

GAMEIDS_RE = re.compile(r"var\s+gameids\s*=\s*\[(.*?)\];", re.S)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-html", required=True, help="Downloaded XQBase search-result HTML file")
    parser.add_argument("--output-urls", required=True, help="Output text file with one game URL per line")
    parser.add_argument(
        "--base-url",
        default="https://www.xqbase.com/xqbase/?gameid=",
        help="URL prefix used to build full game URLs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    html = Path(args.input_html).read_text(encoding="latin1", errors="ignore")
    match = GAMEIDS_RE.search(html)
    if not match:
        raise SystemExit("Could not find `var gameids = [...]` in the input HTML.")

    raw_ids = match.group(1)
    ids = [token.strip() for token in raw_ids.split(",") if token.strip()]
    ids = [gid for gid in ids if gid.isdigit()]
    if not ids:
        raise SystemExit("No numeric game IDs found.")

    output = Path(args.output_urls)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for gid in ids:
            f.write(f"{args.base_url}{gid}\n")

    print(f"Extracted {len(ids)} game URLs to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
