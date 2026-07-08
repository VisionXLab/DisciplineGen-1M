#!/usr/bin/env python3
"""Extract complete PGN games from a Lichess .pgn.zst file.

This script reads the compressed file via `zstd -dc` so it does not require
full decompression to disk. It writes complete PGN games to an output file.

Examples:
  python scripts/extract_lichess_pgn_sample.py \
    --input-zst raw_data/chess/lichess_db_standard_rated_2026-03.pgn.zst \
    --output raw_data/chess/sample_10000_games.pgn \
    --max-games 10000

  python scripts/extract_lichess_pgn_sample.py \
    --input-zst raw_data/chess/lichess_db_standard_rated_2026-03.pgn.zst \
    --output raw_data/chess/openings_sample.pgn \
    --max-games 2000 \
    --opening "Polish Opening" \
    --opening "Queen's Gambit"
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


TAG_RE = re.compile(r'^\[(\w+)\s+"(.*)"\]\s*$')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-zst", required=True, help="Path to .pgn.zst")
    parser.add_argument("--output", required=True, help="Output PGN path")
    parser.add_argument("--max-games", type=int, default=1000)
    parser.add_argument(
        "--opening",
        action="append",
        default=[],
        help="Keep only games whose Opening tag contains this string. Repeatable.",
    )
    parser.add_argument(
        "--event",
        action="append",
        default=[],
        help="Keep only games whose Event tag contains this string. Repeatable.",
    )
    return parser.parse_args()


def keep_game(tags: dict[str, str], openings: list[str], events: list[str]) -> bool:
    opening = tags.get("Opening", "")
    event = tags.get("Event", "")

    if openings:
        opening_l = opening.lower()
        if not any(token.lower() in opening_l for token in openings):
            return False

    if events:
        event_l = event.lower()
        if not any(token.lower() in event_l for token in events):
            return False

    return True


def iter_games_from_zst(input_zst: Path):
    proc = subprocess.Popen(
        ["zstd", "-dc", str(input_zst)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None

    current_lines: list[str] = []
    current_tags: dict[str, str] = {}
    in_moves = False

    for raw_line in proc.stdout:
        line = raw_line.rstrip("\n")

        if not current_lines and not line.strip():
            continue

        if line.startswith("["):
            current_lines.append(raw_line)
            match = TAG_RE.match(line)
            if match:
                current_tags[match.group(1)] = match.group(2)
            continue

        if not line.strip():
            current_lines.append(raw_line)
            if in_moves:
                yield current_tags, "".join(current_lines).strip() + "\n\n"
                current_lines = []
                current_tags = {}
                in_moves = False
            continue

        in_moves = True
        current_lines.append(raw_line)

    if current_lines and in_moves:
        yield current_tags, "".join(current_lines).strip() + "\n\n"

    ret = proc.wait()
    if ret != 0:
        stderr = ""
        if proc.stderr is not None:
            stderr = proc.stderr.read()
        raise RuntimeError(f"zstd failed with exit code {ret}: {stderr}")


def main() -> int:
    args = parse_args()
    input_zst = Path(args.input_zst)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    kept = 0
    seen = 0

    with output.open("w", encoding="utf-8") as f:
        for tags, pgn_text in iter_games_from_zst(input_zst):
            seen += 1
            if keep_game(tags, args.opening, args.event):
                f.write(pgn_text)
                kept += 1
                if kept >= args.max_games:
                    break

            if seen % 100000 == 0:
                print(f"Scanned {seen} games, kept {kept}...", file=sys.stderr)

    print(f"Done. Scanned {seen} games, kept {kept}. Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
