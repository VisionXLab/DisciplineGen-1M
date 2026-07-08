from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image


MAX_LINES_PER_SHARD = 50_000


TASK_INFO_MAP: dict[str, dict[str, str]] = {
    "chess_opening": {
        "info": "Image Editing | Board Game | Chess Opening",
        "task": "Instruction-guided Image Editing",
        "image_style": "AIGC",
    },
    "chess_legal_moves": {
        "info": "Image Editing | Board Game | Chess Legal Moves",
        "task": "Instruction-guided Image Editing",
        "image_style": "AIGC",
    },
    "xiangqi_opening": {
        "info": "Image Editing | Board Game | Xiangqi Opening",
        "task": "Instruction-guided Image Editing",
        "image_style": "AIGC",
    },
    "xiangqi_legal_moves": {
        "info": "Image Editing | Board Game | Xiangqi Legal Moves",
        "task": "Instruction-guided Image Editing",
        "image_style": "AIGC",
    },
    "sports_nutrition_classify_grouping": {
        "info": "Image Editing | Sports Nutrition | Food Grouping",
        "task": "Instruction-guided Image Editing",
        "image_style": "AIGC",
    },
    "sports_nutrition_pie_chart_integration": {
        "info": "Image Editing | Sports Nutrition | Pie Chart Integration",
        "task": "Instruction-guided Image Editing",
        "image_style": "AIGC",
    },
    "sports_nutrition_nutrition_pyramid": {
        "info": "Image Editing | Sports Nutrition | Nutrition Pyramid",
        "task": "Instruction-guided Image Editing",
        "image_style": "AIGC",
    },
    "sports_nutrition_highlight_high_gi": {
        "info": "Image Editing | Sports Nutrition | Highlight High GI Foods",
        "task": "Instruction-guided Image Editing",
        "image_style": "AIGC",
    },
    "sports_nutrition_highlight_high_protein": {
        "info": "Image Editing | Sports Nutrition | Highlight High Protein Foods",
        "task": "Instruction-guided Image Editing",
        "image_style": "AIGC",
    },
    "soccer_formation_dots": {
        "info": "Image Editing | Sports Tactics | Soccer Formation Dots",
        "task": "Instruction-guided Image Editing",
        "image_style": "AIGC",
    },
    "soccer_formation_jerseys": {
        "info": "Image Editing | Sports Tactics | Soccer Formation Jerseys",
        "task": "Instruction-guided Image Editing",
        "image_style": "AIGC",
    },
    "soccer_ball_handler_highlight": {
        "info": "Image Editing | Sports Tactics | Ball Handler Highlight",
        "task": "Instruction-guided Image Editing",
        "image_style": "AIGC",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert rendered editing datasets into unified annotation/meta format."
    )
    parser.add_argument(
        "--dataset-root",
        action="append",
        required=True,
        help="Path to one rendered dataset root containing <dataset_name>.json, editing/, gt/ . Can be passed multiple times.",
    )
    parser.add_argument(
        "--output-root",
        required=True,
        help="Directory to write unified annotations and meta.json.",
    )
    parser.add_argument(
        "--dataset-name",
        action="append",
        default=[],
        help="Optional override name(s), one per --dataset-root in the same order.",
    )
    parser.add_argument(
        "--max-lines-per-file",
        type=int,
        default=MAX_LINES_PER_SHARD,
        help="Maximum number of lines per annotation jsonl shard. Default: 50000.",
    )
    return parser.parse_args()


def load_items(dataset_root: Path, dataset_name: str) -> list[dict[str, Any]]:
    json_path = dataset_root / f"{dataset_name}.json"
    if not json_path.exists():
        raise FileNotFoundError(f"Dataset json not found: {json_path}")
    with json_path.open("r", encoding="utf-8") as handle:
        items = json.load(handle)
    if not isinstance(items, list):
        raise ValueError(f"Dataset json must be a list: {json_path}")
    return items


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.width, img.height


def normalize_relative_path(path_str: str, dataset_name: str) -> str:
    normalized = path_str.replace("\\", "/").lstrip("/")
    prefix = f"{dataset_name}/"
    if normalized.startswith(prefix):
        normalized = normalized[len(prefix):]
    return normalized


def build_annotation_record(
    item: dict[str, Any],
    sample_id: int,
    dataset_root: Path,
    dataset_name: str,
) -> dict[str, Any]:
    image_rel = normalize_relative_path(str(item["image_path"]), dataset_name)
    gt_rel = normalize_relative_path(str(item["gt"]), dataset_name)
    image_abs = dataset_root / image_rel
    gt_abs = dataset_root / gt_rel
    image_w, image_h = image_size(image_abs)
    gt_w, gt_h = image_size(gt_abs)

    original: dict[str, Any] = {}
    if "task_id" in item:
        original["task_id"] = item["task_id"]
    if "sub_task" in item:
        original["sub_task"] = item["sub_task"]
    if "text" in item:
        original["text"] = item["text"]
    meta = item.get("meta")
    if isinstance(meta, dict) and meta:
        original["meta"] = meta

    record = {
        "id": sample_id,
        "image": [image_rel, gt_rel],
        "conversations": [
            {"from": "human", "value": f"<image>\n{item['text']}"},
            {"from": "gpt", "value": "<image>"},
        ],
        "width": [image_w, gt_w],
        "height": [image_h, gt_h],
        "generation_flags": [0, 1],
    }
    if original:
        record["original"] = original
    return record


def write_shards(
    records: list[dict[str, Any]],
    annotation_dir: Path,
    dataset_name: str,
    max_lines_per_file: int,
) -> list[Path]:
    annotation_dir.mkdir(parents=True, exist_ok=True)
    if max_lines_per_file <= 0:
        raise ValueError("--max-lines-per-file must be positive")
    shard_count = max(1, math.ceil(len(records) / max_lines_per_file))
    shard_paths: list[Path] = []
    for shard_idx in range(shard_count):
        start = shard_idx * max_lines_per_file
        end = min(len(records), start + max_lines_per_file)
        shard_path = annotation_dir / f"{dataset_name}.part-{shard_idx:05d}.jsonl"
        with shard_path.open("w", encoding="utf-8") as handle:
            for record in records[start:end]:
                handle.write(json.dumps(record, ensure_ascii=False))
                handle.write("\n")
        shard_paths.append(shard_path)
    return shard_paths


def build_meta_entry(
    dataset_name: str,
    dataset_root: Path,
    annotation_path: Path,
    length: int,
    shard_count: int,
) -> dict[str, Any]:
    info = TASK_INFO_MAP.get(
        dataset_name,
        {
            "info": "Image Editing | Synthetic",
            "task": "Instruction-guided Image Editing",
            "image_style": "AIGC",
        },
    )
    return {
        "info": info["info"],
        "task": info["task"],
        "root": str(dataset_root.resolve()),
        "annotation": str(annotation_path.resolve()),
        "length": length,
        "train_load_samples": shard_count,
        "data_augment": False,
        "repeat_time": 1,
        "generation_modality": 1,
        "dynamic_image_size": False,
        "cache_db": False,
        "cache_dir": f"playground/data_gen/{dataset_name}",
        "image_style": info["image_style"],
    }


def main() -> int:
    args = parse_args()
    dataset_roots = [Path(p).resolve() for p in args.dataset_root]
    if args.dataset_name and len(args.dataset_name) != len(dataset_roots):
        raise SystemExit("--dataset-name count must match --dataset-root count when provided")

    output_root = Path(args.output_root).resolve()
    annotations_root = output_root / "annotations"
    annotations_root.mkdir(parents=True, exist_ok=True)

    meta: dict[str, Any] = {}
    for idx, dataset_root in enumerate(dataset_roots):
        dataset_name = (
            args.dataset_name[idx]
            if idx < len(args.dataset_name) and args.dataset_name[idx]
            else dataset_root.name
        )
        items = load_items(dataset_root, dataset_name)
        records = [
            build_annotation_record(
                item=item,
                sample_id=sample_id,
                dataset_root=dataset_root,
                dataset_name=dataset_name,
            )
            for sample_id, item in enumerate(items)
        ]
        dataset_annotation_dir = annotations_root / dataset_name
        shard_paths = write_shards(
            records=records,
            annotation_dir=dataset_annotation_dir,
            dataset_name=dataset_name,
            max_lines_per_file=args.max_lines_per_file,
        )
        annotation_meta_path = dataset_annotation_dir if len(shard_paths) > 1 else shard_paths[0]
        meta[dataset_name] = build_meta_entry(
            dataset_name=dataset_name,
            dataset_root=dataset_root,
            annotation_path=annotation_meta_path,
            length=len(records),
            shard_count=len(shard_paths),
        )
        print(f"[ok] {dataset_name}: {len(records)} samples, {len(shard_paths)} shard(s)")

    meta_path = output_root / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] meta written to {meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
