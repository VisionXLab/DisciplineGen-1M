#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

GAMEIDS_ARRAY_RE = re.compile(r"var\s+gameids\s*=\s*\[(.*?)\];", re.I | re.S)
GAMEID_RE = re.compile(r"gameid=(\d+)", re.I)
HREF_RE = re.compile(r"href=[\"']([^\"']+)[\"']", re.I)

DEFAULT_SEEDS = [
    "https://www.xqbase.com/xqbase/",
    "https://www.xqbase.com/ecco/ecco_contents.htm",
    "http://www.xqbase.com/xqbase/",
    "http://www.xqbase.com/ecco/ecco_contents.htm",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl XQBase catalog/listing pages and extract all discovered game URLs.")
    parser.add_argument("--seed-url", action="append", default=[], help="Seed catalog URL. Repeatable.")
    parser.add_argument("--output-urls", required=True, help="Output text file with one game URL per line.")
    parser.add_argument("--output-pages", default="", help="Optional output text file containing crawled catalog pages.")
    parser.add_argument("--max-pages", type=int, default=0, help="Maximum number of catalog pages to crawl. 0 means no limit.")
    parser.add_argument("--max-game-urls", type=int, default=0, help="Maximum number of discovered game URLs to keep. 0 means no limit.")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between requests in seconds.")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3, help="Retry count per URL before giving up.")
    parser.add_argument("--prefer-wget", action="store_true", help="Use wget first when available.")
    parser.add_argument("--user-agent", default="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36")
    return parser.parse_args()


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    query = parsed.query
    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    if normalized.endswith("/") and path not in {"/", ""}:
        normalized = normalized[:-1]
    return normalized


def is_xqbase_host(netloc: str) -> bool:
    host = netloc.lower()
    return host == "xqbase.com" or host == "www.xqbase.com"




def should_enqueue_xqbase_query(query: str) -> bool:
    lowered = query.lower()
    if not lowered:
        return True
    if 'gameid=' in lowered:
        return False
    allowed_tokens = ['ecco=', 'page=', 'event=', 'title=', 'search=', 'keyword=', 'opening=']
    return any(token in lowered for token in allowed_tokens)

def should_enqueue_page(url: str) -> bool:
    parsed = urlparse(url)
    if not is_xqbase_host(parsed.netloc):
        return False
    query = (parsed.query or '').lower()
    if GAMEID_RE.search(query):
        return False
    path = (parsed.path or '/').lower()
    if path.endswith(('.jpg', '.jpeg', '.png', '.gif', '.zip', '.rar', '.pdf', '.css', '.js')):
        return False
    if path in {'/xqbase', '/xqbase/'}:
        return should_enqueue_xqbase_query(query)
    if path in {'/ecco', '/ecco/', '/ecco/ecco_contents.htm'}:
        return True
    if path.startswith('/ecco/') and path.endswith(('.htm', '.html')):
        return True
    if path.startswith('/xqbase/'):
        return True
    return False


def extract_game_urls(text: str) -> list[str]:
    ids: set[str] = set()
    array_match = GAMEIDS_ARRAY_RE.search(text)
    if array_match:
        ids.update(token.strip() for token in array_match.group(1).split(",") if token.strip().isdigit())
    ids.update(GAMEID_RE.findall(text))
    return [f"https://www.xqbase.com/xqbase/?gameid={gid}" for gid in sorted(ids, key=int)]


def extract_links(page_url: str, text: str) -> list[str]:
    links: list[str] = []
    for href in HREF_RE.findall(text):
        href = html.unescape(href.strip())
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        links.append(canonicalize_url(urljoin(page_url, href)))
    return links


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


def url_variants(url: str) -> list[str]:
    parsed = urlparse(url)
    out: list[str] = []
    candidates = []
    if parsed.scheme:
        candidates.append(url)
        alt_scheme = "http" if parsed.scheme == "https" else "https"
        candidates.append(urlunparse((alt_scheme, parsed.netloc, parsed.path, "", parsed.query, "")))
    else:
        candidates.extend([f"https://{url}", f"http://{url}"])
    seen: set[str] = set()
    for candidate in candidates:
        normalized = canonicalize_url(candidate)
        if normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def fetch_text(url: str, timeout: float, user_agent: str, retries: int, prefer_wget: bool) -> str:
    methods = ["wget", "urllib"] if prefer_wget else ["urllib", "wget"]
    errors: list[str] = []
    for candidate in url_variants(url):
        for method in methods:
            for attempt in range(1, retries + 1):
                try:
                    if method == "wget":
                        return fetch_via_wget(candidate, timeout=timeout, user_agent=user_agent, retries=retries)
                    return fetch_via_urllib(candidate, timeout=timeout, user_agent=user_agent)
                except Exception as exc:
                    errors.append(f"{candidate} via {method} attempt {attempt}: {exc}")
                    if attempt < retries:
                        time.sleep(min(1.0, 0.2 * attempt))
                    continue
    raise RuntimeError(" | ".join(errors[-6:]))


def main() -> int:
    args = parse_args()
    raw_seeds = args.seed_url if args.seed_url else DEFAULT_SEEDS
    seed_urls: list[str] = []
    seen_seed: set[str] = set()
    for seed in raw_seeds:
        for candidate in url_variants(seed):
            if candidate not in seen_seed:
                seen_seed.add(candidate)
                seed_urls.append(candidate)
    queue: deque[str] = deque(seed_urls)
    seen_pages: set[str] = set()
    seen_games: set[str] = set()
    crawled_pages: list[str] = []
    discovered_games: list[str] = []

    while queue:
        if args.max_pages > 0 and len(crawled_pages) >= args.max_pages:
            break
        url = queue.popleft()
        if url in seen_pages:
            continue
        seen_pages.add(url)
        try:
            text = fetch_text(url, timeout=args.timeout, user_agent=args.user_agent, retries=args.retries, prefer_wget=args.prefer_wget)
        except Exception as exc:
            print(f"[warn] failed to fetch {url}: {exc}", file=sys.stderr)
            continue

        crawled_pages.append(url)
        if len(crawled_pages) % 20 == 0:
            print(f"[crawl] pages={len(crawled_pages)} games={len(discovered_games)} current={url}", file=sys.stderr)

        for game_url in extract_game_urls(text):
            if game_url in seen_games:
                continue
            seen_games.add(game_url)
            discovered_games.append(game_url)
            if args.max_game_urls > 0 and len(discovered_games) >= args.max_game_urls:
                break
        if args.max_game_urls > 0 and len(discovered_games) >= args.max_game_urls:
            break

        for link in extract_links(url, text):
            if should_enqueue_page(link) and link not in seen_pages:
                queue.append(link)

        if args.delay > 0:
            time.sleep(args.delay)

    output_urls = Path(args.output_urls)
    output_urls.parent.mkdir(parents=True, exist_ok=True)
    output_urls.write_text("\n".join(discovered_games) + ("\n" if discovered_games else ""), encoding="utf-8")

    if args.output_pages:
        output_pages = Path(args.output_pages)
        output_pages.parent.mkdir(parents=True, exist_ok=True)
        output_pages.write_text("\n".join(crawled_pages) + ("\n" if crawled_pages else ""), encoding="utf-8")

    if not discovered_games:
        raise SystemExit("No XQBase game URLs were discovered. The server may be slow or blocked from this machine. Try --prefer-wget, larger --timeout, or custom --seed-url values.")

    print(f"Discovered {len(discovered_games)} XQBase game URLs from {len(crawled_pages)} catalog pages.")
    print(f"Game URL list written to {output_urls}")
    if args.output_pages:
        print(f"Catalog page list written to {args.output_pages}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
