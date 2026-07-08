#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from xiangqi_utils import (
    STARTPOS_FEN,
    XiangqiBoard,
    apply_moves,
    coord_to_ucci,
    load_jsonl_records,
    parse_ucci_move,
    piece_descriptor,
    render_xiangqi_board,
)

INFO_RE = re.compile(r'multipv\s+(\d+).*(score\s+(cp|mate)\s+(-?\d+)).*pv\s+([a-i][0-9][a-i][0-9])')
BESTMOVE_RE = re.compile(r'bestmove\s+([a-i][0-9][a-i][0-9])')
MATE_SCORE = 100000


@dataclass
class Analysis:
    bestmove: str | None
    score_cp: int | None
    gap_cp: int | None


def render_kwargs_from_args(args) -> dict:
    renderer = getattr(args, 'renderer', 'auto')
    if renderer == 'auto':
        renderer = 'simple'
    return {
        'renderer': renderer,
        'xiangqi_setup_bin': args.xiangqi_setup_bin,
        'svg_converter': args.svg_converter,
        'board_theme': args.board_theme,
        'pieces_theme': args.pieces_theme,
        'annotations_theme': args.annotations_theme,
        'board_image_path': getattr(args, 'xiangqi_board_image', ''),
        'piece_assets_dir': getattr(args, 'xiangqi_piece_assets', ''),
    }


def resolve_engine_net(engine_path: str, explicit_net: str | None) -> str | None:
    if explicit_net:
        net = Path(explicit_net).expanduser().resolve()
        if not net.is_file():
            raise SystemExit(f'Engine net file not found: {net}')
        return str(net)

    engine = Path(engine_path).expanduser().resolve()
    candidates = [
        engine.parent / 'pikafish.nnue',
        engine.parent.parent / 'pikafish.nnue',
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    sibling_nets = sorted(engine.parent.glob('*.nnue'))
    if len(sibling_nets) == 1:
        return str(sibling_nets[0].resolve())

    return None


class UCIEngine:
    def __init__(self, path: str, net_path: str | None = None, threads: int = 0, hash_mb: int = 0):
        self.proc = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace', bufsize=1)
        self._send('uci')
        self._wait_for('uciok')
        if net_path:
            self._send(f'setoption name EvalFile value {net_path}')
        if threads and threads > 0:
            self._send(f'setoption name Threads value {threads}')
        if hash_mb and hash_mb > 0:
            self._send(f'setoption name Hash value {hash_mb}')
        self._send('setoption name MultiPV value 2')
        self._send('isready')
        self._wait_for('readyok')

    def _send(self, cmd: str):
        assert self.proc.stdin is not None
        self.proc.stdin.write(cmd + '\n')
        self.proc.stdin.flush()

    def _wait_for(self, token: str):
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            if token in line:
                return
        raise RuntimeError(f'Engine terminated before emitting {token}')

    def analyse(self, fen: str, depth: int) -> Analysis:
        assert self.proc.stdout is not None
        lines = {}
        self._send(f'position fen {fen}')
        self._send(f'go depth {depth}')
        bestmove = None
        for raw in self.proc.stdout:
            line = raw.strip()
            match = INFO_RE.search(line)
            if match:
                multipv = int(match.group(1))
                score_type = match.group(3)
                score_val = int(match.group(4))
                pv_move = match.group(5)
                score_cp = MATE_SCORE if score_type == 'mate' and score_val > 0 else (-MATE_SCORE if score_type == 'mate' else score_val)
                lines[multipv] = (score_cp, pv_move)
            bm = BESTMOVE_RE.search(line)
            if bm:
                bestmove = bm.group(1)
                break
        best_score = lines.get(1, (None, None))[0]
        second_score = lines.get(2, (None, None))[0]
        gap = None if best_score is None or second_score is None else best_score - second_score
        return Analysis(bestmove=bestmove, score_cp=best_score, gap_cp=gap)

    def quit(self):
        try:
            self._send('quit')
        except Exception:
            pass
        self.proc.terminate()
        self.proc.wait(timeout=2)


def stable(shallow: Analysis, deep: Analysis, min_gap: int, max_abs_score: int) -> bool:
    if not shallow.bestmove or not deep.bestmove:
        return False
    if shallow.bestmove != deep.bestmove:
        return False
    if shallow.score_cp is None or deep.score_cp is None or shallow.gap_cp is None or deep.gap_cp is None:
        return False
    if abs(shallow.score_cp) >= MATE_SCORE or abs(deep.score_cp) >= MATE_SCORE:
        return False
    if abs(shallow.score_cp) > max_abs_score or abs(deep.score_cp) > max_abs_score:
        return False
    if shallow.gap_cp < min_gap or deep.gap_cp < min_gap:
        return False
    return True


def limit_reached(count: int, limit: int) -> bool:
    return limit > 0 and count >= limit


def ensure_dirs(output_root: Path):
    dataset_name = output_root.name
    editing_dir = output_root / 'editing'
    gt_dir = output_root / 'gt'
    editing_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)
    return dataset_name, editing_dir, gt_dir


def export_json(items: list[dict], output_root: Path):
    json_path = output_root / f'{output_root.name}.json'
    with json_path.open('w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def open_stream_json(output_root: Path):
    json_path = output_root / f'{output_root.name}.json'
    handle = json_path.open('w', encoding='utf-8')
    handle.write('[\n')
    return handle


def append_stream_json(handle, item: dict, first: bool) -> bool:
    if not first:
        handle.write(',\n')
    handle.write(json.dumps(item, ensure_ascii=False, indent=2))
    handle.flush()
    return False


def close_stream_json(handle) -> None:
    handle.write('\n]\n')
    handle.close()


def normalize_opening_name(name: str) -> str:
    return ' '.join(str(name or '').split())


def matches_opening(opening: str, filters: list[str]) -> bool:
    if not filters:
        return True
    opening_l = opening.lower()
    return any(token.lower() in opening_l for token in filters)


def most_common_prefix(entries: list[dict]) -> tuple[list[str], dict, int]:
    if not entries:
        return [], {}, 0
    prefix_counter = Counter(tuple(entry['prefix']) for entry in entries)
    best_prefix, best_count = max(prefix_counter.items(), key=lambda item: (item[1], item[0]))
    representative = next(entry['record'] for entry in entries if tuple(entry['prefix']) == best_prefix)
    return list(best_prefix), representative, best_count


def build_opening_dataset(args) -> int:
    records = load_jsonl_records(args.input)
    render_kwargs = render_kwargs_from_args(args)
    output_root = Path(args.output_root)
    dataset_name, editing_dir, gt_dir = ensure_dirs(output_root)

    grouped: dict[str, list[dict]] = {}
    for record in records:
        opening = normalize_opening_name(record.get('opening') or record.get('opening_name') or '')
        moves = list(record.get('moves_ucci') or [])
        required_plies = max(args.min_plies, args.plies)
        if not opening or not matches_opening(opening, args.openings) or len(moves) < required_plies:
            continue
        prefix = moves[: args.plies]
        if not prefix:
            continue
        grouped.setdefault(opening, []).append({'record': record, 'prefix': prefix})

    canonical_samples: list[dict] = []
    for opening in sorted(grouped):
        entries = grouped[opening]
        canonical_prefix, representative_record, canonical_count = most_common_prefix(entries)
        if not canonical_prefix:
            continue
        canonical_samples.append(
            {
                'opening': opening,
                'record': representative_record,
                'canonical_prefix': canonical_prefix,
                'source_count': len(entries),
                'canonical_count': canonical_count,
            }
        )

    if not canonical_samples:
        raise SystemExit('No xiangqi opening samples generated.')

    if args.max_samples > 0:
        canonical_samples = canonical_samples[: args.max_samples]

    items = []
    for sample in canonical_samples:
        record = sample['record']
        before_board = XiangqiBoard(record.get('initial_fen') or STARTPOS_FEN)
        after_board = apply_moves(before_board, sample['canonical_prefix'], max_plies=len(sample['canonical_prefix']))
        opening_zh = sample['opening']
        opening_en = str(record.get('opening_en') or '').strip()
        opening_text = opening_en or opening_zh
        idx = len(items) + 1
        render_xiangqi_board(before_board, image_size=args.image_size, **render_kwargs).save(editing_dir / f'{idx}_before.png')
        render_xiangqi_board(after_board, image_size=args.image_size, **render_kwargs).save(gt_dir / f'{idx}_after.png')
        items.append({'text': f"Edit the Chinese chess diagram to show the {opening_text}.", 'task_id': f'task_{idx}', 'image_path': f'{dataset_name}/editing/{idx}_before.png', 'gt': f'{dataset_name}/gt/{idx}_after.png', 'sub_task': 'Chinese Chess', 'meta': {'opening': opening_zh, 'opening_en': opening_en, 'plies_used': len(sample['canonical_prefix']), 'requested_plies': args.plies, 'source_count': sample['source_count'], 'canonical_count': sample['canonical_count'], 'canonical_prefix_moves_ucci': sample['canonical_prefix'], 'source_id': record.get('source_id', '')}})

    export_json(items, output_root)
    print(f'Exported {len(items)} xiangqi opening samples to {output_root}')
    return 0


def build_legal_moves_dataset(args) -> int:
    records = load_jsonl_records(args.input)
    render_kwargs = render_kwargs_from_args(args)
    output_root = Path(args.output_root)
    dataset_name, editing_dir, gt_dir = ensure_dirs(output_root)
    written = 0
    first = True
    handle = open_stream_json(output_root)
    try:
        for record in records:
            board = XiangqiBoard(record.get('initial_fen') or STARTPOS_FEN)
            boards: list[tuple[int, XiangqiBoard]] = []
            for ply, mv in enumerate(record.get('moves_ucci') or [], start=1):
                board.apply_ucci(mv)
                if args.min_ply <= ply <= args.max_ply:
                    boards.append((ply, board.copy()))
                if ply > args.max_ply:
                    break
            for ply, board in boards:
                for r, c, piece in board.side_pieces(board.turn):
                    legal = board.legal_moves_from(r, c)
                    if not (args.min_targets <= len(legal) <= args.max_targets):
                        continue
                    desc = piece_descriptor(board, r, c)
                    targets = [(mv.to_row, mv.to_col) for mv in legal]
                    written += 1
                    render_xiangqi_board(
                        board,
                        image_size=args.image_size,
                        **render_kwargs,
                    ).save(editing_dir / f'{written}_before.png')
                    render_xiangqi_board(
                        board,
                        image_size=args.image_size,
                        marker_squares=targets,
                        marker_style='green',
                        **render_kwargs,
                    ).save(gt_dir / f'{written}_after.png')
                    item = {'text': f'Mark the legal moves of the {desc[4:] if desc.startswith("the ") else desc} with green dots.', 'task_id': f'task_{written}', 'image_path': f'{dataset_name}/editing/{written}_before.png', 'gt': f'{dataset_name}/gt/{written}_after.png', 'sub_task': 'Chinese Chess', 'meta': {'piece': desc, 'piece_code': piece, 'piece_square': coord_to_ucci(r, c), 'num_targets': len(targets), 'targets': [mv.to_ucci()[2:] for mv in legal], 'fen': board.fen(), 'ply': ply, 'source_id': record.get('source_id', '')}}
                    first = append_stream_json(handle, item, first)
                    if written % 50 == 0:
                        print(f'Wrote {written} xiangqi legal-move samples to {output_root}...')
                    if limit_reached(written, args.max_samples):
                        break
                if limit_reached(written, args.max_samples):
                    break
            if limit_reached(written, args.max_samples):
                break
    finally:
        close_stream_json(handle)
    if written == 0:
        raise SystemExit('No xiangqi legal-move samples generated.')
    print(f'Exported {written} xiangqi legal-move samples to {output_root}')
    return 0


def build_bestmove_dataset(args) -> int:
    if not args.engine:
        raise SystemExit('--engine is required for xiangqi bestmove')
    if args.verify_depth <= args.depth:
        raise SystemExit('--verify-depth must be greater than --depth')
    records = load_jsonl_records(args.input)
    render_kwargs = render_kwargs_from_args(args)
    output_root = Path(args.output_root)
    dataset_name, editing_dir, gt_dir = ensure_dirs(output_root)
    written = 0
    checked_positions = 0
    first = True
    net_path = resolve_engine_net(args.engine, getattr(args, 'engine_net', None))
    engine = UCIEngine(args.engine, net_path=net_path, threads=getattr(args, 'engine_threads', 0), hash_mb=getattr(args, 'engine_hash', 0))
    handle = open_stream_json(output_root)
    try:
        for record in records:
            board = XiangqiBoard(record.get('initial_fen') or STARTPOS_FEN)
            boards: list[tuple[int, XiangqiBoard]] = []
            for ply, mv in enumerate(record.get('moves_ucci') or [], start=1):
                board.apply_ucci(mv)
                if args.min_ply <= ply <= args.max_ply:
                    boards.append((ply, board.copy()))
                if ply > args.max_ply:
                    break
            for ply, board in boards:
                checked_positions += 1
                shallow = engine.analyse(board.fen(), args.depth)
                deep = engine.analyse(board.fen(), args.verify_depth)
                if checked_positions % 100 == 0:
                    print(f'Checked {checked_positions} xiangqi positions, kept {written} best-move samples...')
                if not stable(shallow, deep, args.min_score_gap_cp, args.max_abs_score_cp):
                    continue
                best = parse_ucci_move(deep.bestmove)
                side = 'Red' if board.turn == 'red' else 'Black'
                after_board = board.copy()
                after_board.apply_move(best)
                written += 1
                render_xiangqi_board(
                    board,
                    image_size=args.image_size,
                    **render_kwargs,
                ).save(editing_dir / f'{written}_before.png')
                render_xiangqi_board(
                    after_board,
                    image_size=args.image_size,
                    **render_kwargs,
                ).save(gt_dir / f'{written}_after.png')
                item = {'text': f"Edit the Chinese chess diagram by making {side}'s best next move.", 'task_id': f'task_{written}', 'image_path': f'{dataset_name}/editing/{written}_before.png', 'gt': f'{dataset_name}/gt/{written}_after.png', 'sub_task': 'Chinese Chess', 'meta': {'best_move_ucci': deep.bestmove, 'side_to_move': side, 'fen': board.fen(), 'after_fen': after_board.fen(), 'ply': ply, 'shallow_score_cp': shallow.score_cp, 'deep_score_cp': deep.score_cp, 'shallow_gap_cp': shallow.gap_cp, 'deep_gap_cp': deep.gap_cp, 'source_id': record.get('source_id', '')}}
                first = append_stream_json(handle, item, first)
                if written % 50 == 0:
                    print(f'Wrote {written} xiangqi best-move samples to {output_root}...')
                if limit_reached(written, args.max_samples):
                    break
            if limit_reached(written, args.max_samples):
                break
    finally:
        close_stream_json(handle)
        engine.quit()
    if written == 0:
        raise SystemExit('No xiangqi best-move samples generated.')
    print(f'Exported {written} xiangqi best-move samples to {output_root}')
    return 0
