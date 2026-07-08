#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DROP_KEYS_ALWAYS = {
    'image_path',
    'image_url',
    'image_page_url',
    'image_license',
    'image_attribution',
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Prune redundant fields in food_assets.json.')
    parser.add_argument('--assets-json', required=True)
    parser.add_argument('--output-json', default='')
    return parser.parse_args()


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ''
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def normalize_name_field(value: Any) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    if '	' in text:
        return text.split('	', 1)[0].strip()
    if '|' in text:
        return text.split('|', 1)[0].strip()
    return text


def prune_item(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)

    for key in list(DROP_KEYS_ALWAYS):
        out.pop(key, None)

    if is_empty(out.get('aliases')):
        out.pop('aliases', None)

    if is_empty(out.get('display_name')):
        out.pop('display_name', None)

    if is_empty(out.get('image_source')):
        out.pop('image_source', None)
    if is_empty(out.get('image_title')):
        out.pop('image_title', None)
    if is_empty(out.get('local_image_path')):
        out.pop('local_image_path', None)
    if is_empty(out.get('cutout_image_path')):
        out.pop('cutout_image_path', None)
    if is_empty(out.get('cutout_source')):
        out.pop('cutout_source', None)

    meta = out.get('meta')
    if isinstance(meta, dict):
        if 'usda_match_query' in meta:
            normalized_query = normalize_name_field(meta.get('usda_match_query'))
            if normalized_query:
                meta['usda_match_query'] = normalized_query
            else:
                meta.pop('usda_match_query', None)

        if 'usda_matched_alias' in meta:
            normalized_alias = normalize_name_field(meta.get('usda_matched_alias'))
            if normalized_alias:
                meta['usda_matched_alias'] = normalized_alias
            else:
                meta.pop('usda_matched_alias', None)

        if meta.get('usda_matched_alias') == out.get('food_name'):
            meta.pop('usda_matched_alias', None)
        if is_empty(meta.get('gi_source_note')):
            meta.pop('gi_source_note', None)
        if len(meta) == 0:
            out.pop('meta', None)
        else:
            out['meta'] = meta

    return out


def main() -> int:
    args = parse_args()
    assets_path = Path(args.assets_json)
    if not assets_path.exists():
        raise SystemExit(f'assets json not found: {assets_path}')

    items = json.loads(assets_path.read_text(encoding='utf-8'))
    if not isinstance(items, list):
        raise SystemExit('assets json must be an array')

    pruned = [prune_item(item) if isinstance(item, dict) else item for item in items]

    output_path = Path(args.output_json) if args.output_json else assets_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(pruned, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'assets_count={len(pruned)}')
    print(f'output={output_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
