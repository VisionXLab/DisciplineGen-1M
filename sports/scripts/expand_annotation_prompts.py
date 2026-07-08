#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable


TemplateFactory = Callable[[dict[str, Any], str], list[str]]


DATASET_PREFIXES: list[tuple[str, str]] = [
    ("chess_opening", "chess_opening"),
    ("chess_legal_moves", "chess_legal_moves"),
    ("chess_bestmove", "chess_bestmove"),
    ("xiangqi_opening", "xiangqi_opening"),
    ("xiangqi_legal_moves", "xiangqi_legal_moves"),
    ("xiangqi_bestmove", "xiangqi_bestmove"),
    ("go_crucial_move", "go_crucial_move"),
    ("sports_nutrition_classify_grouping", "sports_nutrition_classify_grouping"),
    ("sports_nutrition_pie_chart_integration", "sports_nutrition_pie_chart_integration"),
    ("sports_nutrition_pie_chart", "sports_nutrition_pie_chart_integration"),
    ("sports_nutrition_nutrition_pyramid", "sports_nutrition_nutrition_pyramid"),
    ("sports_nutrition_pyramid", "sports_nutrition_nutrition_pyramid"),
    ("sports_nutrition_highlight_high_gi", "sports_nutrition_highlight_high_gi"),
    ("sports_nutrition_high_gi", "sports_nutrition_highlight_high_gi"),
    ("sports_nutrition_highlight_high_protein", "sports_nutrition_highlight_high_protein"),
    ("sports_nutrition_high_protein", "sports_nutrition_highlight_high_protein"),
    ("soccer_formation_dots", "soccer_formation_dots"),
    ("soccer_formation_jerseys", "soccer_formation_jerseys"),
    ("soccer_ball_handler_highlight", "soccer_ball_handler_highlight"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expand prompt styles for existing unified annotation jsonl datasets."
    )
    parser.add_argument(
        "--input-root",
        default="",
        help="Root directory containing dataset annotation subdirectories and optional meta.json.",
    )
    parser.add_argument(
        "--dataset-root",
        action="append",
        default=[],
        help="Specific dataset annotation directory containing one or more .jsonl files. Can be passed multiple times.",
    )
    parser.add_argument(
        "--output-root",
        default="",
        help="Directory to write expanded annotation files and updated meta.json. Defaults to --input-root for in-place output.",
    )
    parser.add_argument(
        "--meta-json",
        default="",
        help="Optional input meta.json. Defaults to <input-root>/meta.json when present.",
    )
    parser.add_argument(
        "--expand-ratio",
        type=float,
        default=0.3,
        help="Fraction of samples to rewrite per dataset. Default: 0.3",
    )
    parser.add_argument(
        "--hash-salt",
        default="prompt_expand_v1",
        help="Salt for deterministic sample selection and template assignment.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing expanded jsonl files.",
    )
    return parser.parse_args()


def stable_hash_int(*parts: Any) -> int:
    payload = "||".join(str(part) for part in parts)
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest(), 16)


def detect_dataset_key(dataset_name: str) -> str | None:
    for prefix, key in DATASET_PREFIXES:
        if dataset_name == prefix or dataset_name.startswith(prefix + "_") or dataset_name.startswith(prefix + "-"):
            return key
    return None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"Non-dict record in {path}:{line_no}")
            records.append(record)
    return records


def dump_jsonl(path: Path, records: list[dict[str, Any]], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")


def discover_dataset_dirs(input_root: Path) -> list[Path]:
    dataset_dirs: list[Path] = []
    for child in sorted(input_root.iterdir()):
        if not child.is_dir():
            continue
        if any(child.glob("*.jsonl")):
            dataset_dirs.append(child)
    return dataset_dirs


def load_meta_map(meta_path: Path | None) -> dict[str, Any]:
    if meta_path is None or not meta_path.exists():
        return {}
    with meta_path.open("r", encoding="utf-8") as handle:
        meta = json.load(handle)
    if not isinstance(meta, dict):
        raise ValueError(f"Meta file must be a dict: {meta_path}")
    return meta


def get_first_human_index(record: dict[str, Any]) -> int | None:
    conversations = record.get("conversations")
    if not isinstance(conversations, list):
        return None
    for idx, message in enumerate(conversations):
        if isinstance(message, dict) and message.get("from") == "human":
            return idx
    return None


def extract_prompt_from_value(value: str) -> tuple[list[str], str]:
    lines = value.splitlines()
    image_lines: list[str] = []
    index = 0
    while index < len(lines) and lines[index].strip() == "<image>":
        image_lines.append("<image>")
        index += 1
    prompt = "\n".join(lines[index:]).strip()
    return image_lines, prompt


def get_current_prompt(record: dict[str, Any]) -> str:
    human_index = get_first_human_index(record)
    if human_index is None:
        return ""
    conversations = record.get("conversations") or []
    value = conversations[human_index].get("value", "")
    if not isinstance(value, str):
        return ""
    _, prompt = extract_prompt_from_value(value)
    return prompt


def replace_human_prompt(record: dict[str, Any], new_prompt: str) -> None:
    human_index = get_first_human_index(record)
    if human_index is None:
        return
    conversations = record.get("conversations") or []
    message = conversations[human_index]
    value = message.get("value", "")
    image_lines, _ = extract_prompt_from_value(value if isinstance(value, str) else "")
    prefix = "\n".join(image_lines) if image_lines else "<image>"
    message["value"] = f"{prefix}\n{new_prompt}"


def get_original_block(record: dict[str, Any]) -> dict[str, Any]:
    original = record.get("original")
    if isinstance(original, dict):
        return original
    original = {}
    record["original"] = original
    return original


def get_record_meta(record: dict[str, Any]) -> dict[str, Any]:
    original = record.get("original")
    if isinstance(original, dict):
        meta = original.get("meta")
        if isinstance(meta, dict):
            return meta
    return {}


def get_source_prompt(record: dict[str, Any]) -> str:
    original = record.get("original")
    if isinstance(original, dict):
        text = original.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        source_prompt = original.get("source_prompt")
        if isinstance(source_prompt, str) and source_prompt.strip():
            return source_prompt.strip()
    return get_current_prompt(record)


def normalize_piece_phrase(piece: str, add_article: bool = True) -> str:
    piece = piece.strip()
    if not piece:
        return "the piece" if add_article else "piece"
    if piece.lower().startswith("the "):
        return piece if add_article else piece[4:]
    return f"the {piece}" if add_article else piece


def build_go_prefix(category: str) -> str:
    lower = category.lower()
    if "tesuji" in lower:
        return "A Tesuji problem."
    if "life" in lower or "death" in lower:
        return "A Life and Death Problem."
    if "opening" in lower or "joseki" in lower or "fuseki" in lower:
        return "An Opening Problem."
    return "A Go problem."


def chess_opening_templates(record: dict[str, Any], _: str) -> list[str]:
    meta = get_record_meta(record)
    opening = str(meta.get("opening") or "opening").strip()
    return [
        f"Edit the chess diagram to show the {opening}.",
        f"Update the chess board so it shows the {opening}.",
        f"Modify the position so that the board displays the {opening}.",
        f"Adjust the chess position so it matches the {opening}.",
    ]


def chess_legal_moves_templates(record: dict[str, Any], _: str) -> list[str]:
    meta = get_record_meta(record)
    piece = normalize_piece_phrase(str(meta.get("piece_type") or "piece"))
    return [
        f"Highlight the squares {piece} can move to.",
        f"Mark all legal destination squares for {piece}.",
        f"Show every legal square available to {piece}.",
        f"Indicate each square {piece} may legally move to.",
    ]


def chess_bestmove_templates(record: dict[str, Any], _: str) -> list[str]:
    meta = get_record_meta(record)
    side = str(meta.get("side_to_move") or "the side to move").strip()
    return [
        f"Edit the chess diagram by making {side}'s best next move.",
        f"Update the board with {side}'s strongest next move.",
        f"Play {side}'s best next move on the chess board.",
        f"Modify the chess position by applying {side}'s best move.",
    ]


def xiangqi_opening_templates(record: dict[str, Any], _: str) -> list[str]:
    meta = get_record_meta(record)
    opening = str(meta.get("opening_en") or meta.get("opening") or "opening").strip()
    return [
        f"Edit the Chinese chess diagram to show the {opening}.",
        f"Update the Chinese chess board so it shows the {opening}.",
        f"Modify the position so that the Chinese chess board displays the {opening}.",
        f"Adjust the Chinese chess position so it matches the {opening}.",
    ]


def xiangqi_legal_moves_templates(record: dict[str, Any], _: str) -> list[str]:
    meta = get_record_meta(record)
    piece = normalize_piece_phrase(str(meta.get("piece") or "piece"))
    return [
        f"Mark the legal moves of {piece} with green dots.",
        f"Show all legal destination squares for {piece} using green dots.",
        f"Highlight every legal move for {piece} with green dots.",
        f"Indicate all legal target squares for {piece} with green dots.",
    ]


def xiangqi_bestmove_templates(record: dict[str, Any], _: str) -> list[str]:
    meta = get_record_meta(record)
    side = str(meta.get("side_to_move") or "the side to move").strip()
    return [
        f"Edit the Chinese chess diagram by making {side}'s best next move.",
        f"Update the board with {side}'s strongest next move.",
        f"Play {side}'s best next move on the Chinese chess board.",
        f"Modify the Chinese chess position by applying {side}'s best move.",
    ]


def go_crucial_move_templates(record: dict[str, Any], _: str) -> list[str]:
    meta = get_record_meta(record)
    category = str(meta.get("category") or "Go Problem")
    side = "Black" if str(meta.get("to_play") or "").lower() == "black" else "White"
    prefix = build_go_prefix(category)
    return [
        f'{prefix} {side} to play. Please find the crucial first move and mark it with "1" on the board.',
        f'{prefix} It is {side}\'s turn. Mark the crucial first move with "1" on the board.',
        f'{prefix} For {side}, identify the key first move and label it with "1".',
        f'{prefix} {side} moves next. Mark the most important first move with "1" on the board.',
    ]


def sports_nutrition_classify_grouping_templates(record: dict[str, Any], _: str) -> list[str]:
    return [
        "Classify the foods by their primary nutritional components and group foods from the same category together in the image.",
        "Sort the foods by primary nutritional component and visually place foods from the same category together.",
        "Rearrange the foods so that items with the same primary nutritional component are grouped together.",
        "Organize the foods into groups based on their primary nutritional components.",
    ]


def sports_nutrition_pie_chart_integration_templates(record: dict[str, Any], _: str) -> list[str]:
    return [
        "Take the foods on the left, classify them by nutritional composition, and place them into the correct sections of the pie chart.",
        "Integrate the foods shown on the left into the pie chart according to their nutritional composition.",
        "Categorize the foods on the left and add them to the matching regions of the pie chart.",
        "Place each food into the appropriate pie-chart sector based on its nutritional composition.",
    ]


def sports_nutrition_nutrition_pyramid_templates(record: dict[str, Any], _: str) -> list[str]:
    return [
        "Based on the foods shown, draw a sports-nutrition pyramid.",
        "Arrange the foods into a nutrition pyramid that follows sports nutrition principles.",
        "Use the foods in the image to construct a sports nutrition pyramid.",
        "Build a sports nutrition pyramid from the foods shown in the image.",
    ]


def sports_nutrition_highlight_high_gi_templates(record: dict[str, Any], _: str) -> list[str]:
    return [
        "Highlight all foods with a high Glycemic Index (GI) in red within the image.",
        "Mark every high-GI food in red.",
        "Use red highlights to indicate all foods with high Glycemic Index (GI).",
        "Highlight each food with high GI using red marks.",
    ]


def sports_nutrition_highlight_high_protein_templates(record: dict[str, Any], _: str) -> list[str]:
    return [
        "Highlight all foods with a high protein content in red within the image.",
        "Mark every high-protein food in red.",
        "Use red highlights to indicate all foods with high protein content.",
        "Highlight each food with high protein content using red marks.",
    ]


def soccer_formation_dots_templates(record: dict[str, Any], _: str) -> list[str]:
    meta = get_record_meta(record)
    formation = str(meta.get("formation") or "this").strip()
    return [
        f"Use blue dots to illustrate {formation} formation in soccer.",
        f"Arrange blue dots to show the {formation} soccer formation.",
        f"Depict the {formation} formation using blue dots.",
        f"Place blue dots to represent the {formation} soccer formation.",
    ]


def soccer_formation_jerseys_templates(record: dict[str, Any], _: str) -> list[str]:
    meta = get_record_meta(record)
    formation = str(meta.get("formation") or "this").strip()
    return [
        f"Use white jerseys to illustrate {formation} formation in soccer.",
        f"Arrange white jerseys to show the {formation} soccer formation.",
        f"Depict the {formation} formation using white jerseys.",
        f"Place white jerseys to represent the {formation} soccer formation.",
    ]


def soccer_ball_handler_highlight_templates(record: dict[str, Any], _: str) -> list[str]:
    return [
        "Use an orange circle to highlight the ball handler in this soccer tactical diagram.",
        "Mark the ball handler with an orange circle.",
        "Highlight the player controlling the ball with an orange circle.",
        "Use an orange ring to indicate the ball handler.",
    ]


TEMPLATE_FACTORIES: dict[str, TemplateFactory] = {
    "chess_opening": chess_opening_templates,
    "chess_legal_moves": chess_legal_moves_templates,
    "chess_bestmove": chess_bestmove_templates,
    "xiangqi_opening": xiangqi_opening_templates,
    "xiangqi_legal_moves": xiangqi_legal_moves_templates,
    "xiangqi_bestmove": xiangqi_bestmove_templates,
    "go_crucial_move": go_crucial_move_templates,
    "sports_nutrition_classify_grouping": sports_nutrition_classify_grouping_templates,
    "sports_nutrition_pie_chart_integration": sports_nutrition_pie_chart_integration_templates,
    "sports_nutrition_nutrition_pyramid": sports_nutrition_nutrition_pyramid_templates,
    "sports_nutrition_highlight_high_gi": sports_nutrition_highlight_high_gi_templates,
    "sports_nutrition_highlight_high_protein": sports_nutrition_highlight_high_protein_templates,
    "soccer_formation_dots": soccer_formation_dots_templates,
    "soccer_formation_jerseys": soccer_formation_jerseys_templates,
    "soccer_ball_handler_highlight": soccer_ball_handler_highlight_templates,
}


def build_prompt_candidates(dataset_key: str, record: dict[str, Any], source_prompt: str) -> list[str]:
    factory = TEMPLATE_FACTORIES.get(dataset_key)
    if factory is None:
        return [source_prompt]
    prompts = [prompt.strip() for prompt in factory(record, source_prompt) if isinstance(prompt, str) and prompt.strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for prompt in prompts:
        if prompt not in seen:
            deduped.append(prompt)
            seen.add(prompt)
    return deduped or [source_prompt]


def rewrite_record(
    record: dict[str, Any],
    dataset_name: str,
    dataset_key: str | None,
    rewrite: bool,
    hash_salt: str,
) -> tuple[dict[str, Any], bool]:
    updated = copy.deepcopy(record)
    source_prompt = get_source_prompt(updated)
    current_prompt = get_current_prompt(updated)
    effective_prompt = source_prompt or current_prompt
    if not effective_prompt:
        return updated, False

    original = get_original_block(updated)
    original.setdefault("source_prompt", effective_prompt)

    if dataset_key is None:
        original["prompt_dataset_key"] = None
        original["prompt_style"] = "canonical"
        original["prompt_template_id"] = 0
        original["prompt_was_rewritten"] = False
        return updated, False

    prompt_candidates = build_prompt_candidates(dataset_key, updated, effective_prompt)
    prompt_template_id = 0
    new_prompt = current_prompt or effective_prompt
    rewritten = False

    if rewrite and len(prompt_candidates) > 1:
        source_id = original.get("task_id") or updated.get("id") or effective_prompt
        alt_count = len(prompt_candidates) - 1
        alt_index = stable_hash_int(hash_salt, dataset_name, source_id, effective_prompt, "template") % alt_count
        prompt_template_id = alt_index + 1
        new_prompt = prompt_candidates[prompt_template_id]
        if new_prompt != current_prompt:
            replace_human_prompt(updated, new_prompt)
            rewritten = True
    else:
        if not current_prompt:
            replace_human_prompt(updated, new_prompt)

    original["prompt_dataset_key"] = dataset_key
    original["prompt_style"] = "expanded" if rewritten else "canonical"
    original["prompt_template_id"] = prompt_template_id
    original["prompt_was_rewritten"] = rewritten
    return updated, rewritten


def build_meta_entry(
    source_entry: dict[str, Any] | None,
    dataset_name: str,
    annotation_path: Path,
    shard_count: int,
    length: int,
) -> dict[str, Any]:
    if source_entry is not None:
        meta_entry = copy.deepcopy(source_entry)
    else:
        meta_entry = {
            "info": "Two Image | Editing | Synthetic",
            "task": "Image Editing",
            "root": None,
            "data_augment": False,
            "repeat_time": 1,
            "generation_modality": 1,
            "dynamic_image_size": False,
            "cache_db": False,
            "cache_dir": None,
            "image_style": "AIGC",
        }
    meta_entry["annotation"] = str(annotation_path.resolve())
    meta_entry["train_load_samples"] = shard_count
    meta_entry["length"] = length
    return meta_entry


def process_dataset(
    dataset_dir: Path,
    output_root: Path,
    meta_map: dict[str, Any],
    expand_ratio: float,
    hash_salt: str,
    overwrite: bool,
) -> tuple[str, dict[str, Any], int, int]:
    dataset_name = dataset_dir.name
    dataset_key = detect_dataset_key(dataset_name)
    input_files = sorted(
        path for path in dataset_dir.glob("*.jsonl") if not path.name.endswith(".expanded.jsonl")
    )
    if not input_files:
        raise FileNotFoundError(f"No jsonl files found in dataset directory: {dataset_dir}")

    file_records: list[list[dict[str, Any]]] = [load_jsonl(path) for path in input_files]
    total_records = sum(len(records) for records in file_records)
    rewrite_target = int(math.floor(total_records * expand_ratio))

    scored_indices: list[tuple[int, int, int]] = []
    for file_idx, records in enumerate(file_records):
        for record_idx, record in enumerate(records):
            source_prompt = get_source_prompt(record)
            sample_id = record.get("id", record_idx)
            score = stable_hash_int(hash_salt, dataset_name, sample_id, source_prompt, "rewrite")
            scored_indices.append((score, file_idx, record_idx))
    scored_indices.sort(key=lambda item: item[0])
    rewrite_lookup = {
        (file_idx, record_idx)
        for _, file_idx, record_idx in scored_indices[:rewrite_target]
    }

    dataset_output_dir = output_root / dataset_name
    dataset_output_dir.mkdir(parents=True, exist_ok=True)

    rewritten_total = 0
    shard_paths: list[Path] = []
    for file_idx, input_path in enumerate(input_files):
        output_path = dataset_output_dir / f"{input_path.stem}.expanded.jsonl"
        expanded_records: list[dict[str, Any]] = []
        for record_idx, record in enumerate(file_records[file_idx]):
            expanded, rewritten = rewrite_record(
                record=record,
                dataset_name=dataset_name,
                dataset_key=dataset_key,
                rewrite=(file_idx, record_idx) in rewrite_lookup,
                hash_salt=hash_salt,
            )
            expanded_records.append(expanded)
            if rewritten:
                rewritten_total += 1
        dump_jsonl(output_path, expanded_records, overwrite=overwrite)
        shard_paths.append(output_path)

    annotation_path = dataset_output_dir if len(shard_paths) > 1 else shard_paths[0]
    meta_entry = build_meta_entry(
        source_entry=meta_map.get(dataset_name) if isinstance(meta_map.get(dataset_name), dict) else None,
        dataset_name=dataset_name,
        annotation_path=annotation_path,
        shard_count=len(shard_paths),
        length=total_records,
    )
    return dataset_name, meta_entry, total_records, rewritten_total


def main() -> int:
    args = parse_args()
    if not (0.0 <= args.expand_ratio <= 1.0):
        raise SystemExit("--expand-ratio must be between 0 and 1")

    input_root = Path(args.input_root).resolve() if args.input_root else None
    if input_root is None:
        raise SystemExit("--input-root is required")
    output_root = Path(args.output_root).resolve() if args.output_root else input_root
    dataset_dirs = [Path(path).resolve() for path in args.dataset_root]
    if input_root is not None:
        dataset_dirs.extend(discover_dataset_dirs(input_root))
    if not dataset_dirs:
        raise SystemExit("Provide --input-root and/or at least one --dataset-root.")

    deduped_dirs: list[Path] = []
    seen_dirs: set[Path] = set()
    for dataset_dir in dataset_dirs:
        if dataset_dir not in seen_dirs:
            deduped_dirs.append(dataset_dir)
            seen_dirs.add(dataset_dir)

    meta_path: Path | None = None
    if args.meta_json:
        meta_path = Path(args.meta_json).resolve()
    elif input_root is not None:
        candidate = input_root / "meta.json"
        if candidate.exists():
            meta_path = candidate
    meta_map = load_meta_map(meta_path)

    output_root.mkdir(parents=True, exist_ok=True)

    new_meta: dict[str, Any] = {}
    total_records = 0
    total_rewritten = 0

    for dataset_dir in deduped_dirs:
        dataset_name, meta_entry, dataset_records, dataset_rewritten = process_dataset(
            dataset_dir=dataset_dir,
            output_root=output_root,
            meta_map=meta_map,
            expand_ratio=args.expand_ratio,
            hash_salt=args.hash_salt,
            overwrite=args.overwrite,
        )
        new_meta[dataset_name] = meta_entry
        total_records += dataset_records
        total_rewritten += dataset_rewritten
        print(
            f"[ok] {dataset_name}: total={dataset_records}, rewritten={dataset_rewritten}, "
            f"ratio={dataset_rewritten / dataset_records:.3f}"
        )

    meta_output_name = "meta.expanded.json" if input_root is not None and output_root == input_root else "meta.json"
    meta_output_path = output_root / meta_output_name
    meta_output_path.write_text(json.dumps(new_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] meta written to {meta_output_path}")
    print(
        f"[ok] finished: datasets={len(new_meta)}, total_records={total_records}, "
        f"total_rewritten={total_rewritten}, overall_ratio={total_rewritten / total_records if total_records else 0.0:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
