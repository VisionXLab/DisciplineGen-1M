#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Apply local food images into food_assets JSON by Chinese name filename matching.')
    parser.add_argument('--assets-json', required=True)
    parser.add_argument('--images-dir', required=True)
    parser.add_argument('--output-json', default='')
    parser.add_argument('--default-image-source', default='local_manual')
    parser.add_argument('--missing-json', default='')
    return parser.parse_args()


def build_image_index(images_dir: Path) -> dict[str, Path]:
    supported_exts = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
    files = [p for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() in supported_exts]

    def priority(p: Path) -> tuple[int, str]:
        ext = p.suffix.lower()
        rank = 0 if ext == '.png' else 1
        return (rank, p.name)

    index: dict[str, Path] = {}
    grouped: dict[str, list[Path]] = {}
    for p in files:
        grouped.setdefault(p.stem.strip(), []).append(p)
    for stem, group in grouped.items():
        group.sort(key=priority)
        index[stem] = group[0]
    return index


def to_repo_relative(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def main() -> int:
    args = parse_args()
    assets_path = Path(args.assets_json)
    images_dir = Path(args.images_dir)

    if not assets_path.exists():
        raise SystemExit(f'assets json not found: {assets_path}')
    if not images_dir.exists() or not images_dir.is_dir():
        raise SystemExit(f'images dir not found: {images_dir}')

    assets = json.loads(assets_path.read_text(encoding='utf-8'))
    image_index = build_image_index(images_dir)

    repo_root = Path.cwd()
    matched = 0
    missing: list[dict[str, str]] = []

    for item in assets:
        zh_name = str(item.get('display_name_zh') or '').strip()
        if not zh_name:
            missing.append({'food_name': str(item.get('food_name', '')), 'reason': 'empty_display_name_zh'})
            continue

        image_path = image_index.get(zh_name)
        if image_path is None:
            missing.append({'food_name': str(item.get('food_name', '')), 'display_name_zh': zh_name, 'reason': 'image_not_found'})
            continue

        item['local_image_path'] = to_repo_relative(image_path, repo_root)
        if not item.get('image_source'):
            item['image_source'] = args.default_image_source
        if not item.get('image_title'):
            item['image_title'] = image_path.name
        matched += 1

    output_path = Path(args.output_json) if args.output_json else assets_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'assets_count={len(assets)}')
    print(f'images_indexed={len(image_index)}')
    print(f'matched={matched}')
    print(f'missing={len(missing)}')
    print(f'output={output_path}')

    if args.missing_json:
        missing_path = Path(args.missing_json)
        missing_path.parent.mkdir(parents=True, exist_ok=True)
        missing_path.write_text(json.dumps(missing, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'missing_json={missing_path}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
