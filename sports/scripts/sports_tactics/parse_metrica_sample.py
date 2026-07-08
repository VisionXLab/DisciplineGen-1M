#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
from pathlib import Path
from typing import Any

from tactics_utils import dump_jsonl


TRACKING_HOME = 'RawTrackingData_Home_Team.csv'
TRACKING_AWAY = 'RawTrackingData_Away_Team.csv'
MAX_PLAYERS_PER_TEAM = 11


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Parse Metrica sample-data into canonical soccer tactics JSONL.')
    parser.add_argument('--metrica-root', required=True, help='Directory containing Sample_Game_* subdirectories.')
    parser.add_argument('--output-jsonl', required=True)
    parser.add_argument('--frame-step', type=int, default=150)
    parser.add_argument('--future-frames', type=int, default=20)
    parser.add_argument('--min-player-disp', type=float, default=0.035)
    parser.add_argument('--max-samples-per-game', type=int, default=60)
    parser.add_argument('--seed', type=int, default=7)
    return parser.parse_args()


def safe_float(value: str) -> float | None:
    text = str(value or '').strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def safe_int(value: str | int | float, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_header(value: str) -> str:
    return str(value or '').strip().lower()


def extract_jersey_number(value: str) -> int | None:
    text = str(value or '').strip()
    if not text:
        return None
    match = re.search(r'(\d+)', text)
    if not match:
        return None
    return int(match.group(1))


def is_valid_coord(x: float | None, y: float | None) -> bool:
    if x is None or y is None:
        return False
    if not math.isfinite(x) or not math.isfinite(y):
        return False
    return 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


def find_header_row(rows: list[list[str]]) -> int:
    for idx, row in enumerate(rows[:6]):
        headers = {normalize_header(cell) for cell in row}
        if 'frame' in headers and 'period' in headers:
            return idx
    raise SystemExit('Could not locate Metrica tracking header row containing Frame and Period columns.')


def find_column_index(headers: list[str], target: str) -> int:
    target = normalize_header(target)
    for idx, value in enumerate(headers):
        if normalize_header(value) == target:
            return idx
    raise ValueError(target)


def build_player_column_map(header_row: list[str], jersey_row: list[str], meta_cols: int) -> tuple[list[tuple[int, int, int]], int | None, int | None]:
    column_map: list[tuple[int, int, int]] = []
    ball_x_idx: int | None = None
    ball_y_idx: int | None = None

    max_len = min(len(header_row), len(jersey_row))
    idx = meta_cols
    while idx + 1 < max_len:
        header_name = normalize_header(header_row[idx])
        next_header_name = normalize_header(header_row[idx + 1])
        jersey = extract_jersey_number(jersey_row[idx])
        if header_name == 'ball':
            ball_x_idx = idx
            ball_y_idx = idx + 1
            idx += 2
            continue
        if jersey is not None:
            column_map.append((jersey, idx, idx + 1))
            idx += 2
            continue
        if header_name and next_header_name == '':
            maybe_jersey = extract_jersey_number(header_row[idx])
            if maybe_jersey is not None:
                column_map.append((maybe_jersey, idx, idx + 1))
                idx += 2
                continue
        idx += 1

    if ball_x_idx is None or ball_y_idx is None:
        for probe in range(meta_cols, len(header_row) - 1):
            if normalize_header(header_row[probe]) == 'ball':
                ball_x_idx = probe
                ball_y_idx = probe + 1
                break

    return column_map, ball_x_idx, ball_y_idx


def sanitize_players(players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    seen: set[int] = set()
    for player in players:
        jersey = safe_int(player.get('jersey_number'), -1)
        x = player.get('x')
        y = player.get('y')
        if jersey <= 0 or jersey in seen:
            continue
        if not is_valid_coord(x, y):
            continue
        clean.append(player)
        seen.add(jersey)
        if len(clean) >= MAX_PLAYERS_PER_TEAM:
            break
    return clean


def load_tracking_csv(path: Path, team_label: str) -> tuple[list[int], dict[int, dict[str, Any]]]:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    if len(rows) < 4:
        raise SystemExit(f'Unexpected tracking format: {path}')

    header_idx = find_header_row(rows)
    jersey_row_idx = max(0, header_idx - 1)
    header_row = rows[header_idx]
    jersey_row = rows[jersey_row_idx]
    data_rows = rows[header_idx + 1 :]

    try:
        period_idx = find_column_index(header_row, 'Period')
        frame_idx = find_column_index(header_row, 'Frame')
    except ValueError as exc:
        raise SystemExit(f'Missing required column {exc} in {path}') from exc

    if any(normalize_header(v) == 'time [s]' for v in header_row):
        meta_cols = max(period_idx, frame_idx, find_column_index(header_row, 'Time [s]')) + 1
    else:
        meta_cols = max(period_idx, frame_idx) + 1

    player_columns, ball_x_idx, ball_y_idx = build_player_column_map(header_row, jersey_row, meta_cols)
    player_ids = [jersey for jersey, _, _ in player_columns]

    frames: dict[int, dict[str, Any]] = {}
    for row in data_rows:
        if not row or len(row) <= max(frame_idx, period_idx):
            continue
        frame = safe_int(row[frame_idx], -1)
        period = safe_int(row[period_idx], -1)
        if frame < 0 or period < 0:
            continue

        team_players: list[dict[str, Any]] = []
        for jersey, x_idx, y_idx in player_columns:
            if y_idx >= len(row):
                continue
            x = safe_float(row[x_idx])
            y = safe_float(row[y_idx])
            if not is_valid_coord(x, y):
                continue
            team_players.append(
                {
                    'player_code': f'{team_label}_{jersey}',
                    'team': team_label.lower(),
                    'jersey_number': jersey,
                    'x': x,
                    'y': y,
                }
            )

        team_players = sanitize_players(team_players)
        if not team_players:
            continue

        ball_x = safe_float(row[ball_x_idx]) if ball_x_idx is not None and ball_x_idx < len(row) else None
        ball_y = safe_float(row[ball_y_idx]) if ball_y_idx is not None and ball_y_idx < len(row) else None
        if not is_valid_coord(ball_x, ball_y):
            ball_x = None
            ball_y = None

        frames[frame] = {
            'frame': frame,
            'period': period,
            'players': team_players,
            'ball': [ball_x, ball_y],
        }
    return player_ids, frames


def merge_tracking(home_frames: dict[int, dict[str, Any]], away_frames: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    common_frames = sorted(set(home_frames) & set(away_frames))
    merged: list[dict[str, Any]] = []
    for frame in common_frames:
        home = home_frames[frame]
        away = away_frames[frame]
        if not home['players'] or not away['players']:
            continue
        merged.append(
            {
                'frame': frame,
                'period': home['period'],
                'home_players': home['players'],
                'away_players': away['players'],
                'ball': home['ball'],
            }
        )
    return merged


def tracking_index_by_frame(frames: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {item['frame']: item for item in frames}


def sqdist(a: tuple[float, float], b: tuple[float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy


def find_player(frame: dict[str, Any], team: str, jersey: int) -> tuple[float, float] | None:
    players = frame['home_players'] if team == 'home' else frame['away_players']
    for player in players:
        if safe_int(player.get('jersey_number')) == jersey:
            return float(player['x']), float(player['y'])
    return None


def build_tracking_records(game_dir: Path, args: argparse.Namespace, rng: random.Random) -> list[dict[str, Any]]:
    home_path = next(game_dir.glob(f'*{TRACKING_HOME}'), None)
    away_path = next(game_dir.glob(f'*{TRACKING_AWAY}'), None)
    if home_path is None or away_path is None:
        return []

    game_name = game_dir.name
    _, home_frames = load_tracking_csv(home_path, 'Home')
    _, away_frames = load_tracking_csv(away_path, 'Away')
    merged = merge_tracking(home_frames, away_frames)
    frame_map = tracking_index_by_frame(merged)
    records: list[dict[str, Any]] = []

    for index in range(0, len(merged), max(1, args.frame_step)):
        start = merged[index]
        next_state = frame_map.get(start['frame'] + args.future_frames)
        if next_state is None or start['period'] != next_state['period']:
            continue

        max_disp2 = 0.0
        for side_key, team_name in [('home_players', 'home'), ('away_players', 'away')]:
            for player in start[side_key]:
                jersey = safe_int(player.get('jersey_number'), -1)
                if jersey <= 0:
                    continue
                start_coord = (float(player['x']), float(player['y']))
                end_coord = find_player(next_state, team_name, jersey)
                if end_coord is None:
                    continue
                disp2 = sqdist(start_coord, end_coord)
                if disp2 > max_disp2:
                    max_disp2 = disp2

        if max_disp2 < args.min_player_disp * args.min_player_disp:
            continue

        records.append(
            {
                'task_type': 'soccer_next_frame',
                'source_id': f'metrica_next_{game_name}_{start["frame"]}',
                'source_dataset': 'metrica_sample',
                'game_id': game_name,
                'start_frame': start['frame'],
                'future_frame': next_state['frame'],
                'period': start['period'],
                'home_players_start': start['home_players'],
                'away_players_start': start['away_players'],
                'home_players_next': next_state['home_players'],
                'away_players_next': next_state['away_players'],
                'ball_start': start['ball'],
                'ball_next': next_state['ball'],
            }
        )
        if len(records) >= args.max_samples_per_game:
            break

    rng.shuffle(records)
    return records


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    root = Path(args.metrica_root)
    if not root.exists():
        raise SystemExit(f'metrica-root not found: {root}')
    records: list[dict[str, Any]] = []
    for game_dir in sorted(path for path in root.iterdir() if path.is_dir() and path.name.startswith('Sample_Game_')):
        game_records = build_tracking_records(game_dir, args, rng)
        print(f'[game] {game_dir.name}: records={len(game_records)}')
        records.extend(game_records)
    dump_jsonl(records, Path(args.output_jsonl))
    next_count = sum(1 for record in records if record.get('task_type') == 'soccer_next_frame')
    print(f'Wrote {len(records)} records to {args.output_jsonl}')
    print(f'next_frame_records={next_count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
