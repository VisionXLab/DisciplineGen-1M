#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from nutrition_utils import gi_level_from_value, normalize_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Apply GI reference CSV into food_assets JSON.')
    parser.add_argument('--assets-json', required=True)
    parser.add_argument('--gi-csv', required=True)
    parser.add_argument('--output-json', default='')
    parser.add_argument('--default-source', default='gluok.com')
    return parser.parse_args()


def safe_float(value: str) -> float | None:
    text = (value or '').strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_gi_map(path: Path, default_source: str) -> dict[str, dict[str, str | float | None]]:
    out: dict[str, dict[str, str | float | None]] = {}
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            food_name = normalize_text(str(row.get('food_name', '')))
            if not food_name:
                continue
            gi_value = safe_float(str(row.get('gi_value', '')))
            if gi_value is None:
                continue
            source = str(row.get('source', '')).strip() or default_source
            source_note = str(row.get('source_note', '')).strip()
            out[food_name] = {
                'gi_value': gi_value,
                'source': source,
                'source_note': source_note,
            }
    return out


def parse_food_name(raw_name: str) -> tuple[str, str]:
    text = (raw_name or '').strip()
    if not text:
        return '', ''
    if '\t' in text:
        parts = [part.strip() for part in text.split('\t')]
        en_name = parts[0] if parts else ''
        zh_name = parts[1] if len(parts) > 1 else ''
        return en_name, zh_name
    if '|' in text:
        parts = [part.strip() for part in text.split('|')]
        en_name = parts[0] if parts else ''
        zh_name = parts[1] if len(parts) > 1 else ''
        return en_name, zh_name
    return text, ''


def main() -> int:
    args = parse_args()
    assets_path = Path(args.assets_json)
    gi_path = Path(args.gi_csv)
    if not assets_path.exists():
        raise SystemExit(f'assets json not found: {assets_path}')
    if not gi_path.exists():
        raise SystemExit(f'gi csv not found: {gi_path}')

    assets = json.loads(assets_path.read_text(encoding='utf-8'))
    gi_map = load_gi_map(gi_path, args.default_source)

    updated = 0
    normalized_names = 0
    for item in assets:
        raw_food_name = str(item.get('food_name', ''))
        en_food_name, zh_food_name = parse_food_name(raw_food_name)
        if en_food_name and en_food_name != raw_food_name:
            item['food_name'] = en_food_name
            if zh_food_name and not item.get('display_name_zh'):
                item['display_name_zh'] = zh_food_name
            normalized_names += 1

        food_name = normalize_text(en_food_name or raw_food_name)
        gi = gi_map.get(food_name)
        if not gi:
            continue

        gi_value = float(gi['gi_value'])
        item['gi_value'] = gi_value
        item['gi_level'] = gi_level_from_value(gi_value)
        item['gi_source'] = str(gi['source'])

        meta = item.get('meta', {})
        if not isinstance(meta, dict):
            meta = {}
        meta['gi_status'] = 'measured'
        if gi.get('source_note'):
            meta['gi_source_note'] = gi.get('source_note')
        item['meta'] = meta
        updated += 1

    output_path = Path(args.output_json) if args.output_json else assets_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'GI references loaded: {len(gi_map)}')
    print(f'Assets normalized (food_name split): {normalized_names}')
    print(f'Assets updated with GI: {updated}')
    print(f'Output written to: {output_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
