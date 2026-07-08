#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from tactics_utils import (
    draw_dot,
    draw_highlight_ring,
    draw_jersey,
    load_tactics_records,
    render_soccer_pitch,
    slots_from_players,
    statsbomb_location_to_board,
)


TASK_CHOICES = [
    'soccer_formation_dots',
    'soccer_formation_jerseys',
    'soccer_ball_handler_highlight',
    'all',
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build soccer tactics-board editing datasets from canonical tactics JSONL.')
    parser.add_argument('--input-jsonl', required=True)
    parser.add_argument('--task', required=True, choices=TASK_CHOICES)
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--max-samples', type=int, default=100)
    parser.add_argument('--image-size', type=int, default=1024)
    parser.add_argument('--seed', type=int, default=7)
    return parser.parse_args()


def ensure_dirs(output_root: Path) -> tuple[str, Path, Path]:
    dataset_name = output_root.name
    editing_dir = output_root / 'editing'
    gt_dir = output_root / 'gt'
    editing_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)
    return dataset_name, editing_dir, gt_dir


def render_team_dots(image_size: int, coords: list[tuple[float, float]], color: str = '#2AA7FF') -> Image.Image:
    canvas = render_soccer_pitch(image_size)
    for coord in coords:
        draw_dot(canvas, coord, color=color)
    return canvas


def render_team_jerseys(image_size: int, coords: list[tuple[float, float]], fill: str = '#FFFFFF', outline: str = '#1E2430') -> Image.Image:
    canvas = render_soccer_pitch(image_size)
    for coord in coords:
        draw_jersey(canvas, coord, fill=fill, outline=outline)
    return canvas


def build_soccer_formation_dots(record: dict[str, Any], image_size: int) -> dict[str, Any]:
    coords = slots_from_players(record.get('players') or [], mirror=False)
    before = render_soccer_pitch(image_size)
    after = render_team_dots(image_size, coords)
    return {
        'before': before,
        'after': after,
        'text': f"Use blue dots to illustrate {record.get('formation', 'this')} formation in soccer.",
        'meta': {
            'task_type': 'soccer_formation_dots',
            'source_id': record.get('source_id'),
            'match_id': record.get('match_id'),
            'team_name': record.get('team_name'),
            'formation': record.get('formation'),
        },
    }


def build_soccer_formation_jerseys(record: dict[str, Any], image_size: int) -> dict[str, Any]:
    coords = slots_from_players(record.get('players') or [], mirror=False)
    before = render_soccer_pitch(image_size)
    after = render_team_jerseys(image_size, coords)
    return {
        'before': before,
        'after': after,
        'text': f"Use white jerseys to illustrate {record.get('formation', 'this')} formation in soccer.",
        'meta': {
            'task_type': 'soccer_formation_jerseys',
            'source_id': record.get('source_id'),
            'match_id': record.get('match_id'),
            'team_name': record.get('team_name'),
            'formation': record.get('formation'),
        },
    }


def build_soccer_ball_handler_highlight(record: dict[str, Any], image_size: int) -> dict[str, Any]:
    before = render_soccer_pitch(image_size)
    after = render_soccer_pitch(image_size)
    handler_player_id = record.get('ball_handler_player_id')
    handler_coord = statsbomb_location_to_board(record.get('location') or [60.0, 40.0])

    opp_coords = slots_from_players(record.get('opponent_players') or [], mirror=True)
    for coord in opp_coords:
        draw_jersey(before, coord, fill='#1F2430', outline='#FFFFFF', scale=0.92)
        draw_jersey(after, coord, fill='#1F2430', outline='#FFFFFF', scale=0.92)

    team_players = record.get('players') or []
    for player in team_players:
        player_id = (player or {}).get('player_id')
        if player_id == handler_player_id:
            coord = handler_coord
            scale = 1.0
        else:
            coord = slots_from_players([player], mirror=False)[0]
            scale = 0.92
        draw_jersey(before, coord, fill='#FFFFFF', outline='#1F2430', scale=scale)
        draw_jersey(after, coord, fill='#FFFFFF', outline='#1F2430', scale=scale)

    draw_highlight_ring(after, handler_coord, radius=30, color='#F28C28')

    return {
        'before': before,
        'after': after,
        'text': 'Use an orange circle to highlight the ball handler in this soccer tactical diagram.',
        'meta': {
            'task_type': 'soccer_ball_handler_highlight',
            'source_id': record.get('source_id'),
            'match_id': record.get('match_id'),
            'team_name': record.get('team_name'),
            'opponent_team_name': record.get('opponent_team_name'),
            'formation': record.get('formation'),
            'opponent_formation': record.get('opponent_formation'),
            'ball_handler_name': record.get('ball_handler_name'),
            'event_type': record.get('event_type'),
            'event_minute': record.get('event_minute'),
            'event_second': record.get('event_second'),
        },
    }


BUILDERS: dict[str, Callable[[dict[str, Any], int], dict[str, Any]]] = {
    'soccer_formation_dots': build_soccer_formation_dots,
    'soccer_formation_jerseys': build_soccer_formation_jerseys,
    'soccer_ball_handler_highlight': build_soccer_ball_handler_highlight,
}


def filter_records(records: list[dict[str, Any]], task: str) -> list[dict[str, Any]]:
    if task in {'soccer_formation_dots', 'soccer_formation_jerseys'}:
        return [record for record in records if record.get('task_type') == 'soccer_formation']
    if task == 'soccer_ball_handler_highlight':
        return [record for record in records if record.get('task_type') == 'soccer_ball_handler']
    return records


def export_dataset(samples: list[dict[str, Any]], output_root: Path) -> int:
    dataset_name, editing_dir, gt_dir = ensure_dirs(output_root)
    items: list[dict[str, Any]] = []
    for idx, sample in enumerate(samples, start=1):
        sample['before'].save(editing_dir / f'{idx}_before.png')
        sample['after'].save(gt_dir / f'{idx}_after.png')
        items.append(
            {
                'text': sample['text'],
                'task_id': f'task_{idx}',
                'image_path': f'{dataset_name}/editing/{idx}_before.png',
                'gt': f'{dataset_name}/gt/{idx}_after.png',
                'sub_task': 'Sports Tactic',
                'meta': sample.get('meta', {}),
            }
        )
    json_path = output_root / f'{dataset_name}.json'
    json_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Exported {len(items)} sports tactics samples to {output_root}')
    print(f'JSON written to {json_path}')
    return 0


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    records = load_tactics_records(Path(args.input_jsonl))
    tasks = list(BUILDERS) if args.task == 'all' else [args.task]
    samples: list[dict[str, Any]] = []
    for task in tasks:
        task_records = filter_records(records, task)
        random.shuffle(task_records)
        for record in task_records:
            samples.append(BUILDERS[task](record, args.image_size))
            if len(samples) >= args.max_samples:
                return export_dataset(samples, Path(args.output_root))
    if not samples:
        raise SystemExit('No sports tactics samples were generated. Check the parsed JSONL and chosen task.')
    return export_dataset(samples, Path(args.output_root))


if __name__ == '__main__':
    raise SystemExit(main())
