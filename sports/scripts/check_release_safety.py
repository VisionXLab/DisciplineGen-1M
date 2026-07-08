#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:OPENSSH|RSA|DSA|EC|PRIVATE) KEY-----"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?key|secret|password|passwd|pwd)\b\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"(?i)\b(auth[_-]?token|bearer[_-]?token|refresh[_-]?token|access[_-]?token)\b\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"(?i)\bauthorization\s*[:=]\s*['\"]?bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}\b"),
]

ABS_PATH_PATTERNS = [
    re.compile(r"/mnt/[^ \t\r\n\"')]+"),
    re.compile(r"/home/[^ \t\r\n\"')]+"),
    re.compile(r"/root/[^ \t\r\n\"')]+"),
    re.compile(r"\b[A-Za-z]:\\(?:Users|study|workspace|data|mnt|root|home)[^ \t\r\n\"')]*"),
]

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "raw_data",
    "outputs",
    "test_output",
    "tmp",
    "board_games",
    "tmp_xiangqi_setup_src",
    "tmp_xiangqi_setup_inspect",
    "tmp_xiangqi_assets_prepared",
    "tmp_xiangqi_assets_prepared_v2",
    "tmp_xiangqi_assets_prepared_v3",
    "ailab_ssh_key",
    "board_game_dataset_construction",
    "sports",
    "sports_anatomy",
}

SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".pdf",
    ".pptx",
    ".zip",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".zst",
    ".whl",
    ".pyc",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan repository files for common release-safety issues.")
    parser.add_argument("root", nargs="?", default=".", help="Repository root to scan.")
    parser.add_argument("--allow-absolute-paths", action="store_true", help="Do not fail on absolute local path examples.")
    return parser.parse_args()


def should_skip(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    if any(part in SKIP_DIRS for part in rel_parts[:-1]):
        return True
    return path.suffix.lower() in SKIP_SUFFIXES


def scan_file(path: Path, root: Path, allow_absolute_paths: bool) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            return [f"{path.relative_to(root)}: unable to read file: {exc}"]
    except OSError as exc:
        return [f"{path.relative_to(root)}: unable to read file: {exc}"]

    issues: list[str] = []
    rel = path.relative_to(root)
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            issues.append(f"{rel}: possible secret or private credential")
            break
    if not allow_absolute_paths and path.name != "check_release_safety.py":
        for pattern in ABS_PATH_PATTERNS:
            match = pattern.search(text)
            if match:
                issues.append(f"{rel}: local absolute path example: {match.group(0)}")
                break
    return issues


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Root does not exist: {root}")

    issues: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or should_skip(path, root):
            continue
        issues.extend(scan_file(path, root, args.allow_absolute_paths))

    if issues:
        print("Release safety check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Release safety check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
