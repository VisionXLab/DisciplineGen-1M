#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_DATASET_URLS = {
    "foundation": "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_json_2025-12-18.zip",
    "survey": "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_survey_food_json_2024-10-31.zip",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and extract USDA FoodData Central archives for sports nutrition dataset construction.")
    parser.add_argument("--output-dir", required=True, help="Output directory, e.g. raw_data/sports_nutrition/usda")
    parser.add_argument(
        "--dataset",
        nargs="*",
        default=["foundation", "survey"],
        choices=sorted(DEFAULT_DATASET_URLS),
        help="Official USDA dataset presets to download.",
    )
    parser.add_argument("--url", action="append", default=[], help="Additional custom ZIP URL. Can be repeated.")
    parser.add_argument("--user-agent", default="Mozilla/5.0")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--prefer-wget", action="store_true", help="Use wget first when available.")
    parser.add_argument("--skip-extract", action="store_true")
    parser.add_argument("--force", action="store_true", help="Redownload and re-extract even if files already exist.")
    return parser.parse_args()


def download_bytes_urllib(url: str, user_agent: str, timeout: float) -> bytes:
    req = Request(url, headers={"User-Agent": user_agent})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def download_with_wget(url: str, archive_path: Path, user_agent: str, timeout: float, retries: int) -> None:
    cmd = [
        "wget",
        "--continue",
        "--timestamping",
        f"--timeout={max(1, int(timeout))}",
        f"--tries={max(1, retries)}",
        f"--user-agent={user_agent}",
        "-O",
        str(archive_path),
        url,
    ]
    subprocess.run(cmd, check=True)


def download_bytes(url: str, user_agent: str, timeout: float, retries: int) -> bytes:
    errors: list[str] = []
    for attempt in range(1, retries + 1):
        try:
            return download_bytes_urllib(url, user_agent, timeout)
        except Exception as exc:
            errors.append(f"urllib attempt {attempt}: {exc}")
            if attempt < retries:
                time.sleep(min(2.0, 0.5 * attempt))
    raise RuntimeError(f"Failed to download {url}: {' | '.join(errors[-6:])}")


def download_archive(url: str, archive_path: Path, user_agent: str, timeout: float, retries: int, prefer_wget: bool, force: bool) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists() and archive_path.stat().st_size > 0 and not force:
        print(f"[skip] archive exists: {archive_path}")
        return
    print(f"[download] {url}")
    if prefer_wget or shutil.which('wget'):
        download_with_wget(url, archive_path, user_agent, timeout, retries)
    else:
        archive_path.write_bytes(download_bytes(url, user_agent, timeout, retries))


def extract_archive(archive_path: Path, extract_dir: Path, force: bool) -> None:
    if extract_dir.exists() and any(extract_dir.iterdir()) and not force:
        print(f"[skip] extracted dir exists: {extract_dir}")
        return
    if extract_dir.exists() and force:
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    print(f"[extract] {archive_path} -> {extract_dir}")
    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(extract_dir)


def save_manifest(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    manifest: list[dict[str, Any]] = []

    jobs: list[tuple[str, str]] = []
    for dataset in args.dataset:
        jobs.append((dataset, DEFAULT_DATASET_URLS[dataset]))
    for index, url in enumerate(args.url, start=1):
        jobs.append((f"custom_{index}", url))

    if not jobs:
        raise SystemExit("No datasets selected. Use --dataset and/or --url.")

    for dataset_name, url in jobs:
        archive_name = Path(url).name or f"{dataset_name}.zip"
        dataset_dir = output_dir / dataset_name
        archive_path = dataset_dir / "archive" / archive_name
        extract_dir = dataset_dir / "extracted"
        download_archive(url, archive_path, args.user_agent, args.timeout, args.retries, args.prefer_wget, args.force)
        if not args.skip_extract:
            extract_archive(archive_path, extract_dir, args.force)
        manifest.append(
            {
                "dataset": dataset_name,
                "url": url,
                "archive_path": archive_path.as_posix(),
                "extract_dir": extract_dir.as_posix(),
                "extracted": not args.skip_extract,
            }
        )

    manifest_path = output_dir / "download_manifest.json"
    save_manifest(manifest_path, manifest)
    print(f"Saved manifest to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
