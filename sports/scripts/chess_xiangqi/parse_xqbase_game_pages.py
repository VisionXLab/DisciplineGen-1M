#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)
OPENING_RE = re.compile(r"<a[^>]+href=[\"'](?:https?://www\.xqbase\.com)?/xqbase/\?ecco=[^\"']+[\"'][^>]*><b>(.*?)</b></a>", re.I | re.S)
JSBOARD_RE = re.compile(r"jsboard\(\s*[\"'].*?[\"']\s*,\s*[\"'](.*?)[\"']\s*\)", re.I | re.S)
GAMEID_RE = re.compile(r"gameid=(\d+)")
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
MOVE_RE = re.compile(r"([A-I][0-9]-[A-I][0-9])")

STARTPOS_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w"
ENCODINGS = ["utf-8", "gb18030", "gbk", "latin1"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, help="Directory containing downloaded XQBase game HTML files")
    parser.add_argument("--output-jsonl", required=True, help="Output normalized JSONL path")
    return parser.parse_args()


def clean_html_text(text: str) -> str:
    text = TAG_RE.sub("", text)
    text = text.replace("&nbsp;", " ")
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def read_html_text(path: Path) -> str:
    raw_bytes = path.read_bytes()
    for encoding in ENCODINGS:
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("latin1", errors="ignore")


def parse_game_file(path: Path) -> dict | None:
    raw = read_html_text(path)

    move_match = JSBOARD_RE.search(raw)
    if not move_match:
        return None
    raw_moves = move_match.group(1)
    move_tokens = MOVE_RE.findall(raw_moves)
    moves_ucci = [mv.replace("-", "").lower() for mv in move_tokens]
    if not moves_ucci:
        return None

    opening = ""
    opening_match = OPENING_RE.search(raw)
    if opening_match:
        opening = clean_html_text(opening_match.group(1))

    title = ""
    title_match = TITLE_RE.search(raw)
    if title_match:
        title = clean_html_text(title_match.group(1))

    source_id = path.stem
    gid_match = GAMEID_RE.search(raw) or GAMEID_RE.search(path.name)
    if gid_match:
        source_id = f"xqbase_{gid_match.group(1)}"

    return {
        "source_id": source_id,
        "title": title,
        "opening": opening,
        "initial_fen": STARTPOS_FEN,
        "moves_ucci": moves_ucci,
    }


def iter_html_files(input_dir: Path):
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".html", ".htm", ""}:
            yield path


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    output = Path(args.output_jsonl)
    output.parent.mkdir(parents=True, exist_ok=True)

    files = list(iter_html_files(input_dir))
    count = 0
    invalid = []

    with output.open("w", encoding="utf-8") as f:
        for path in files:
            obj = parse_game_file(path)
            if obj is None:
                invalid.append(path.name)
                continue
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            count += 1

    if count == 0:
        preview = ", ".join(invalid[:5]) if invalid else "no html files found"
        raise SystemExit(
            f"No valid XQBase game pages were parsed. Scanned {len(files)} files. "
            f"Examples: {preview}. Check whether these are real game pages containing jsboard(...)."
        )

    print(f"Parsed {count} game pages into {output}")
    if invalid:
        print(f"Skipped {len(invalid)} files without valid jsboard move content")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
