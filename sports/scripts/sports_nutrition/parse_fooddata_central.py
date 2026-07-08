#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Iterable

from nutrition_utils import (
    gi_level_from_value,
    infer_gi_value,
    infer_primary_macro_category,
    infer_protein_source,
    normalize_text,
    safe_float,
)


NUTRIENT_IDS = {
    "1008": "energy_kcal",
    "1003": "protein_g",
    "1005": "carb_g",
    "1004": "fat_g",
    "1079": "fiber_g",
    "2000": "sugar_g",
    "208": "energy_kcal",
    "203": "protein_g",
    "205": "carb_g",
    "204": "fat_g",
    "291": "fiber_g",
    "269": "sugar_g",
}
NUTRIENT_NAMES = {
    "energy": "energy_kcal",
    "energy kcal": "energy_kcal",
    "protein": "protein_g",
    "carbohydrate by difference": "carb_g",
    "carbohydrate, by difference": "carb_g",
    "carbohydrate": "carb_g",
    "total lipid fat": "fat_g",
    "total lipid (fat)": "fat_g",
    "fat": "fat_g",
    "fiber total dietary": "fiber_g",
    "fiber, total dietary": "fiber_g",
    "dietary fiber": "fiber_g",
    "sugars total including nlea": "sugar_g",
    "sugars, total including nlea": "sugar_g",
    "total sugars": "sugar_g",
}
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
DESCRIPTOR_TOKENS = {
    "raw",
    "cooked",
    "dry",
    "fresh",
    "frozen",
    "prepared",
    "boiled",
    "baked",
    "fried",
    "roasted",
    "steamed",
    "grilled",
    "broiled",
    "nfs",
    "ns",
    "unenriched",
    "enriched",
    "plain",
}
DISH_TOKENS = {
    "pie",
    "sandwich",
    "sauce",
    "soup",
    "salad",
    "casserole",
    "stew",
    "pizza",
    "burger",
    "burrito",
    "taco",
    "lasagna",
    "omelet",
    "omelette",
    "roll",
    "flavored",
    "mixed",
    "squash",
}
CONNECTOR_TOKENS = {"and", "with", "in", "on", "from", "style"}
QUERY_RULES = {
    "white rice": {
        "require_all": ["white", "rice"],
        "forbid": ["flour", "bean", "beans", "mix", "mixed"],
        "category_allow_any": ["rice"],
        "category_forbid": ["pasta"],
    },
    "brown rice": {
        "require_all": ["brown", "rice"],
        "forbid": ["flour", "bean", "beans", "mix", "mixed"],
        "category_allow_any": ["rice"],
        "category_forbid": ["pasta"],
    },
    "oats": {
        "require_any": ["oats", "oat"],
        "forbid": ["roll", "pie", "cookie", "bread"],
        "category_forbid": ["rolls", "buns", "breads"],
    },
    "oatmeal": {
        "require_any": ["oatmeal", "oats", "oat"],
        "forbid": ["roll", "pie", "cookie", "bread", "cracker"],
        "category_forbid": ["rolls", "buns", "breads", "crackers"],
    },
    "wheat bread": {
        "require_all": ["bread", "wheat"],
        "forbid": ["sandwich"],
        "category_allow_any": ["bread"],
        "category_forbid": ["sandwich"],
    },
    "white bread": {
        "require_all": ["bread", "white"],
        "forbid": ["sandwich"],
        "category_allow_any": ["bread"],
        "category_forbid": ["sandwich"],
    },
    "bagel": {"require_all": ["bagel"], "category_allow_any": ["bagel"], "category_forbid": []},
    "pasta": {
        "require_any": ["pasta", "macaroni", "noodle"],
        "forbid": ["flavored", "mixed", "squash", "sauce", "salad"],
        "category_allow_any": ["pasta", "macaroni", "noodle"],
        "category_forbid": ["mixed dishes", "vegetables"],
    },
    "spaghetti": {
        "require_all": ["spaghetti"],
        "forbid": ["squash", "sauce", "meatballs", "dinner", "meal", "frozen"],
        "category_allow_any": ["pasta", "noodle"],
        "category_forbid": ["vegetables", "sauce", "mixed dishes"],
    },
    "potato": {
        "require_all": ["potato"],
        "forbid": ["sweet", "pie", "chips", "salad", "patty", "tots", "fries", "fried"],
        "category_forbid": ["chips", "snacks", "salad", "fried", "fries"],
    },
    "sweet potato": {
        "require_all": ["sweet", "potato"],
        "forbid": ["pie", "tots", "fried", "fries"],
        "category_forbid": ["pie", "fried", "fries"],
    },
    "banana": {"require_all": ["banana"], "forbid": ["bread", "cake", "chip", "split", "pudding", "muffin"]},
    "apple": {"require_all": ["apple"], "forbid": ["pie", "juice", "sauce", "cider", "crisp", "cake"], "category_forbid": ["juice", "cakes", "pies"]},
    "orange": {"require_all": ["orange"], "forbid": ["juice", "drink", "chicken", "soda"], "category_forbid": ["sauce", "mixtures", "juice"]},
    "corn flakes": {"require_all": ["corn", "flakes"]},
    "rice cake": {"require_all": ["rice", "cake"]},
    "chicken breast": {"require_all": ["chicken", "breast"], "forbid": ["sandwich", "salad"]},
    "beef steak": {"require_any": ["steak", "beef"], "forbid": ["sandwich", "sauce"]},
    "salmon": {"require_all": ["salmon"], "forbid": ["lomi", "salad", "spread"], "category_allow_any": ["fish", "seafood"], "category_forbid": ["mixed dishes"]},
    "tuna": {"require_all": ["tuna"], "forbid": ["salad", "sandwich"]},
    "egg": {"require_all": ["egg"], "forbid": ["sandwich", "creamed", "salad"], "category_forbid": ["omelets"]},
    "milk": {"require_all": ["milk"], "forbid": ["shake", "chocolate"], "category_allow_any": ["milk"]},
    "yogurt": {"require_any": ["yogurt", "yoghurt"], "forbid": ["frozen", "tube"], "category_allow_any": ["yogurt"]},
    "cottage cheese": {"require_all": ["cottage", "cheese"]},
    "tofu": {"require_all": ["tofu"], "forbid": ["soup"], "category_forbid": ["soups"]},
    "whey protein": {"require_any": ["whey", "protein"], "forbid": ["bar", "drink"]},
    "lentils": {"require_any": ["lentil", "lentils"], "forbid": ["soup", "salad"]},
    "chickpeas": {"require_any": ["chickpea", "chickpeas", "garbanzo"], "forbid": ["salad"]},
    "black beans": {"require_all": ["black", "beans"], "forbid": ["rice", "soup"]},
    "olive oil": {"require_all": ["olive", "oil"]},
    "almonds": {"require_any": ["almond", "almonds"], "forbid": ["milk", "butter"]},
    "peanut butter": {"require_all": ["peanut", "butter"]},
    "avocado": {"require_all": ["avocado"], "forbid": ["oil", "dressing", "spread"]},
    "mixed nuts": {"require_all": ["mixed", "nuts"]},
    "broccoli": {"require_all": ["broccoli"]},
    "spinach": {"require_all": ["spinach"]},
    "carrot": {"require_all": ["carrot"], "forbid": ["cake", "juice", "muffin"]},
    "tomato": {"require_all": ["tomato"], "forbid": ["sauce", "juice"]},
    "berries": {"require_any": ["berries", "berry"], "forbid": ["jam", "dried"]},
    "shrimp": {"require_all": ["shrimp"], "forbid": ["toast", "salad"], "category_allow_any": ["fish", "seafood"], "category_forbid": ["mixed dishes"]},
    "cod": {"require_all": ["cod"], "forbid": ["cape"], "category_allow_any": ["fish"], "category_forbid": ["liquor", "cocktails"]},
    "cheese": {"require_all": ["cheese"], "forbid": ["dip", "sauce"], "category_forbid": ["dips", "sauces"]},
    "cucumber": {"require_all": ["cucumber"], "forbid": ["pickle", "pickles"]},
    "mushrooms": {"require_any": ["mushroom", "mushrooms"], "forbid": ["stuffed"]},
    "onion": {"require_all": ["onion"], "forbid": ["bread", "dip"]},
    "cabbage": {"require_all": ["cabbage"], "forbid": ["pickled", "slaw"]},
    "cauliflower": {"require_all": ["cauliflower"], "forbid": ["pickled"]},
    "green beans": {"require_all": ["green", "beans"], "forbid": ["pickled"]},
    "zucchini": {"require_all": ["zucchini"], "forbid": ["bread", "muffin"]},
    "pumpkin": {"require_all": ["pumpkin"], "forbid": ["bread", "pie", "muffin"]},
    "beets": {"require_any": ["beet", "beets"], "forbid": ["pickled"]},
    "watermelon": {"require_all": ["watermelon"], "forbid": ["juice"]},
    "blueberries": {"require_any": ["blueberry", "blueberries"], "forbid": ["dried", "jam"]},
    "strawberries": {"require_any": ["strawberry", "strawberries"], "forbid": ["canned", "jam"]},
    "pineapple": {"require_all": ["pineapple"], "forbid": ["dried", "juice", "canned"]},
    "granola": {"require_all": ["granola"], "forbid": ["cookie", "bar"]},
    "pancakes": {"require_all": ["pancakes"], "forbid": ["fruit"]},
    "corn": {"require_all": ["corn"], "forbid": ["dog"]},
    "noodles": {"require_any": ["noodles", "noodle"], "forbid": ["chow", "mein"], "category_allow_any": ["pasta", "noodle"], "category_forbid": ["crackers", "mixed dishes"]},
    "pear": {"require_all": ["pear"], "forbid": ["dried", "canned"]},
    "peach": {"require_all": ["peach"], "forbid": ["crisp", "pie", "cake"]},
    "mango": {"require_all": ["mango"], "forbid": ["dried", "juice"]},
    "grapefruit": {"require_all": ["grapefruit"], "forbid": ["canned", "juice"]},
    "lemon": {"require_all": ["lemon"], "forbid": ["cookie", "bar", "pie"]},
    "lime": {"require_all": ["lime"], "forbid": ["souffle", "pie", "drink"]},
}


def default_food_list_path() -> str:
    candidate = Path(__file__).with_name("sports_nutrition_food_list.txt")
    return candidate.as_posix() if candidate.exists() else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse USDA FoodData Central JSON into canonical JSONL for sports nutrition dataset construction.")
    parser.add_argument("--input", nargs="+", required=True, help="Input USDA extracted JSON file(s) or directories.")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--food-list", default=default_food_list_path(), help="Optional newline-delimited food query list. Defaults to bundled sports_nutrition_food_list.txt.")
    parser.add_argument("--gi-csv", default="", help="Optional CSV with columns match_key,gi_value,source.")
    parser.add_argument("--selection-json", default="", help="Optional manual selection JSON mapping query -> {fdc_id}.")
    parser.add_argument("--max-foods", type=int, default=0, help="0 means no limit.")
    return parser.parse_args()


def parse_food_list_line(line: str) -> tuple[str, str]:
    text = line.strip()
    if not text or text.startswith("#"):
        return "", ""
    if "	" in text:
        parts = [part.strip() for part in text.split("	")]
        food_name = parts[0] if parts else ""
        zh_name = parts[1] if len(parts) > 1 else ""
        return food_name, zh_name
    if "|" in text:
        parts = [part.strip() for part in text.split("|")]
        food_name = parts[0] if parts else ""
        zh_name = parts[1] if len(parts) > 1 else ""
        return food_name, zh_name
    return text, ""


def load_queries(path_str: str) -> list[str]:
    if not path_str:
        return []
    path = Path(path_str)
    if not path.exists():
        raise SystemExit(f"Food list file not found: {path}")
    queries: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        food_name, _ = parse_food_list_line(line)
        if food_name:
            queries.append(food_name)
    return queries


def load_gi_overrides(path_str: str) -> list[tuple[str, float, str]]:
    if not path_str:
        return []
    path = Path(path_str)
    if not path.exists():
        raise SystemExit(f"GI CSV not found: {path}")
    overrides: list[tuple[str, float, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            match_key = normalize_text(str(row.get("match_key", "")))
            if not match_key:
                continue
            gi_value = safe_float(row.get("gi_value"))
            source = str(row.get("source", "csv_override")).strip() or "csv_override"
            overrides.append((match_key, gi_value, source))
    return overrides



def load_selection_overrides(path_str: str) -> dict[str, dict[str, str]]:
    if not path_str:
        return {}
    path = Path(path_str)
    if not path.exists():
        raise SystemExit(f"Selection JSON not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Selection JSON must be an object mapping query -> rule.")
    out: dict[str, dict[str, str]] = {}
    for query, rule in data.items():
        if not isinstance(rule, dict):
            continue
        normalized_query = normalize_text(str(query))
        if not normalized_query:
            continue
        out[normalized_query] = {
            "fdc_id": str(rule.get("fdc_id", "")).strip(),
            "description": str(rule.get("description", "")).strip(),
        }
    return out
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


def nutrient_target(entry: dict[str, Any]) -> str:
    nutrient = entry.get("nutrient") if isinstance(entry.get("nutrient"), dict) else {}
    nutrient_id = str(
        entry.get("nutrientId")
        or nutrient.get("id")
        or nutrient.get("nutrientId")
        or nutrient.get("number")
        or entry.get("number")
        or ""
    ).strip()
    if nutrient_id in NUTRIENT_IDS:
        return NUTRIENT_IDS[nutrient_id]
    nutrient_name = str(entry.get("nutrientName") or nutrient.get("name") or entry.get("name") or "").lower().strip()
    nutrient_name = nutrient_name.replace("(", " ").replace(")", " ").replace("-", " ")
    nutrient_name = " ".join(nutrient_name.split())
    return NUTRIENT_NAMES.get(nutrient_name, "")


def nutrient_amount(entry: dict[str, Any]) -> float:
    for key in ["amount", "value"]:
        if key in entry:
            return safe_float(entry[key])
    return 0.0


def extract_nutrients(food: dict[str, Any]) -> dict[str, float]:
    values = {
        "energy_kcal": 0.0,
        "protein_g": 0.0,
        "carb_g": 0.0,
        "fat_g": 0.0,
        "fiber_g": 0.0,
        "sugar_g": 0.0,
    }
    for entry in food.get("foodNutrients", []) or []:
        if not isinstance(entry, dict):
            continue
        target = nutrient_target(entry)
        if target:
            values[target] = nutrient_amount(entry)
    return values


def extract_text_field(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in [
            "description",
            "name",
            "wweiaFoodCategoryDescription",
            "foodCategoryDescription",
            "label",
            "text",
        ]:
            text = extract_text_field(value.get(key))
            if text:
                return text
        return ""
    return str(value)


def query_rule_penalty(normalized_name: str, normalized_query: str, normalized_category: str) -> int | None:
    rule = QUERY_RULES.get(normalized_query)
    if not rule:
        return 0
    tokens = set(normalized_name.split())
    require_all = set(rule.get("require_all", []))
    require_any = set(rule.get("require_any", []))
    forbid = set(rule.get("forbid", []))
    category_allow_any = set(rule.get("category_allow_any", []))
    category_forbid = set(rule.get("category_forbid", []))

    if require_all and not require_all.issubset(tokens):
        return None
    if require_any and not (require_any & tokens):
        return None
    if forbid & tokens:
        return None
    if category_allow_any and not any(token in normalized_category for token in category_allow_any):
        return None
    if category_forbid and any(token in normalized_category for token in category_forbid):
        return None
    return 0



def manual_override_matches(food: dict[str, Any], query: str, selection_overrides: dict[str, dict[str, str]]) -> bool:
    rule = selection_overrides.get(normalize_text(query))
    if not rule:
        return True
    food_fdc_id = str(food.get("fdcId", "")).strip()
    food_description = first_non_empty(food.get("description"), food.get("lowercaseDescription"), food.get("foodDescription"))
    if rule.get("fdc_id") and food_fdc_id != rule["fdc_id"]:
        return False
    if rule.get("description") and normalize_text(food_description) != normalize_text(rule["description"]):
        return False
    return True
def match_score(food_name: str, query: str, food_category: str) -> tuple[int, int, int, int, int] | None:
    normalized_name = normalize_text(food_name)
    normalized_query = normalize_text(query)
    normalized_category = normalize_text(food_category)
    if not normalized_name or not normalized_query:
        return None

    rule_penalty = query_rule_penalty(normalized_name, normalized_query, normalized_category)
    if rule_penalty is None:
        return None

    name_tokens = [token for token in normalized_name.split() if token]
    query_tokens = [token for token in normalized_query.split() if token]
    name_set = set(name_tokens)
    query_set = set(query_tokens)
    if not query_tokens:
        return None

    descriptor_penalty = sum(1 for token in name_tokens if token in DESCRIPTOR_TOKENS)
    dish_penalty = sum(1 for token in name_tokens if token in DISH_TOKENS)
    connector_penalty = sum(1 for token in name_tokens if token in CONNECTOR_TOKENS)
    extra_tokens = max(0, len(name_tokens) - len(query_tokens))

    if normalized_name == normalized_query:
        return (0, rule_penalty, 0, 0, len(food_name))
    if query_set == name_set:
        return (1, rule_penalty, descriptor_penalty, 0, len(food_name))
    if query_set.issubset(name_set):
        return (2, rule_penalty + dish_penalty + connector_penalty, descriptor_penalty, extra_tokens, len(food_name))
    if f" {normalized_query} " in f" {normalized_name} ":
        return (3, rule_penalty + dish_penalty + connector_penalty + 1, descriptor_penalty, extra_tokens, len(food_name))

    overlap = len(query_set & name_set)
    if overlap == len(query_set):
        return (4, rule_penalty + dish_penalty + connector_penalty + 2, descriptor_penalty, extra_tokens, len(food_name))
    return None


def first_non_empty(*values: Any) -> str:
    for value in values:
        text = extract_text_field(value)
        if text:
            return text
    return ""


def food_category_text(food: dict[str, Any]) -> str:
    return first_non_empty(food.get("foodCategory"), food.get("wweiaFoodCategory"), food.get("foodClass"))


def resolve_gi(food_name: str, overrides: list[tuple[str, float, str]]) -> tuple[float | None, str]:
    normalized = normalize_text(food_name)
    for match_key, gi_value, source in overrides:
        if match_key and match_key in normalized:
            return gi_value, source
    return infer_gi_value(food_name)


def build_record(food: dict[str, Any], source_dataset: str, gi_overrides: list[tuple[str, float, str]], matched_query: str = "") -> dict[str, Any] | None:
    food_name = first_non_empty(food.get("description"), food.get("lowercaseDescription"), food.get("foodDescription"))
    if not food_name:
        return None
    fdc_id = first_non_empty(food.get("fdcId"), food.get("fdc_id"))
    data_type = first_non_empty(food.get("dataType"), food.get("foodClass"))
    food_category = food_category_text(food)
    nutrient_values = extract_nutrients(food)
    gi_value, gi_source = resolve_gi(food_name, gi_overrides)
    primary_category = infer_primary_macro_category(
        food_name,
        food_category,
        nutrient_values["protein_g"],
        nutrient_values["carb_g"],
        nutrient_values["fat_g"],
        nutrient_values["fiber_g"],
    )
    protein_source = infer_protein_source(food_name, food_category)
    source_id = f"usda_{fdc_id}" if fdc_id else f"usda_{normalize_text(food_name).replace(' ', '_')}"
    return {
        "source_id": source_id,
        "food_name": food_name,
        "fdc_id": fdc_id,
        "data_type": data_type,
        "source_dataset": source_dataset,
        "food_category": food_category,
        "energy_kcal": nutrient_values["energy_kcal"],
        "protein_g": nutrient_values["protein_g"],
        "carb_g": nutrient_values["carb_g"],
        "fat_g": nutrient_values["fat_g"],
        "fiber_g": nutrient_values["fiber_g"],
        "sugar_g": nutrient_values["sugar_g"],
        "primary_macro_category": primary_category,
        "gi_value": gi_value,
        "gi_level": gi_level_from_value(gi_value),
        "gi_source": gi_source,
        "protein_source": protein_source,
        "tags": [primary_category, protein_source],
        "meta": {
            "publication_date": first_non_empty(food.get("publicationDate")),
            "input_food_category": food_category,
            "matched_query": matched_query,
        },
    }


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        key = normalize_text(str(record.get("food_name", "")))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def main() -> int:
    args = parse_args()
    queries = load_queries(args.food_list)
    gi_overrides = load_gi_overrides(args.gi_csv)
    selection_overrides = load_selection_overrides(args.selection_json)
    json_files = list(iter_json_files(args.input))
    if not json_files:
        raise SystemExit("No JSON files were found under --input.")

    all_records: list[dict[str, Any]] = []
    best_by_query: dict[str, tuple[tuple[int, int, int, int, int], dict[str, Any]]] = {}

    for file_index, json_path in enumerate(json_files, start=1):
        print(f"[{file_index}/{len(json_files)}] scanning {json_path}")
        payload = load_json(json_path)
        source_dataset = json_path.parent.name or json_path.stem
        for food in iter_food_dicts(payload):
            if queries:
                raw_name = first_non_empty(food.get("description"), food.get("lowercaseDescription"), food.get("foodDescription"))
                if not raw_name:
                    continue
                raw_category = food_category_text(food)
                for query in queries:
                    if not manual_override_matches(food, query, selection_overrides):
                        continue
                    score = match_score(raw_name, query, raw_category)
                    if score is None:
                        continue
                    record = build_record(food, source_dataset, gi_overrides, matched_query=query)
                    if record is None:
                        continue
                    current = best_by_query.get(query)
                    if current is None or score < current[0]:
                        best_by_query[query] = (score, record)
            else:
                record = build_record(food, source_dataset, gi_overrides)
                if record is not None:
                    all_records.append(record)

    if queries:
        for query in queries:
            if query in best_by_query:
                all_records.append(best_by_query[query][1])
            else:
                print(f"[miss] no USDA record matched query: {query}")

    all_records = dedupe_records(all_records)
    if args.max_foods > 0:
        all_records = all_records[: args.max_foods]

    output_path = Path(args.output_jsonl)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for record in all_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    if not all_records:
        raise SystemExit("No nutrition records were parsed. Check the input JSON and optional food list.")
    print(f"Parsed {len(all_records)} nutrition records to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

