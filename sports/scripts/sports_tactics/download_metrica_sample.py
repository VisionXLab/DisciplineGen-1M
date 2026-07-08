#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path


DEFAULT_ARCHIVE_URL = 'https://github.com/metrica-sports/sample-data/archive/refs/heads/master.zip'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Download and extract Metrica Sports sample-data from GitHub.')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--archive-url', default=DEFAULT_ARCHIVE_URL)
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--prefer-wget', action='store_true')
    parser.add_argument('--timeout', type=float, default=60.0)
    parser.add_argument('--retries', type=int, default=4)
    parser.add_argument('--user-agent', default='Mozilla/5.0')
    return parser.parse_args()


def download_with_wget(url: str, archive_path: Path, timeout: float, retries: int, user_agent: str) -> None:
    cmd = [
        'wget',
        '--continue',
        '--timestamping',
        f'--timeout={max(1, int(timeout))}',
        f'--tries={max(1, retries)}',
        f'--user-agent={user_agent}',
        '-O',
        str(archive_path),
        url,
    ]
    subprocess.run(cmd, check=True)


def download_archive(url: str, archive_path: Path, force: bool, prefer_wget: bool, timeout: float, retries: int, user_agent: str) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists() and archive_path.stat().st_size > 0 and not force:
        print(f'[skip] archive exists: {archive_path}')
        return
    print(f'[download] {url}')
    if prefer_wget or shutil.which('wget'):
        download_with_wget(url, archive_path, timeout, retries, user_agent)
    else:
        urllib.request.urlretrieve(url, archive_path)


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    archive_dir = output_dir / 'archive'
    extract_dir = output_dir / 'extracted'
    archive_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    archive_path = archive_dir / 'metrica_sample_data.zip'
    repo_root = extract_dir / 'sample-data-master'
    final_data_dir = extract_dir / 'data'

    download_archive(args.archive_url, archive_path, args.force, args.prefer_wget, args.timeout, args.retries, args.user_agent)

    if args.force and repo_root.exists():
        shutil.rmtree(repo_root)
    if args.force and final_data_dir.exists():
        shutil.rmtree(final_data_dir)

    if not repo_root.exists():
        print(f'[extract] {archive_path} -> {extract_dir}')
        with zipfile.ZipFile(archive_path, 'r') as zf:
            zf.extractall(extract_dir)
    else:
        print(f'[skip] extracted repo exists: {repo_root}')

    source_data_dir = repo_root / 'data'
    if not source_data_dir.exists():
        raise SystemExit(f'Could not find extracted data directory: {source_data_dir}')
    if final_data_dir.exists():
        shutil.rmtree(final_data_dir)
    shutil.copytree(source_data_dir, final_data_dir)
    print(f'[ready] data root: {final_data_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
