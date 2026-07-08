#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


SUPPORTED_EXTS = {'.png', '.webp', '.tif', '.tiff'}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Apply local food cutout images into food_assets JSON by Chinese name filename matching.')
    parser.add_argument('--assets-json', required=True)
    parser.add_argument('--cutouts-dir', required=True)
    parser.add_argument('--output-json', default='')
    parser.add_argument('--default-cutout-source', default='local_cutout')
    parser.add_argument('--missing-json', default='')
    return parser.parse_args()


def build_image_index(cutouts_dir: Path) -> dict[str, Path]:
    files = [p for p in cutouts_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]

    def priority(p: Path) -> tuple[int, str]:
        ext_rank = 0 if p.suffix.lower() == '.png' else 1
        return (ext_rank, p.name)

    grouped: dict[str, list[Path]] = {}
    for p in files:
        grouped.setdefault(p.stem.strip(), []).append(p)

    index: dict[str, Path] = {}
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
    cutouts_dir = Path(args.cutouts_dir)

    if not assets_path.exists():
        raise SystemExit(f'assets json not found: {assets_path}')
    if not cutouts_dir.exists() or not cutouts_dir.is_dir():
        raise SystemExit(f'cutouts dir not found: {cutouts_dir}')

    assets = json.loads(assets_path.read_text(encoding='utf-8'))
    if not isinstance(assets, list):
        raise SystemExit('assets json must be an array')

    image_index = build_image_index(cutouts_dir)
    repo_root = Path.cwd()
    matched = 0
    missing: list[dict[str, str]] = []

    for item in assets:
        if not isinstance(item, dict):
            continue
        zh_name = str(item.get('display_name_zh') or '').strip()
        meta = item.get('meta')
        if not isinstance(meta, dict):
            meta = {}
            item['meta'] = meta

        if not zh_name:
            meta['cutout_status'] = 'missing_display_name_zh'
            missing.append({'food_name': str(item.get('food_name', '')), 'reason': 'empty_display_name_zh'})
            continue

        cutout_path = image_index.get(zh_name)
        if cutout_path is None:
            meta['cutout_status'] = 'cutout_not_found'
            missing.append({'food_name': str(item.get('food_name', '')), 'display_name_zh': zh_name, 'reason': 'cutout_not_found'})
            continue

        item['cutout_image_path'] = to_repo_relative(cutout_path, repo_root)
        item['cutout_source'] = args.default_cutout_source
        meta['cutout_status'] = 'matched'
        matched += 1

    output_path = Path(args.output_json) if args.output_json else assets_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'assets_count={len(assets)}')
    print(f'cutouts_indexed={len(image_index)}')
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
