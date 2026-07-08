#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from tactics_utils import dump_jsonl, format_formation, safe_int

ON_BALL_EVENT_TYPES = {
    'Pass',
    'Carry',
    'Dribble',
    'Shot',
    'Ball Receipt*',
    'Miscontrol',
    'Foul Won',
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Parse StatsBomb Open Data into canonical soccer tactics JSONL.')
    parser.add_argument('--statsbomb-root', required=True, help='Directory that contains competitions.json and subdirs like events/ lineups/.')
    parser.add_argument('--output-jsonl', required=True)
    parser.add_argument('--highlight-stride', type=int, default=18)
    parser.add_argument('--max-highlight-per-match', type=int, default=12)
    parser.add_argument('--max-matches', type=int, default=0, help='Maximum number of event files to scan. Use 0 for all matches.')
    parser.add_argument('--include-ball-handler', action='store_true', help='Also export soccer_ball_handler records from on-ball events.')
    parser.add_argument('--seed', type=int, default=7)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def team_name(team: dict[str, Any]) -> str:
    return str((team or {}).get('name') or (team or {}).get('team_name') or '')


def extract_starting_xi(events: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for event in events:
        if ((event.get('type') or {}).get('name') or '') != 'Starting XI':
            continue
        team = event.get('team') or {}
        tactics = event.get('tactics') or {}
        team_id = safe_int(team.get('id'))
        lineup = []
        for item in tactics.get('lineup') or []:
            player = item.get('player') or {}
            position = item.get('position') or {}
            lineup.append(
                {
                    'player_id': safe_int(player.get('id')),
                    'player_name': str(player.get('name') or ''),
                    'position_id': safe_int(position.get('id')),
                    'position_name': str(position.get('name') or ''),
                    'jersey_number': item.get('jersey_number'),
                }
            )
        out[team_id] = {
            'team_id': team_id,
            'team_name': team_name(team),
            'formation': format_formation(tactics.get('formation')),
            'players': lineup,
        }
    return out


def lineup_position_map(lineups_payload: list[dict[str, Any]]) -> dict[int, dict[int, dict[str, Any]]]:
    out: dict[int, dict[int, dict[str, Any]]] = {}
    for team_entry in lineups_payload:
        tid = safe_int(team_entry.get('team_id'))
        players: dict[int, dict[str, Any]] = {}
        for item in team_entry.get('lineup') or []:
            positions = item.get('positions') or []
            first = positions[0] if positions else {}
            players[safe_int(item.get('player_id'))] = {
                'player_id': safe_int(item.get('player_id')),
                'player_name': str(item.get('player_name') or ''),
                'position_id': safe_int(first.get('position_id')),
                'position_name': str(first.get('position') or ''),
                'jersey_number': item.get('jersey_number'),
            }
        out[tid] = players
    return out



def unique_players_by_position(players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_positions: set[int] = set()
    unique: list[dict[str, Any]] = []
    ordered = sorted(
        players,
        key=lambda item: (
            safe_int(item.get('position_id')),
            safe_int(item.get('jersey_number'), 999),
            safe_int(item.get('player_id')),
        ),
    )
    for item in ordered:
        position_id = safe_int(item.get('position_id'))
        if position_id <= 0 or position_id in seen_positions:
            continue
        seen_positions.add(position_id)
        unique.append(item)
    return unique


def build_formation_records(match_id: int, starting_xi: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for team_id, team_data in starting_xi.items():
        unique_players = unique_players_by_position(team_data['players'])
        if len(unique_players) < 10:
            continue
        records.append(
            {
                'task_type': 'soccer_formation',
                'source_id': f'statsbomb_formation_{match_id}_{team_id}',
                'match_id': match_id,
                'team_id': team_id,
                'team_name': team_data['team_name'],
                'formation': team_data['formation'],
                'players': unique_players,
            }
        )
    return records


def build_highlight_records(
    match_id: int,
    events: list[dict[str, Any]],
    starting_xi: dict[int, dict[str, Any]],
    position_map: dict[int, dict[int, dict[str, Any]]],
    highlight_stride: int,
    max_highlight_per_match: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    team_ids = list(starting_xi)
    if len(team_ids) != 2:
        return records
    opponent_by_team = {team_ids[0]: team_ids[1], team_ids[1]: team_ids[0]}

    for event in events:
        event_type = ((event.get('type') or {}).get('name') or '')
        if event_type not in ON_BALL_EVENT_TYPES:
            continue
        location = event.get('location') or []
        if len(location) < 2:
            continue
        team = event.get('team') or {}
        player = event.get('player') or {}
        team_id = safe_int(team.get('id'))
        player_id = safe_int(player.get('id'))
        if team_id not in starting_xi or player_id <= 0:
            continue
        starters = unique_players_by_position(starting_xi[team_id]['players'])
        opponent_starters = unique_players_by_position(starting_xi[opponent_by_team.get(team_id, -1)]['players']) if opponent_by_team.get(team_id, -1) in starting_xi else []
        starter_ids = {safe_int(item.get('player_id')) for item in starters}
        if player_id not in starter_ids:
            continue
        player_entry = (position_map.get(team_id) or {}).get(player_id)
        if not player_entry or safe_int(player_entry.get('position_id')) <= 0:
            continue
        opponent_id = opponent_by_team.get(team_id)
        if opponent_id is None or opponent_id not in starting_xi:
            continue
        eligible.append(
            {
                'task_type': 'soccer_ball_handler',
                'source_id': f"statsbomb_highlight_{match_id}_{event.get('id')}",
                'match_id': match_id,
                'team_id': team_id,
                'team_name': starting_xi[team_id]['team_name'],
                'opponent_team_id': opponent_id,
                'opponent_team_name': starting_xi[opponent_id]['team_name'],
                'formation': starting_xi[team_id]['formation'],
                'opponent_formation': starting_xi[opponent_id]['formation'],
                'players': starters,
                'opponent_players': opponent_starters,
                'ball_handler_player_id': player_id,
                'ball_handler_name': str(player.get('name') or ''),
                'event_type': event_type,
                'event_minute': safe_int(event.get('minute')),
                'event_second': safe_int(event.get('second')),
                'location': [float(location[0]), float(location[1])],
            }
        )

    if not eligible:
        return records
    sampled = eligible[:: max(1, highlight_stride)]
    if len(sampled) > max_highlight_per_match:
        rng.shuffle(sampled)
        sampled = sampled[:max_highlight_per_match]
    return sampled


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    statsbomb_root = Path(args.statsbomb_root)
    events_dir = statsbomb_root / 'events'
    lineups_dir = statsbomb_root / 'lineups'
    if not events_dir.exists() or not lineups_dir.exists():
        raise SystemExit('statsbomb-root must contain events/ and lineups/ subdirectories')

    records: list[dict[str, Any]] = []
    event_files = sorted(events_dir.glob('*.json'))
    for idx, event_path in enumerate(event_files, start=1):
        if args.max_matches > 0 and idx > args.max_matches:
            break
        match_id = safe_int(event_path.stem)
        lineup_path = lineups_dir / f'{match_id}.json'
        if not lineup_path.exists():
            continue
        events = load_json(event_path)
        lineups_payload = load_json(lineup_path)
        starting_xi = extract_starting_xi(events)
        if len(starting_xi) < 2:
            continue
        position_map = lineup_position_map(lineups_payload)
        records.extend(build_formation_records(match_id, starting_xi))
        if args.include_ball_handler:
            records.extend(
                build_highlight_records(
                    match_id,
                    events,
                    starting_xi,
                    position_map,
                    args.highlight_stride,
                    args.max_highlight_per_match,
                    rng,
                )
            )
        if idx % 50 == 0:
            print(f'[progress] {idx}/{len(event_files)} matches scanned, records={len(records)}')

    dump_jsonl(records, Path(args.output_jsonl))
    formation_count = sum(1 for record in records if record.get('task_type') == 'soccer_formation')
    highlight_count = sum(1 for record in records if record.get('task_type') == 'soccer_ball_handler')
    print(f'Wrote {len(records)} records to {args.output_jsonl}')
    print(f'formation_records={formation_count}')
    print(f'ball_handler_records={highlight_count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
