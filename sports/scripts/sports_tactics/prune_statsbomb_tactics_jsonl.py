#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Prune canonical StatsBomb tactics JSONL to formation-only records and unique formation values.')
    parser.add_argument('--input-jsonl', required=True)
    parser.add_argument('--output-jsonl', required=True)
    parser.add_argument('--keep-task-types', nargs='*', default=['soccer_formation'])
    parser.add_argument('--dedupe-key', default='formation', choices=['formation', 'source_id', 'team_name'])
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def dedupe_value(record: dict, key: str) -> str:
    value = record.get(key)
    if value is None:
        return ''
    return str(value).strip()


def main() -> int:
    args = parse_args()
    records = load_jsonl(Path(args.input_jsonl))
    keep = set(args.keep_task_types)
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []

    for record in records:
        task_type = str(record.get('task_type', ''))
        if task_type not in keep:
            continue
        dedupe = dedupe_value(record, args.dedupe_key)
        if not dedupe:
            continue
        token = (task_type, dedupe)
        if token in seen:
            continue
        seen.add(token)
        out.append(record)

    output_path = Path(args.output_jsonl)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8') as f:
        for record in out:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    print(f'input_records={len(records)}')
    print(f'output_records={len(out)}')
    print(f'dedupe_key={args.dedupe_key}')
    print(f'output={output_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
