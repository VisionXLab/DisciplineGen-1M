#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nutrition_utils import normalize_text
from parse_fooddata_central import (
    build_record,
    food_category_text,
    iter_food_dicts,
    iter_json_files,
    load_json,
    load_selection_overrides,
    manual_override_matches,
    match_score,
)


def default_food_list_path() -> str:
    candidate = Path(__file__).with_name("sports_nutrition_food_list.txt")
    return candidate.as_posix() if candidate.exists() else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a unified food_assets.json from a standard food list and USDA FoodData Central raw JSON.")
    parser.add_argument("--input", nargs="+", required=True, help="USDA extracted JSON file(s) or directories.")
    parser.add_argument("--output-json", required=True, help="Output JSON array path.")
    parser.add_argument("--food-list", default=default_food_list_path(), help="Food list TXT or JSON. Defaults to bundled sports_nutrition_food_list.txt.")
    parser.add_argument("--selection-json", default="", help="Optional manual USDA selection mapping query -> {fdc_id, description}.")
    parser.add_argument("--output-unmatched", default="", help="Optional path to write unmatched food specs as JSON.")
    parser.add_argument("--max-foods", type=int, default=0, help="0 means no limit.")
    return parser.parse_args()


def slugify(text: str) -> str:
    normalized = normalize_text(text)
    return normalized.replace(" ", "_")


def title_case_name(text: str) -> str:
    return " ".join(part.capitalize() for part in normalize_text(text).split())


def unique_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        normalized = normalize_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(value.strip())
    return out


def parse_food_list_line(line: str) -> tuple[str, str]:
    text = line.strip()
    if not text or text.startswith("#"):
        return "", ""
    if "\t" in text:
        parts = [part.strip() for part in text.split("\t")]
        food_name = parts[0] if parts else ""
        zh_name = parts[1] if len(parts) > 1 else ""
        return food_name, zh_name
    if "|" in text:
        parts = [part.strip() for part in text.split("|")]
        food_name = parts[0] if parts else ""
        zh_name = parts[1] if len(parts) > 1 else ""
        return food_name, zh_name
    return text, ""


def load_food_specs(path_str: str) -> list[dict[str, Any]]:
    path = Path(path_str)
    if not path.exists():
        raise SystemExit(f"Food list file not found: {path}")

    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise SystemExit("Food list JSON must be an array.")
        specs: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, str):
                food_name = item.strip()
                if not food_name:
                    continue
                specs.append(
                    {
                        "food_id": slugify(food_name),
                        "food_name": food_name,
                        "display_name": title_case_name(food_name),
                        "display_name_zh": "",
                        "aliases": [],
                    }
                )
                continue
            if not isinstance(item, dict):
                continue
            food_name = str(item.get("food_name", "")).strip()
            if not food_name:
                continue
            aliases = item.get("aliases", [])
            if not isinstance(aliases, list):
                aliases = []
            specs.append(
                {
                    "food_id": str(item.get("food_id", "")).strip() or slugify(food_name),
                    "food_name": food_name,
                    "display_name": str(item.get("display_name", "")).strip() or title_case_name(food_name),
                    "display_name_zh": str(item.get("display_name_zh", "")).strip(),
                    "aliases": unique_list([str(alias) for alias in aliases]),
                }
            )
        return specs

    specs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        food_name, zh_name = parse_food_list_line(line)
        if not food_name:
            continue
        specs.append(
            {
                "food_id": slugify(food_name),
                "food_name": food_name,
                "display_name": title_case_name(food_name),
                "display_name_zh": zh_name,
                "aliases": [],
            }
        )
    return specs


def best_alias_score(raw_name: str, raw_category: str, spec: dict[str, Any]) -> tuple[tuple[int, int, int, int, int, int], str] | None:
    best: tuple[tuple[int, int, int, int, int, int], str] | None = None
    for alias_index, query in enumerate([spec["food_name"], *spec.get("aliases", [])]):
        score = match_score(raw_name, query, raw_category)
        if score is None:
            continue
        extended = (alias_index, *score)
        if best is None or extended < best[0]:
            best = (extended, query)
    return best


def build_asset_record(spec: dict[str, Any], usda_record: dict[str, Any] | None) -> dict[str, Any]:
    if usda_record is None:
        return {
            "food_id": spec["food_id"],
            "food_name": spec["food_name"],
            "display_name": spec["display_name"],
            "display_name_zh": spec["display_name_zh"] or None,
            "fdc_id": None,
            "usda_description": None,
            "data_type": None,
            "source_dataset": None,
            "food_category": None,
            "energy_kcal": None,
            "protein_g": None,
            "carb_g": None,
            "fat_g": None,
            "fiber_g": None,
            "sugar_g": None,
            "gi_value": None,
            "gi_level": "unknown",
            "gi_source": None,
            "primary_macro_category": None,
            "protein_source": None,
            "meta": {
                "usda_match_status": "unmatched",
                "gi_status": "pending_manual",
            },
        }

    return {
        "food_id": spec["food_id"],
        "food_name": spec["food_name"],
        "display_name": spec["display_name"],
        "display_name_zh": spec["display_name_zh"] or None,
        "fdc_id": usda_record.get("fdc_id") or None,
        "usda_description": usda_record.get("food_name") or None,
        "data_type": usda_record.get("data_type") or None,
        "source_dataset": usda_record.get("source_dataset") or None,
        "food_category": usda_record.get("food_category") or None,
        "energy_kcal": usda_record.get("energy_kcal"),
        "protein_g": usda_record.get("protein_g"),
        "carb_g": usda_record.get("carb_g"),
        "fat_g": usda_record.get("fat_g"),
        "fiber_g": usda_record.get("fiber_g"),
        "sugar_g": usda_record.get("sugar_g"),
        "gi_value": None,
        "gi_level": "unknown",
        "gi_source": None,
        "primary_macro_category": usda_record.get("primary_macro_category") or None,
        "protein_source": usda_record.get("protein_source") or None,
        "meta": {
            "usda_match_status": "matched_manual" if usda_record.get("meta", {}).get("matched_manual") else "matched_auto",
            "usda_match_query": spec["food_name"],
            "usda_matched_alias": usda_record.get("meta", {}).get("matched_alias") or None,
            "usda_publication_date": usda_record.get("meta", {}).get("publication_date") or None,
            "gi_status": "pending_manual",
        },
    }


def main() -> int:
    args = parse_args()
    food_specs = load_food_specs(args.food_list)
    if args.max_foods > 0:
        food_specs = food_specs[: args.max_foods]
    if not food_specs:
        raise SystemExit("No food specs were loaded from --food-list.")

    selection_overrides = load_selection_overrides(args.selection_json)
    json_files = list(iter_json_files(args.input))
    if not json_files:
        raise SystemExit("No JSON files were found under --input.")

    best_by_food_id: dict[str, tuple[tuple[int, int, int, int, int, int], dict[str, Any]]] = {}
    normalized_manual_queries = {normalize_text(key) for key in selection_overrides}

    for file_index, json_path in enumerate(json_files, start=1):
        print(f"[{file_index}/{len(json_files)}] scanning {json_path}")
        payload = load_json(json_path)
        source_dataset = json_path.parent.name or json_path.stem
        for food in iter_food_dicts(payload):
            raw_name = str(food.get("description") or food.get("lowercaseDescription") or food.get("foodDescription") or "").strip()
            if not raw_name:
                continue
            raw_category = food_category_text(food)
            for spec in food_specs:
                normalized_query = normalize_text(spec["food_name"])
                matched_manual = normalized_query in normalized_manual_queries
                if not manual_override_matches(food, spec["food_name"], selection_overrides):
                    continue

                if matched_manual:
                    score = (-1, -1, -1, -1, -1, -1)
                    matched_alias = spec["food_name"]
                else:
                    scored_alias = best_alias_score(raw_name, raw_category, spec)
                    if scored_alias is None:
                        continue
                    score, matched_alias = scored_alias

                record = build_record(food, source_dataset, [], matched_query=spec["food_name"])
                if record is None:
                    continue
                meta = dict(record.get("meta", {}))
                meta["matched_alias"] = matched_alias
                meta["matched_manual"] = matched_manual
                record["meta"] = meta
                current = best_by_food_id.get(spec["food_id"])
                if current is None or score < current[0]:
                    best_by_food_id[spec["food_id"]] = (score, record)

    assets: list[dict[str, Any]] = []
    unmatched_specs: list[dict[str, Any]] = []
    for spec in food_specs:
        matched = best_by_food_id.get(spec["food_id"])
        asset = build_asset_record(spec, matched[1] if matched else None)
        assets.append(asset)
        if matched is None:
            unmatched_specs.append(spec)
            print(f"[miss] no USDA record matched food: {spec['food_name']}")

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(assets)} food assets to {output_path}")

    if args.output_unmatched:
        unmatched_path = Path(args.output_unmatched)
        unmatched_path.parent.mkdir(parents=True, exist_ok=True)
        unmatched_path.write_text(json.dumps(unmatched_specs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {len(unmatched_specs)} unmatched food specs to {unmatched_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
