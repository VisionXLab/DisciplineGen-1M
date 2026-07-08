#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from nutrition_utils import normalize_text, strip_html_tags


COMMONS_API = "https://commons.wikimedia.org/w/api.php"
NEGATIVE_TITLE_KEYWORDS = {
    "icon",
    "logo",
    "diagram",
    "chart",
    "label",
    "package",
    "packaging",
    "nutrition facts",
    "infobox",
    "map",
    "coat of arms",
    "flag",
    "animated",
    "painting",
    "museum",
}
PREFERRED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
SEARCH_STOPWORDS = {
    "raw",
    "cooked",
    "nfs",
    "ns",
    "prepared",
    "dry",
    "unenriched",
    "enriched",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and match real food images from Wikimedia Commons for sports nutrition dataset construction.")
    parser.add_argument("--input-jsonl", required=True)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--output-dir", required=True, help="Directory for downloaded images, e.g. raw_data/sports_nutrition/images")
    parser.add_argument("--max-records", type=int, default=0, help="0 means no limit.")
    parser.add_argument("--search-limit", type=int, default=8)
    parser.add_argument("--thumb-width", type=int, default=900)
    parser.add_argument("--min-width", type=int, default=256)
    parser.add_argument("--min-height", type=int, default=256)
    parser.add_argument("--request-delay", type=float, default=0.8, help="Delay in seconds between remote requests.")
    parser.add_argument("--retry-count", type=int, default=4)
    parser.add_argument("--retry-base-seconds", type=float, default=2.0)
    parser.add_argument("--http-timeout", type=float, default=30.0, help="Per-request timeout in seconds.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--user-agent", default="Mozilla/5.0")
    return parser.parse_args()


def request_with_retry(url: str, user_agent: str, retry_count: int, retry_base_seconds: float, expect_json: bool, timeout: float) -> Any:
    for attempt in range(retry_count + 1):
        try:
            req = Request(url, headers={"User-Agent": user_agent})
            with urlopen(req, timeout=timeout) as resp:
                payload = resp.read()
            return json.loads(payload.decode("utf-8")) if expect_json else payload
        except HTTPError as exc:
            if exc.code == 429 or 500 <= exc.code < 600:
                if attempt < retry_count:
                    wait_seconds = retry_base_seconds * (2 ** attempt)
                    print(f"    [retry] HTTP {exc.code}, sleep {wait_seconds:.1f}s", flush=True)
                    time.sleep(wait_seconds)
                    continue
            raise
        except (URLError, TimeoutError) as exc:
            if attempt < retry_count:
                wait_seconds = retry_base_seconds * (2 ** attempt)
                print(f"    [retry] {type(exc).__name__}, sleep {wait_seconds:.1f}s", flush=True)
                time.sleep(wait_seconds)
                continue
            raise


def http_get_json(url: str, user_agent: str, retry_count: int, retry_base_seconds: float, timeout: float) -> dict[str, Any]:
    return request_with_retry(url, user_agent, retry_count, retry_base_seconds, expect_json=True, timeout=timeout)


def http_get_bytes(url: str, user_agent: str, retry_count: int, retry_base_seconds: float, timeout: float) -> bytes:
    return request_with_retry(url, user_agent, retry_count, retry_base_seconds, expect_json=False, timeout=timeout)


def api_get(params: dict[str, Any], user_agent: str, retry_count: int, retry_base_seconds: float, timeout: float) -> dict[str, Any]:
    query = urlencode({**params, "format": "json", "formatversion": 2})
    return http_get_json(f"{COMMONS_API}?{query}", user_agent, retry_count, retry_base_seconds, timeout)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def save_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def file_basename(title: str) -> str:
    title = title.removeprefix("File:")
    title = re.sub(r"\.[A-Za-z0-9]+$", "", title)
    return title


def file_extension(title: str) -> str:
    match = re.search(r"\.([A-Za-z0-9]+)$", title)
    return match.group(1).lower() if match else ""


def clean_food_phrase(food_name: str) -> str:
    text = food_name.strip()
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if parts:
        head = normalize_text(parts[0])
        if head in {"pie", "soup", "salad", "sandwich", "sauce"} and len(parts) >= 2:
            return parts[1]
        if len(parts) >= 2 and head in {"flour"}:
            return f"{parts[1]} flour"
        if len(parts) >= 2 and head in {"beans", "bean"}:
            return " ".join(parts[:2])
        return parts[0]
    tokens = [token for token in normalize_text(text).split() if token and token not in SEARCH_STOPWORDS]
    if len(tokens) >= 2:
        return " ".join(tokens)
    return text


def build_search_terms(food_name: str) -> list[str]:
    terms: list[str] = []
    base = food_name.strip()
    cleaned = clean_food_phrase(base)
    for term in [base, cleaned]:
        if term:
            terms.append(term)
    normalized = normalize_text(cleaned or base)
    alias_map = {
        "greek yogurt": ["yogurt"],
        "yogurt": ["plain yogurt"],
        "chicken breast": ["chicken breast", "chicken"],
        "beef steak": ["steak", "beef"],
        "white rice": ["white rice", "rice"],
        "brown rice": ["brown rice", "rice"],
        "rice flour": ["rice flour"],
        "wheat bread": ["bread"],
        "white bread": ["bread"],
        "whey protein": ["protein powder"],
        "black beans": ["black bean", "beans"],
        "beans and white rice": ["rice and beans", "white rice"],
        "beans and brown rice": ["rice and beans", "brown rice"],
        "egg sandwich on wheat bread": ["egg sandwich", "wheat bread"],
        "egg sandwich on white bread": ["egg sandwich", "white bread"],
        "pie oatmeal": ["oatmeal"],
        "pie sweet potato": ["sweet potato"],
    }
    for key, aliases in alias_map.items():
        if key in normalized:
            terms.extend(aliases)
    if " and " in normalized:
        terms.extend([part.strip() for part in normalized.split(" and ") if part.strip()])
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        norm = normalize_text(term)
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append(term)
    return deduped


def search_titles(term: str, limit: int, user_agent: str, retry_count: int, retry_base_seconds: float, timeout: float) -> list[str]:
    payload = api_get(
        {
            "action": "query",
            "list": "search",
            "srsearch": f'intitle:"{term}"',
            "srnamespace": 6,
            "srlimit": limit,
        },
        user_agent,
        retry_count,
        retry_base_seconds,
        timeout,
    )
    return [item["title"] for item in payload.get("query", {}).get("search", []) if isinstance(item, dict) and item.get("title")]


def fetch_imageinfo(titles: list[str], thumb_width: int, user_agent: str, retry_count: int, retry_base_seconds: float, timeout: float) -> list[dict[str, Any]]:
    if not titles:
        return []
    payload = api_get(
        {
            "action": "query",
            "prop": "imageinfo|info",
            "titles": "|".join(titles),
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": thumb_width,
            "inprop": "url",
        },
        user_agent,
        retry_count,
        retry_base_seconds,
        timeout,
    )
    return [page for page in payload.get("query", {}).get("pages", []) if isinstance(page, dict) and not page.get("missing")]


def extmeta_value(extmetadata: dict[str, Any], key: str) -> str:
    value = extmetadata.get(key, {}) if isinstance(extmetadata, dict) else {}
    if isinstance(value, dict):
        return strip_html_tags(str(value.get("value", "")))
    return strip_html_tags(str(value))


def score_candidate(page: dict[str, Any], food_name: str) -> float:
    title = str(page.get("title", ""))
    norm_title = normalize_text(file_basename(title))
    norm_food = normalize_text(clean_food_phrase(food_name))
    if not norm_title:
        return -1e9
    score = 0.0
    if norm_title == norm_food:
        score += 120
    elif norm_food in norm_title:
        score += 70
    food_tokens = [token for token in norm_food.split() if token]
    title_tokens = set(norm_title.split())
    score += sum(12 for token in food_tokens if token in title_tokens)
    for negative in NEGATIVE_TITLE_KEYWORDS:
        if negative in norm_title:
            score -= 100
    ext = file_extension(title)
    if ext in PREFERRED_EXTENSIONS:
        score += 8
    imageinfo = (page.get("imageinfo") or [{}])[0]
    width = int(imageinfo.get("width") or 0)
    height = int(imageinfo.get("height") or 0)
    score += min(width, 3000) / 500.0
    score += min(height, 3000) / 500.0
    if width < 256 or height < 256:
        score -= 60
    extmetadata = imageinfo.get("extmetadata", {}) if isinstance(imageinfo, dict) else {}
    license_short = extmeta_value(extmetadata, "LicenseShortName").lower()
    if license_short:
        score += 4
    return score


def choose_candidate(pages: list[dict[str, Any]], food_name: str, min_width: int, min_height: int) -> dict[str, Any] | None:
    best_page: dict[str, Any] | None = None
    best_score = -1e18
    for page in pages:
        imageinfo = (page.get("imageinfo") or [{}])[0]
        width = int(imageinfo.get("width") or 0)
        height = int(imageinfo.get("height") or 0)
        if width < min_width or height < min_height:
            continue
        score = score_candidate(page, food_name)
        if score > best_score:
            best_page = page
            best_score = score
    return best_page


def safe_filename(source_id: str, title: str) -> str:
    ext = file_extension(title) or "jpg"
    tail = re.sub(r"[^A-Za-z0-9._-]+", "_", file_basename(title))[:80].strip("_") or "image"
    return f"{source_id}_{tail}.{ext}"


def enrich_record(record: dict[str, Any], page: dict[str, Any], local_path: Path) -> dict[str, Any]:
    out = dict(record)
    imageinfo = (page.get("imageinfo") or [{}])[0]
    extmetadata = imageinfo.get("extmetadata", {}) if isinstance(imageinfo, dict) else {}
    out["image_title"] = str(page.get("title", ""))
    out["image_url"] = str(imageinfo.get("thumburl") or imageinfo.get("url") or "")
    out["image_page_url"] = str(page.get("fullurl") or f"https://commons.wikimedia.org/wiki/{str(page.get('title', '')).replace(' ', '_')}")
    out["image_license"] = extmeta_value(extmetadata, "LicenseShortName") or extmeta_value(extmetadata, "License")
    out["image_attribution"] = extmeta_value(extmetadata, "Artist") or extmeta_value(extmetadata, "Credit")
    out["image_source"] = "wikimedia_commons"
    out["local_image_path"] = local_path.as_posix()
    meta = dict(out.get("meta", {}))
    meta["image_width"] = int(imageinfo.get("width") or 0)
    meta["image_height"] = int(imageinfo.get("height") or 0)
    meta["image_mime"] = str(imageinfo.get("mime") or "")
    out["meta"] = meta
    return out


def main() -> int:
    args = parse_args()
    input_records = load_jsonl(Path(args.input_jsonl))
    if args.max_records > 0:
        input_records = input_records[: args.max_records]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    enriched: list[dict[str, Any]] = []
    success = 0
    misses = 0

    for index, record in enumerate(input_records, start=1):
        food_name = str(record.get("food_name", "")).strip()
        source_id = str(record.get("source_id", f"food_{index}"))
        if not food_name:
            enriched.append(record)
            misses += 1
            continue

        local_existing = Path(str(record.get("local_image_path", ""))) if record.get("local_image_path") else None
        if local_existing and local_existing.exists() and not args.overwrite:
            enriched.append(record)
            success += 1
            print(f"[{index}/{len(input_records)}] keep existing image for {food_name}", flush=True)
            continue

        print(f"[{index}/{len(input_records)}] searching image for {food_name}", flush=True)
        terms = build_search_terms(food_name)
        print(f"  [terms] {terms}", flush=True)
        candidate_titles: list[str] = []
        seen_titles: set[str] = set()
        for term in terms:
            try:
                print(f"  [search] {term}", flush=True)
                titles = search_titles(term, args.search_limit, args.user_agent, args.retry_count, args.retry_base_seconds, args.http_timeout)
                time.sleep(args.request_delay)
            except Exception as exc:
                print(f"  [warn] search failed for '{term}': {exc}", flush=True)
                continue
            for title in titles:
                if title not in seen_titles:
                    seen_titles.add(title)
                    candidate_titles.append(title)
        if not candidate_titles:
            print(f"  [miss] no Wikimedia titles found", flush=True)
            enriched.append(record)
            misses += 1
            continue

        try:
            print(f"  [imageinfo] {min(len(candidate_titles), 50)} candidates", flush=True)
            pages = fetch_imageinfo(candidate_titles[:50], args.thumb_width, args.user_agent, args.retry_count, args.retry_base_seconds, args.http_timeout)
            time.sleep(args.request_delay)
        except Exception as exc:
            print(f"  [warn] imageinfo failed: {exc}", flush=True)
            enriched.append(record)
            misses += 1
            continue

        best_page = choose_candidate(pages, food_name, args.min_width, args.min_height)
        if best_page is None:
            print(f"  [miss] no usable image candidate", flush=True)
            enriched.append(record)
            misses += 1
            continue

        imageinfo = (best_page.get("imageinfo") or [{}])[0]
        download_url = str(imageinfo.get("thumburl") or imageinfo.get("url") or "")
        if not download_url:
            print(f"  [miss] chosen candidate has no downloadable URL", flush=True)
            enriched.append(record)
            misses += 1
            continue

        target_path = output_dir / safe_filename(source_id, str(best_page.get("title", "")))
        try:
            if not target_path.exists() or args.overwrite:
                print(f"  [download] {best_page.get('title', '')}", flush=True)
                target_path.write_bytes(http_get_bytes(download_url, args.user_agent, args.retry_count, args.retry_base_seconds, args.http_timeout))
                time.sleep(args.request_delay)
        except Exception as exc:
            print(f"  [warn] download failed: {exc}", flush=True)
            enriched.append(record)
            misses += 1
            continue

        updated = enrich_record(record, best_page, target_path)
        enriched.append(updated)
        success += 1
        print(f"  [ok] {food_name} -> {best_page.get('title', '')}", flush=True)

    save_jsonl(Path(args.output_jsonl), enriched)
    print(f"Saved {len(enriched)} records to {args.output_jsonl}", flush=True)
    print(f"Image matches: {success}, misses: {misses}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
