#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from go_utils import GoProblem, build_instruction, load_jsonl_problems, load_sgf_problems, render_go_board, row_col_to_gtp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Go dataset builder for image-editing tasks.")
    parser.add_argument("--task", default="crucial_move", choices=["crucial_move"])
    parser.add_argument("--input", required=True, help="Input JSONL or SGF collection.")
    parser.add_argument("--input-format", default="auto", choices=["auto", "jsonl", "sgf"])
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--max-samples", type=int, default=100, help="Number of samples to export. Use 0 for all loaded Go positions.")
    parser.add_argument("--image-size", type=int, default=1024)
    return parser.parse_args()


def load_problems(path: str, input_format: str) -> list[GoProblem]:
    if input_format == "jsonl" or (input_format == "auto" and path.lower().endswith(".jsonl")):
        return [problem for problem in load_jsonl_problems(path) if problem.size == 19]
    if input_format == "sgf" or (input_format == "auto" and path.lower().endswith((".sgf", ".sgfs"))):
        return [problem for problem in load_sgf_problems(path) if problem.size == 19]
    raise SystemExit(f"Unsupported input format for {path}. Use --input-format jsonl or sgf.")


def ensure_dirs(output_root: Path) -> tuple[str, Path, Path]:
    dataset_name = output_root.name
    editing_dir = output_root / "editing"
    gt_dir = output_root / "gt"
    editing_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)
    return dataset_name, editing_dir, gt_dir


def export_dataset(problems: list[GoProblem], output_root: Path, image_size: int) -> int:
    dataset_name, editing_dir, gt_dir = ensure_dirs(output_root)
    items: list[dict] = []
    for idx, problem in enumerate(problems, start=1):
        render_go_board(problem, image_size=image_size, show_answer=False).save(editing_dir / f"{idx}_before.png")
        render_go_board(problem, image_size=image_size, show_answer=True).save(gt_dir / f"{idx}_after.png")

        items.append(
            {
                "text": build_instruction(problem),
                "task_id": f"task_{idx}",
                "image_path": f"{dataset_name}/editing/{idx}_before.png",
                "gt": f"{dataset_name}/gt/{idx}_after.png",
                "sub_task": "Go",
                "meta": {
                    "category": problem.category,
                    "board_size": problem.size,
                    "to_play": problem.to_play,
                    "answer": row_col_to_gtp(problem.answer[0], problem.answer[1], problem.size),
                    "source_id": problem.source_id,
                    **problem.meta,
                },
            }
        )

    json_path = output_root / f"{dataset_name}.json"
    json_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(items)} Go samples to {output_root}")
    print(f"JSON written to {json_path}")
    return 0


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    problems = load_problems(args.input, args.input_format)
    if not problems:
        raise SystemExit("No valid Go problems were loaded.")
    chosen = problems if args.max_samples <= 0 else problems[: args.max_samples]
    return export_dataset(chosen, output_root, args.image_size)


if __name__ == "__main__":
    raise SystemExit(main())

