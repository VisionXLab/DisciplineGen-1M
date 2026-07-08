#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

KNOWN_LIST_KEYS = [
    "FoundationFoods",
    "SurveyFoods",
    "BrandedFoods",
    "SRLegacyFoods",
    "foods",
    "Foods",
    "items",
    "Items",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect raw USDA FoodData Central JSON structure for selected fdcIds.")
    parser.add_argument("--input", nargs="+", required=True, help="Input USDA JSON file(s) or directories.")
    parser.add_argument("--fdc-id", nargs="+", required=True, help="One or more target fdcIds.")
    parser.add_argument("--print-full", action="store_true", help="Print the full matched record JSON.")
    parser.add_argument("--nutrient-limit", type=int, default=10, help="How many foodNutrients entries to print when not using --print-full.")
    return parser.parse_args()


def iter_json_files(paths: list[str]) -> Iterable[Path]:
    for raw in paths:
        path = Path(raw)
        if path.is_file() and path.suffix.lower() == ".json":
            yield path
            continue
        if path.is_dir():
            for item in sorted(path.rglob("*.json")):
                yield item
            continue
        raise SystemExit(f"Unsupported input path: {path}")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def is_food_dict(value: Any) -> bool:
    return isinstance(value, dict) and any(key in value for key in ["description", "fdcId", "foodClass", "dataType"])


def iter_food_dicts(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if is_food_dict(item):
                yield item
            else:
                yield from iter_food_dicts(item)
        return
    if isinstance(payload, dict):
        for key in KNOWN_LIST_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    if is_food_dict(item):
                        yield item
                return
        if is_food_dict(payload):
            yield payload
            return
        for value in payload.values():
            yield from iter_food_dicts(value)


def print_summary(record: dict[str, Any], nutrient_limit: int) -> None:
    print(f"fdcId: {record.get('fdcId')}")
    print(f"description: {record.get('description')}")
    print(f"dataType: {record.get('dataType')}")
    print(f"foodClass: {record.get('foodClass')}")
    print("foodCategory:")
    print(json.dumps(record.get("foodCategory"), ensure_ascii=False, indent=2))
    print("wweiaFoodCategory:")
    print(json.dumps(record.get("wweiaFoodCategory"), ensure_ascii=False, indent=2))
    nutrients = record.get("foodNutrients") or []
    print(f"foodNutrients sample (first {min(len(nutrients), nutrient_limit)}):")
    print(json.dumps(nutrients[:nutrient_limit], ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    targets = {str(item) for item in args.fdc_id}
    json_files = list(iter_json_files(args.input))
    if not json_files:
        raise SystemExit("No JSON files were found under --input.")

    found_targets: set[str] = set()
    for index, json_path in enumerate(json_files, start=1):
        print(f"=== [{index}/{len(json_files)}] {json_path} ===")
        payload = load_json(json_path)
        file_hits = 0
        for record in iter_food_dicts(payload):
            fdc_id = str(record.get("fdcId", ""))
            if fdc_id not in targets:
                continue
            file_hits += 1
            found_targets.add(fdc_id)
            print()
            if args.print_full:
                print(json.dumps(record, ensure_ascii=False, indent=2))
            else:
                print_summary(record, args.nutrient_limit)
            print()
        if file_hits == 0:
            print("(no target fdcId found in this file)")

    missing = sorted(targets - found_targets)
    if missing:
        print(f"Missing fdcIds: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
