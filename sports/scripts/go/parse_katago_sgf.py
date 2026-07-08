#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from go_utils import row_col_to_gtp, sgf_coord_to_row_col


@dataclass
class SgfNode:
    props: dict[str, list[str]] = field(default_factory=dict)
    children: list["SgfNode"] = field(default_factory=list)

    def move(self) -> tuple[str, str] | None:
        for color in ("B", "W"):
            values = self.props.get(color, [])
            if values:
                return color, values[0]
        return None


class SgfParser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def parse_collection(self) -> list[SgfNode]:
        trees: list[SgfNode] = []
        self._skip_ws()
        while self.pos < len(self.text):
            if self.text[self.pos] == '(':
                tree = self._parse_tree()
                if tree is not None:
                    trees.append(tree)
            else:
                self.pos += 1
            self._skip_ws()
        return trees

    def _skip_ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def _parse_tree(self) -> SgfNode | None:
        self._expect('(')
        nodes: list[SgfNode] = []
        self._skip_ws()
        while self.pos < len(self.text) and self.text[self.pos] == ';':
            nodes.append(self._parse_node())
            self._skip_ws()

        if not nodes:
            while self.pos < len(self.text) and self.text[self.pos] != ')':
                self.pos += 1
            self._expect(')')
            return None

        for idx in range(len(nodes) - 1):
            nodes[idx].children.append(nodes[idx + 1])

        last = nodes[-1]
        self._skip_ws()
        while self.pos < len(self.text) and self.text[self.pos] == '(':
            child = self._parse_tree()
            if child is not None:
                last.children.append(child)
            self._skip_ws()

        self._expect(')')
        return nodes[0]

    def _parse_node(self) -> SgfNode:
        self._expect(';')
        props: dict[str, list[str]] = {}
        self._skip_ws()
        while self.pos < len(self.text):
            if self.text[self.pos] in ';()':
                break
            if not self.text[self.pos].isalpha():
                self.pos += 1
                continue
            ident = self._parse_ident()
            values = self._parse_values()
            props[ident] = values
            self._skip_ws()
        return SgfNode(props=props)

    def _parse_ident(self) -> str:
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos].isalpha():
            self.pos += 1
        return self.text[start:self.pos]

    def _parse_values(self) -> list[str]:
        values: list[str] = []
        self._skip_ws()
        while self.pos < len(self.text) and self.text[self.pos] == '[':
            self.pos += 1
            buf: list[str] = []
            while self.pos < len(self.text):
                ch = self.text[self.pos]
                if ch == '\\' and self.pos + 1 < len(self.text):
                    buf.append(self.text[self.pos + 1])
                    self.pos += 2
                    continue
                if ch == ']':
                    self.pos += 1
                    break
                buf.append(ch)
                self.pos += 1
            values.append(''.join(buf))
            self._skip_ws()
        return values

    def _expect(self, token: str) -> None:
        if self.pos >= len(self.text) or self.text[self.pos] != token:
            raise ValueError(f"Expected '{token}' at position {self.pos}")
        self.pos += 1


class GoBoard:
    def __init__(self, size: int):
        self.size = size
        self.board = [['.' for _ in range(size)] for _ in range(size)]

    def setup(self, black: list[str], white: list[str]) -> None:
        for coord in black:
            if coord:
                row, col = sgf_coord_to_row_col(coord, self.size)
                self.board[row][col] = 'B'
        for coord in white:
            if coord:
                row, col = sgf_coord_to_row_col(coord, self.size)
                self.board[row][col] = 'W'

    def neighbors(self, row: int, col: int):
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = row + dr, col + dc
            if 0 <= nr < self.size and 0 <= nc < self.size:
                yield nr, nc

    def group_and_liberties(self, row: int, col: int):
        color = self.board[row][col]
        stack = [(row, col)]
        visited = set()
        group = set()
        liberties = set()
        while stack:
            r, c = stack.pop()
            if (r, c) in visited:
                continue
            visited.add((r, c))
            group.add((r, c))
            for nr, nc in self.neighbors(r, c):
                cell = self.board[nr][nc]
                if cell == '.':
                    liberties.add((nr, nc))
                elif cell == color and (nr, nc) not in visited:
                    stack.append((nr, nc))
        return group, liberties

    def remove_group(self, group):
        for r, c in group:
            self.board[r][c] = '.'

    def play(self, color: str, coord: str) -> None:
        if coord == '':
            return
        row, col = sgf_coord_to_row_col(coord, self.size)
        self.board[row][col] = color
        opp = 'W' if color == 'B' else 'B'
        for nr, nc in list(self.neighbors(row, col)):
            if self.board[nr][nc] != opp:
                continue
            group, liberties = self.group_and_liberties(nr, nc)
            if not liberties:
                self.remove_group(group)
        group, liberties = self.group_and_liberties(row, col)
        if not liberties:
            self.remove_group(group)

    def stones(self) -> tuple[list[str], list[str]]:
        black, white = [], []
        for row in range(self.size):
            for col in range(self.size):
                if self.board[row][col] == 'B':
                    black.append(row_col_to_gtp(row, col, self.size))
                elif self.board[row][col] == 'W':
                    white.append(row_col_to_gtp(row, col, self.size))
        return black, white


class ProgressPrinter:
    def __init__(self, total_files: int | None, enabled: bool):
        self.total_files = total_files
        self.enabled = enabled
        self.start_time = time.time()
        self.last_render = 0.0

    def update(self, files_done: int, games_done: int, samples_done: int, current_file: Path | None = None, force: bool = False) -> None:
        if not self.enabled:
            return
        now = time.time()
        if not force and now - self.last_render < 0.2:
            return
        self.last_render = now
        elapsed = max(now - self.start_time, 1e-6)
        rate = files_done / elapsed if files_done > 0 else 0.0
        if self.total_files is not None and self.total_files > 0:
            ratio = min(files_done / self.total_files, 1.0)
            bar_width = 24
            filled = int(ratio * bar_width)
            bar = '#' * filled + '-' * (bar_width - filled)
            progress = f'[{bar}] {files_done}/{self.total_files} files'
        else:
            progress = f'{files_done} files'
        current_name = current_file.name if current_file is not None else '-'
        message = f'\r{progress} | {games_done} games | {samples_done} samples | {rate:.1f} files/s | {current_name[:60]}'
        sys.stderr.write(message)
        sys.stderr.flush()

    def finish(self, files_done: int, games_done: int, samples_done: int) -> None:
        if not self.enabled:
            return
        self.update(files_done, games_done, samples_done, force=True)
        sys.stderr.write('\n')
        sys.stderr.flush()


def mainline_nodes(root: SgfNode) -> list[SgfNode]:
    nodes = [root]
    current = root
    while current.children:
        current = current.children[0]
        nodes.append(current)
    return nodes


def iter_target_files(path: Path, max_files: int = 0) -> Iterator[Path]:
    count = 0
    if path.is_dir():
        for target in sorted(p for p in path.rglob('*') if p.is_file() and p.suffix.lower() in {'.sgf', '.sgfs'}):
            yield target
            count += 1
            if max_files > 0 and count >= max_files:
                break
    else:
        yield path


def count_target_files(path: Path, max_files: int = 0) -> int:
    if path.is_dir():
        count = 0
        for p in path.rglob('*'):
            if p.is_file() and p.suffix.lower() in {'.sgf', '.sgfs'}:
                count += 1
                if max_files > 0 and count >= max_files:
                    break
        return count
    return 1


def iter_trees(path: Path, max_files: int = 0) -> Iterator[tuple[Path, SgfNode]]:
    for target in iter_target_files(path, max_files=max_files):
        text = target.read_text(encoding='utf-8', errors='replace')
        parser = SgfParser(text)
        for tree in parser.parse_collection():
            yield target, tree


def category_from_path(path: Path) -> str:
    lower = path.as_posix().lower()
    if 'opening' in lower or 'joseki' in lower or 'fuseki' in lower:
        return 'Opening Problem'
    if 'life' in lower or 'death' in lower or 'tsumego' in lower:
        return 'Life and Death'
    if 'tesuji' in lower:
        return 'Tesuji'
    if 'sgfpos' in lower:
        return 'KataGo SgfPos'
    return 'KataGo Position'


def auto_text(to_play: str) -> str:
    side = 'Black' if to_play == 'black' else 'White'
    return f'A Go problem. {side} to play. Please find the crucial first move and mark it with "1" on the board.'


def sgf_to_gtp_or_pass(coord: str, size: int) -> str:
    if not coord:
        return 'pass'
    row, col = sgf_coord_to_row_col(coord, size)
    return row_col_to_gtp(row, col, size)


def parse_board_size(root: SgfNode) -> int | None:
    raw = root.props.get('SZ', ['19'])[0].strip()
    if ':' in raw:
        parts = raw.split(':', 1)
        if len(parts) != 2:
            return None
        try:
            width = int(parts[0])
            height = int(parts[1])
        except ValueError:
            return None
        if width != height:
            return None
        return width
    try:
        return int(raw)
    except ValueError:
        return None


def extract_records(source_path: Path, root: SgfNode, min_ply: int, max_ply: int, sample_every: int, source_prefix: str) -> list[dict]:
    size = parse_board_size(root)
    if size is None or size != 19:
        return []
    initial_black = [coord for coord in root.props.get('AB', []) if coord]
    initial_white = [coord for coord in root.props.get('AW', []) if coord]
    initial_black_gtp = [sgf_to_gtp_or_pass(coord, size) for coord in initial_black]
    initial_white_gtp = [sgf_to_gtp_or_pass(coord, size) for coord in initial_white]

    board = GoBoard(size)
    board.setup(initial_black, initial_white)
    nodes = mainline_nodes(root)
    move_nodes = []
    for node in nodes[1:]:
        mv = node.move()
        if mv is not None:
            move_nodes.append(mv)

    records: list[dict] = []
    current_ply = 0
    moves_gtp_history: list[list[str]] = []
    for color, move_coord in move_nodes:
        if move_coord and min_ply <= current_ply <= max_ply and ((current_ply - min_ply) % sample_every == 0):
            black_stones, white_stones = board.stones()
            to_play = 'black' if color == 'B' else 'white'
            row, col = sgf_coord_to_row_col(move_coord, size)
            source_id = f'{source_prefix}_{current_ply}_{len(records) + 1}'
            records.append(
                {
                    'source_id': source_id,
                    'size': size,
                    'category': category_from_path(source_path),
                    'to_play': to_play,
                    'answer': row_col_to_gtp(row, col, size),
                    'black_stones': black_stones,
                    'white_stones': white_stones,
                    'text': auto_text(to_play),
                    'meta': {
                        'source_path': source_path.as_posix(),
                        'ply': current_ply,
                        'next_move_sgf': move_coord,
                        'next_move_color': color,
                        'initial_black_stones': initial_black_gtp,
                        'initial_white_stones': initial_white_gtp,
                        'komi': root.props.get('KM', [''])[0],
                        'rules': root.props.get('RU', [''])[0],
                        'event': root.props.get('EV', [''])[0],
                        'game_name': root.props.get('GN', [''])[0],
                        'moves_gtp_history': moves_gtp_history[:],
                    },
                }
            )
        board.play(color, move_coord)
        moves_gtp_history.append([color, sgf_to_gtp_or_pass(move_coord, size)])
        current_ply += 1
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Parse KataGo training SGF into JSONL for Go dataset building.')
    parser.add_argument('--input', required=True, help='SGF file or directory.')
    parser.add_argument('--output-jsonl', required=True)
    parser.add_argument('--min-ply', type=int, default=20)
    parser.add_argument('--max-ply', type=int, default=120)
    parser.add_argument('--sample-every', type=int, default=10)
    parser.add_argument('--max-samples', type=int, default=0, help='0 means no limit.')
    parser.add_argument('--max-files', type=int, default=0, help='Only scan the first N SGF files. 0 means no limit.')
    parser.add_argument('--skip-count', action='store_true', help='Do not pre-count total SGF files before parsing.')
    parser.add_argument('--no-progress', action='store_true', help='Disable progress output.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    total_files = None if args.skip_count else count_target_files(input_path, max_files=args.max_files)
    progress = ProgressPrinter(total_files=total_files, enabled=not args.no_progress)

    records: list[dict] = []
    parsed_games = 0
    files_done = 0
    last_file: Path | None = None
    skipped_reasons: Counter[str] = Counter()

    for game_idx, (source_path, root) in enumerate(iter_trees(input_path, max_files=args.max_files), start=1):
        if source_path != last_file:
            files_done += 1
            last_file = source_path
            progress.update(files_done, parsed_games, len(records), current_file=source_path)

        size = parse_board_size(root)
        if size is None:
            skipped_reasons['invalid_board_size'] += 1
            parsed_games += 1
            continue
        if size != 19:
            skipped_reasons[f'unsupported_board_size_{size}'] += 1
            parsed_games += 1
            continue

        source_prefix = f'{source_path.stem}_{game_idx}'
        for record in extract_records(source_path, root, args.min_ply, args.max_ply, args.sample_every, source_prefix):
            records.append(record)
            progress.update(files_done, parsed_games, len(records), current_file=source_path)
            if args.max_samples and len(records) >= args.max_samples:
                break
        parsed_games += 1
        progress.update(files_done, parsed_games, len(records), current_file=source_path)
        if args.max_samples and len(records) >= args.max_samples:
            break

    progress.finish(files_done, parsed_games, len(records))

    if not records:
        summary = ', '.join(f'{key}={value}' for key, value in skipped_reasons.most_common()) if skipped_reasons else 'none'
        raise SystemExit(f'No valid KataGo SGF records were parsed. Skip reasons: {summary}')

    output = Path(args.output_jsonl)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    summary = ', '.join(f'{key}={value}' for key, value in skipped_reasons.most_common()) if skipped_reasons else 'none'
    print(f'Parsed {len(records)} KataGo-derived records from {parsed_games} SGF trees to {output}. Skip reasons: {summary}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

