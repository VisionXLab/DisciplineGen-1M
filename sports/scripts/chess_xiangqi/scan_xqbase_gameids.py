#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

VALID_TOKENS = ["jsboard(", "gameid=", "xqbase"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sequentially scan XQBase gameid pages and collect valid game URLs.")
    parser.add_argument("--start-gameid", type=int, default=1)
    parser.add_argument("--max-gameid", type=int, default=0, help="0 means no explicit upper bound.")
    parser.add_argument("--stop-empty-run", type=int, default=5000, help="Stop after this many consecutive invalid game IDs.")
    parser.add_argument("--max-valid", type=int, default=0, help="Stop after collecting this many valid game URLs. 0 means no limit.")
    parser.add_argument("--base-url", default="https://www.xqbase.com/xqbase/?gameid={gameid}")
    parser.add_argument("--output-urls", required=True)
    parser.add_argument("--output-log", default="", help="Optional TSV log of probed ids and validity.")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--prefer-wget", action="store_true")
    parser.add_argument("--user-agent", default="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36")
    return parser.parse_args()


def decode_bytes(raw: bytes, content_charset: str | None = None) -> str:
    for encoding in [content_charset, "utf-8", "gb18030", "gbk", "latin1"]:
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin1", errors="ignore")


def fetch_via_urllib(url: str, timeout: float, user_agent: str) -> str:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        content_type = response.headers.get_content_charset()
    return decode_bytes(raw, content_type)


def fetch_via_wget(url: str, timeout: float, user_agent: str, retries: int) -> str:
    if shutil.which("wget") is None:
        raise RuntimeError("wget not found in PATH")
    cmd = [
        "wget",
        "-qO-",
        f"--timeout={max(1, int(timeout))}",
        f"--tries={max(1, retries)}",
        f"--user-agent={user_agent}",
        url,
    ]
    proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return decode_bytes(proc.stdout)


def fetch_text(url: str, timeout: float, user_agent: str, retries: int, prefer_wget: bool) -> str:
    methods = ["wget", "urllib"] if prefer_wget else ["urllib", "wget"]
    errors: list[str] = []
    for method in methods:
        for attempt in range(1, retries + 1):
            try:
                if method == "wget":
                    return fetch_via_wget(url, timeout=timeout, user_agent=user_agent, retries=retries)
                return fetch_via_urllib(url, timeout=timeout, user_agent=user_agent)
            except Exception as exc:
                errors.append(f"{method} attempt {attempt}: {exc}")
                if attempt < retries:
                    time.sleep(min(1.0, 0.2 * attempt))
    raise RuntimeError(" | ".join(errors[-6:]))


def is_valid_game_page(text: str, gameid: int) -> bool:
    lowered = text.lower()
    if "jsboard(" in lowered:
        return True
    if f"gameid={gameid}" in lowered and any(token in lowered for token in VALID_TOKENS):
        return True
    return False


def main() -> int:
    args = parse_args()
    empty_run = 0
    current = args.start_gameid
    valid_count = 0

    output_urls = Path(args.output_urls)
    output_urls.parent.mkdir(parents=True, exist_ok=True)
    output_log = Path(args.output_log) if args.output_log else None
    if output_log is not None:
        output_log.parent.mkdir(parents=True, exist_ok=True)

    with output_urls.open("w", encoding="utf-8") as urls_fp, (output_log.open("w", encoding="utf-8") if output_log else open(Path(os.devnull), "w", encoding="utf-8")) as log_fp:
        while True:
            if args.max_gameid > 0 and current > args.max_gameid:
                break
            if args.max_valid > 0 and valid_count >= args.max_valid:
                break
            if args.stop_empty_run > 0 and empty_run >= args.stop_empty_run:
                break

            url = args.base_url.format(gameid=current)
            status = "invalid"
            detail = ""
            try:
                text = fetch_text(url, timeout=args.timeout, user_agent=args.user_agent, retries=args.retries, prefer_wget=args.prefer_wget)
                if is_valid_game_page(text, current):
                    urls_fp.write(url + "\n")
                    valid_count += 1
                    empty_run = 0
                    status = "valid"
                else:
                    empty_run += 1
            except Exception as exc:
                empty_run += 1
                detail = str(exc).replace("\t", " ")
                status = "error"

            if output_log is not None:
                log_fp.write(f"{current}\t{status}\t{empty_run}\t{detail}\n")

            if current % 100 == 0:
                urls_fp.flush()
                if output_log is not None:
                    log_fp.flush()
                print(f"[scan] current_gameid={current} valid={valid_count} empty_run={empty_run}", file=sys.stderr)

            current += 1
            if args.delay > 0:
                time.sleep(args.delay)

    if valid_count == 0:
        raise SystemExit("No valid XQBase game pages were discovered. Try a smaller start-gameid, larger timeout, or lower delay.")

    print(f"Discovered {valid_count} valid XQBase game URLs.")
    print(f"URL list written to {output_urls}")
    if output_log is not None:
        print(f"Probe log written to {output_log}")
    return 0


if __name__ == "__main__":
    import os
    raise SystemExit(main())

