#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine
import chess.pgn
from PIL import Image, ImageDraw, ImageFont, ImageOps

try:
    import chess.svg as chess_svg
except Exception:
    chess_svg = None

try:
    import cairosvg
except Exception:
    cairosvg = None

DEFAULT_BOARD_THEME = 'random'
CHESS_THEMES = {
    'green_classic': {
        'light_square': '#EEEED2',
        'dark_square': '#769656',
        'coord_color': '#6B8E5E',
        'border_color': '#FFFFFF',
        'highlight_fill': '#6FCF97',
        'highlight_outline': '#2E8B57',
        'arrow_color': '#2E8B57',
        'arrow_alpha': 'CC',
        'src_fill': '#A9DFBF',
        'dst_fill': '#58D68D',
    },
    'wood_classic': {
        'light_square': '#F2DFC2',
        'dark_square': '#A7743A',
        'coord_color': '#F7F1E3',
        'border_color': '#8B5A2B',
        'highlight_fill': '#78C679',
        'highlight_outline': '#2E8B57',
        'arrow_color': '#2E8B57',
        'arrow_alpha': 'CC',
        'src_fill': '#B7E4C7',
        'dst_fill': '#52B788',
    },
    'walnut': {
        'light_square': '#E7D3B3',
        'dark_square': '#7A5230',
        'coord_color': '#F5E9D4',
        'border_color': '#6B4423',
        'highlight_fill': '#74C69D',
        'highlight_outline': '#2D6A4F',
        'arrow_color': '#2D6A4F',
        'arrow_alpha': 'CC',
        'src_fill': '#B7E4C7',
        'dst_fill': '#40916C',
    },
    'blue_tournament': {
        'light_square': '#EAEFF7',
        'dark_square': '#6F86B6',
        'coord_color': '#445A80',
        'border_color': '#FFFFFF',
        'highlight_fill': '#74C69D',
        'highlight_outline': '#2D6A4F',
        'arrow_color': '#2D6A4F',
        'arrow_alpha': 'CC',
        'src_fill': '#B7E4C7',
        'dst_fill': '#52B788',
    },
}
WHITE_PIECE_FILL = '#F8F8F8'
WHITE_PIECE_OUTLINE = '#555555'
BLACK_PIECE_FILL = '#333333'
BLACK_PIECE_OUTLINE = '#111111'
LABEL_COLOR = '#222222'
MATE_CP = 100000

PIECE_LABELS = {k: k.upper() for k in ['P', 'N', 'B', 'R', 'Q', 'K', 'p', 'n', 'b', 'r', 'q', 'k']}
UNICODE_PIECES = {
    'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
    'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚',
}
PIECE_NAMES = {
    chess.PAWN: 'pawn',
    chess.KNIGHT: 'knight',
    chess.BISHOP: 'bishop',
    chess.ROOK: 'rook',
    chess.QUEEN: 'queen',
    chess.KING: 'king',
}
ALL_PIECE_TYPES = [
    chess.PAWN,
    chess.KNIGHT,
    chess.BISHOP,
    chess.ROOK,
    chess.QUEEN,
    chess.KING,
]


@dataclass
class OpeningSample:
    opening: str
    game: chess.pgn.Game


@dataclass
class LegalSample:
    board: chess.Board
    piece_square: int
    piece_type: int
    legal_targets: list[int]


@dataclass
class BestMoveSample:
    board: chess.Board
    best_move: chess.Move
    side_to_move: str
    shallow_score_cp: int | None
    deep_score_cp: int | None
    shallow_gap_cp: int | None
    deep_gap_cp: int | None
    shallow_depth: int
    deep_depth: int


@dataclass
class AnalysisResult:
    best_move: chess.Move | None
    best_score_cp: int | None
    score_gap_cp: int | None


def iter_games(path: Path):
    with path.open('r', encoding='utf-8', errors='replace') as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            yield game


def count_plies(game: chess.pgn.Game) -> int:
    return sum(1 for _ in game.mainline_moves())


def normalize_opening_name(name: str) -> str:
    return ' '.join(name.split())


def matches_opening(opening: str, filters: list[str]) -> bool:
    if not filters:
        return True
    opening_l = opening.lower()
    return any(token.lower() in opening_l for token in filters)


def make_board_after_plies(game: chess.pgn.Game, plies: int) -> chess.Board:
    board = game.board()
    for idx, move in enumerate(game.mainline_moves(), start=1):
        board.push(move)
        if idx >= plies:
            break
    return board


def opening_move_prefix(game: chess.pgn.Game, plies: int) -> list[str]:
    moves: list[str] = []
    for idx, move in enumerate(game.mainline_moves(), start=1):
        moves.append(move.uci())
        if idx >= plies:
            break
    return moves


def longest_common_prefix(sequences: list[list[str]]) -> list[str]:
    if not sequences:
        return []
    prefix = list(sequences[0])
    for sequence in sequences[1:]:
        limit = min(len(prefix), len(sequence))
        idx = 0
        while idx < limit and prefix[idx] == sequence[idx]:
            idx += 1
        prefix = prefix[:idx]
        if not prefix:
            break
    return prefix



def choose_theme(board_theme: str | None, rng: random.Random | None = None) -> tuple[str, dict[str, str]]:
    requested = (board_theme or DEFAULT_BOARD_THEME).strip().lower()
    if requested in ('', 'random'):
        theme_name = (rng or random).choice(['green_classic', 'wood_classic'])
        return theme_name, CHESS_THEMES[theme_name]
    if requested not in CHESS_THEMES:
        raise SystemExit(f'Unknown chess board theme: {board_theme}. Available: {", ".join(sorted(CHESS_THEMES))}, random')
    return requested, CHESS_THEMES[requested]


_TEXTURE_CACHE: dict[tuple[str, int], Image.Image] = {}


def load_square_texture(path_str: str, square_px: int) -> Image.Image:
    key = (path_str, square_px)
    cached = _TEXTURE_CACHE.get(key)
    if cached is not None:
        return cached
    path = Path(path_str)
    if not path.is_file():
        raise SystemExit(f'Chess texture not found: {path}')
    image = Image.open(path).convert('RGB')
    image = ImageOps.fit(image, (square_px, square_px), method=Image.Resampling.LANCZOS)
    _TEXTURE_CACHE[key] = image
    return image


def most_common_prefix(entries: list[tuple[list[str], chess.pgn.Game]]) -> tuple[list[str], chess.pgn.Game | None, int]:
    if not entries:
        return [], None, 0
    counter = Counter(tuple(prefix) for prefix, _ in entries if prefix)
    if not counter:
        return [], None, 0
    canonical_tuple, canonical_count = counter.most_common(1)[0]
    canonical_prefix = list(canonical_tuple)
    representative_game = next((game for prefix, game in entries if prefix == canonical_prefix), None)
    return canonical_prefix, representative_game, canonical_count

def board_from_uci_prefix(moves: list[str]) -> chess.Board:
    board = chess.Board()
    for uci in moves:
        board.push(chess.Move.from_uci(uci))
    return board


def load_font(size: int):
    for candidate in ['DejaVuSans-Bold.ttf', 'arial.ttf', 'LiberationSans-Bold.ttf']:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_centered_text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font, fill: str):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((xy[0] - w / 2, xy[1] - h / 2), text, font=font, fill=fill)


def square_geometry(square_idx: int, image_size: int):
    margin = 0
    board_size = image_size
    square = board_size / 8.0
    file = chess.square_file(square_idx)
    rank_from_white = chess.square_rank(square_idx)
    rank = 7 - rank_from_white
    x0 = margin + file * square
    y0 = margin + rank * square
    x1 = x0 + square
    y1 = y0 + square
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    return margin, square, x0, y0, x1, y1, cx, cy, board_size


def render_board_simple(board: chess.Board, image_size: int, theme: dict[str, str], highlighted_squares: list[int] | None = None, best_move: chess.Move | None = None, light_square_texture: str = '', dark_square_texture: str = '') -> Image.Image:
    highlighted = set(highlighted_squares or [])
    margin = 0
    board_size = image_size
    square = board_size / 8.0
    canvas = Image.new('RGBA', (image_size, image_size), theme['light_square'])
    draw = ImageDraw.Draw(canvas, 'RGBA')
    square_px = max(1, int(round(square)))
    light_texture = load_square_texture(light_square_texture, square_px) if light_square_texture else None
    dark_texture = load_square_texture(dark_square_texture, square_px) if dark_square_texture else None
    coord_font = load_font(max(14, int(square * 0.18)))
    piece_font = load_font(max(28, int(square * 0.8)))

    src = best_move.from_square if best_move else None
    dst = best_move.to_square if best_move else None

    for rank in range(8):
        for file in range(8):
            sq = chess.square(file, 7 - rank)
            x0 = margin + file * square
            y0 = margin + rank * square
            x1 = x0 + square
            y1 = y0 + square
            is_light = (rank + file) % 2 == 0
            color = theme['light_square'] if is_light else theme['dark_square']
            box = (int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)))
            texture = light_texture if is_light else dark_texture
            if texture is not None:
                box_w = box[2] - box[0]
                box_h = box[3] - box[1]
                tile = texture
                if tile.size != (box_w, box_h):
                    tile = texture.resize((box_w, box_h), Image.Resampling.LANCZOS)
                canvas.paste(tile, box)
            else:
                draw.rectangle(box, fill=color)
            if sq in highlighted:
                pad = square * 0.24
                draw.rectangle(box, fill=(111, 207, 151, 110))
            if sq == src:
                inset = max(3, int(square * 0.08))
                draw.rectangle([x0 + inset, y0 + inset, x1 - inset, y1 - inset], outline=theme['src_fill'], width=max(3, int(square * 0.06)))
            if sq == dst:
                pad = square * 0.22
                draw.ellipse([x0 + pad, y0 + pad, x1 - pad, y1 - pad], fill=theme['dst_fill'], outline=theme['arrow_color'], width=max(2, int(square * 0.05)))

    for file in range(8):
        x0 = margin + file * square
        draw.text((x0 + square * 0.82, image_size - square * 0.18), chr(ord('a') + file), font=coord_font, fill=theme['coord_color'], anchor='mm')
    for rank in range(8):
        y0 = margin + rank * square
        draw.text((square * 0.12, y0 + square * 0.14), str(8 - rank), font=coord_font, fill=theme['coord_color'], anchor='mm')

    if best_move is not None:
        _, _, _, _, _, _, sx, sy, _ = square_geometry(best_move.from_square, image_size)
        _, _, _, _, _, _, tx, ty, _ = square_geometry(best_move.to_square, image_size)
        draw.line([sx, sy, tx, ty], fill=theme['arrow_color'], width=max(4, int(square * 0.11)))
        angle = math.atan2(ty - sy, tx - sx)
        arrow_len = square * 0.28
        left = (tx - arrow_len * math.cos(angle - math.pi / 6), ty - arrow_len * math.sin(angle - math.pi / 6))
        right = (tx - arrow_len * math.cos(angle + math.pi / 6), ty - arrow_len * math.sin(angle + math.pi / 6))
        draw.polygon([(tx, ty), left, right], fill=theme['arrow_color'])

    for square_idx, piece in board.piece_map().items():
        file = chess.square_file(square_idx)
        rank_from_white = chess.square_rank(square_idx)
        rank = 7 - rank_from_white
        x0 = margin + file * square
        y0 = margin + rank * square
        cx = x0 + square / 2
        cy = y0 + square / 2
        glyph = UNICODE_PIECES[piece.symbol()]
        if piece.color == chess.WHITE:
            fill = '#F5F5F5'
            stroke_fill = '#555555'
        else:
            fill = '#4A4A4A'
            stroke_fill = '#262626'
        draw.text((cx, cy - square * 0.03), glyph, font=piece_font, fill=fill, anchor='mm', stroke_width=max(1, int(square * 0.03)), stroke_fill=stroke_fill)

    return canvas.convert('RGB')


def render_board_svg(board: chess.Board, image_size: int, theme: dict[str, str], highlighted_squares: list[int] | None = None, best_move: chess.Move | None = None) -> Image.Image:
    if chess_svg is None or cairosvg is None:
        raise RuntimeError('SVG renderer requires python-chess SVG support and cairosvg.')
    arrows = []
    fill = {sq: theme['highlight_fill'] for sq in highlighted_squares or []}
    if best_move is not None:
        arrows = [chess_svg.Arrow(best_move.from_square, best_move.to_square, color=theme['arrow_color'] + theme['arrow_alpha'])]
        fill.update({best_move.from_square: theme['src_fill'], best_move.to_square: theme['dst_fill']})
    svg = chess_svg.board(
        board=board,
        size=image_size,
        coordinates=True,
        arrows=arrows,
        fill=fill,
        colors={'square light': theme['light_square'], 'square dark': theme['dark_square'], 'coord': theme['coord_color'], 'outer border': theme['border_color'], 'margin': theme['border_color']},
    )
    png_bytes = cairosvg.svg2png(bytestring=svg.encode('utf-8'))
    return Image.open(io.BytesIO(png_bytes)).convert('RGB')


def resolve_renderer(renderer: str, theme_name: str) -> str:
    if renderer != 'auto':
        return renderer
    if theme_name == 'wood_classic':
        return 'simple'
    if chess_svg is not None and cairosvg is not None:
        return 'svg'
    return 'simple'


def render_board(board: chess.Board, image_size: int, renderer: str, theme: dict[str, str], highlighted_squares: list[int] | None = None, best_move: chess.Move | None = None, light_square_texture: str = '', dark_square_texture: str = '') -> Image.Image:
    if renderer == 'svg':
        return render_board_svg(board, image_size, theme, highlighted_squares, best_move)
    if renderer == 'simple':
        return render_board_simple(board, image_size, theme, highlighted_squares, best_move, light_square_texture, dark_square_texture)
    if chess_svg is not None and cairosvg is not None:
        return render_board_svg(board, image_size, theme, highlighted_squares, best_move)
    return render_board_simple(board, image_size, theme, highlighted_squares, best_move, light_square_texture, dark_square_texture)


def export_json(items: list[dict], output_root: Path):
    json_path = output_root / f'{output_root.name}.json'
    with json_path.open('w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def limit_reached(count: int, limit: int) -> bool:
    return limit > 0 and count >= limit


def ensure_dirs(output_root: Path):
    dataset_name = output_root.name
    editing_dir = output_root / 'editing'
    gt_dir = output_root / 'gt'
    editing_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)
    return dataset_name, editing_dir, gt_dir


def build_opening_dataset(args) -> int:
    grouped: dict[str, list[tuple[list[str], chess.pgn.Game]]] = {}
    for game in iter_games(Path(args.input)):
        opening = normalize_opening_name(game.headers.get('Opening', '').strip())
        required_plies = max(args.min_plies, args.plies)
        if not opening or not matches_opening(opening, args.openings) or count_plies(game) < required_plies:
            continue
        prefix = opening_move_prefix(game, args.plies)
        if not prefix:
            continue
        grouped.setdefault(opening, []).append((prefix, game))

    canonical_samples: list[dict] = []
    for opening in sorted(grouped):
        entries = grouped[opening]
        canonical_prefix, representative_game, canonical_count = most_common_prefix(entries)
        if not canonical_prefix or representative_game is None:
            continue
        canonical_samples.append(
            {
                'opening': opening,
                'game': representative_game,
                'canonical_prefix': canonical_prefix,
                'source_count': len(entries),
                'canonical_count': canonical_count,
            }
        )

    if not canonical_samples:
        raise SystemExit('No chess opening samples found.')

    if args.max_samples > 0:
        canonical_samples = canonical_samples[: args.max_samples]

    output_root = Path(args.output_root)
    dataset_name, editing_dir, gt_dir = ensure_dirs(output_root)
    effective_renderer = args.renderer if args.renderer != 'auto' else ('svg' if chess_svg is not None and cairosvg is not None else 'simple')
    items = []
    for idx, sample in enumerate(canonical_samples, start=1):
        theme_name, theme = choose_theme(getattr(args, 'board_theme', DEFAULT_BOARD_THEME), random)
        before_board = chess.Board()
        after_board = board_from_uci_prefix(sample['canonical_prefix'])
        light_texture = getattr(args, 'chess_light_square_image', '') if theme_name == 'wood_classic' else ''
        dark_texture = getattr(args, 'chess_dark_square_image', '') if theme_name == 'wood_classic' else ''
        sample_renderer = resolve_renderer(args.renderer, theme_name)
        render_board(before_board, args.image_size, sample_renderer, theme, light_square_texture=light_texture, dark_square_texture=dark_texture).save(editing_dir / f'{idx}_before.png')
        render_board(after_board, args.image_size, sample_renderer, theme, light_square_texture=light_texture, dark_square_texture=dark_texture).save(gt_dir / f'{idx}_after.png')
        items.append({'text': f"Edit the chess diagram to show the {sample['opening']}.", 'task_id': f'task_{idx}', 'image_path': f'{dataset_name}/editing/{idx}_before.png', 'gt': f'{dataset_name}/gt/{idx}_after.png', 'sub_task': 'Chess', 'meta': {'opening': sample['opening'], 'eco': sample['game'].headers.get('ECO', ''), 'plies_used': len(sample['canonical_prefix']), 'requested_plies': args.plies, 'source_count': sample['source_count'], 'canonical_count': sample['canonical_count'], 'canonical_prefix_moves_uci': sample['canonical_prefix'], 'renderer': sample_renderer, 'board_theme': theme_name, 'light_square_texture': light_texture, 'dark_square_texture': dark_texture}})
    export_json(items, output_root)
    print(f'Exported {len(items)} chess opening samples to {output_root}')
    return 0


def candidate_piece_squares(board: chess.Board, piece_type: int) -> list[int]:
    squares = []
    for sq, piece in board.piece_map().items():
        if piece.piece_type != piece_type:
            continue
        targets = [m.to_square for m in board.legal_moves if m.from_square == sq]
        if targets:
            squares.append(sq)
    return squares


def choose_legal_sample(board: chess.Board, min_targets: int, max_targets: int) -> LegalSample | None:
    piece_types = ALL_PIECE_TYPES[:]
    random.shuffle(piece_types)
    for piece_type in piece_types:
        squares = candidate_piece_squares(board, piece_type)
        random.shuffle(squares)
        for sq in squares:
            targets = sorted({m.to_square for m in board.legal_moves if m.from_square == sq})
            if min_targets <= len(targets) <= max_targets:
                return LegalSample(board=board.copy(stack=False), piece_square=sq, piece_type=piece_type, legal_targets=targets)
    return None


def sample_positions_from_game(game: chess.pgn.Game, min_ply: int, max_ply: int, keep_game_over: bool = True) -> list[chess.Board]:
    board = game.board()
    positions: list[chess.Board] = []
    for ply, move in enumerate(game.mainline_moves(), start=1):
        board.push(move)
        if min_ply <= ply <= max_ply and (keep_game_over or not board.is_game_over()):
            positions.append(board.copy(stack=False))
        if ply > max_ply:
            break
    return positions


def build_legal_moves_dataset(args) -> int:
    random.seed(args.seed)
    samples: list[LegalSample] = []
    per_piece_limit = None if args.max_samples <= 0 else max(1, args.max_samples // len(ALL_PIECE_TYPES))
    per_piece_count = {piece_type: 0 for piece_type in ALL_PIECE_TYPES}
    for game in iter_games(Path(args.input)):
        positions = sample_positions_from_game(game, args.min_ply, args.max_ply)
        random.shuffle(positions)
        for board in positions:
            sample = choose_legal_sample(board, args.min_targets, args.max_targets)
            if sample is None or (per_piece_limit is not None and per_piece_count[sample.piece_type] >= per_piece_limit):
                continue
            samples.append(sample)
            per_piece_count[sample.piece_type] += 1
            if limit_reached(len(samples), args.max_samples):
                break
        if limit_reached(len(samples), args.max_samples):
            break
    if not samples:
        raise SystemExit('No chess legal-move samples found.')

    output_root = Path(args.output_root)
    dataset_name, editing_dir, gt_dir = ensure_dirs(output_root)
    effective_renderer = args.renderer if args.renderer != 'auto' else ('svg' if chess_svg is not None and cairosvg is not None else 'simple')
    items = []
    for idx, sample in enumerate(samples, start=1):
        theme_name, theme = choose_theme(getattr(args, 'board_theme', DEFAULT_BOARD_THEME), random)
        light_texture = getattr(args, 'chess_light_square_image', '') if theme_name == 'wood_classic' else ''
        dark_texture = getattr(args, 'chess_dark_square_image', '') if theme_name == 'wood_classic' else ''
        sample_renderer = resolve_renderer(args.renderer, theme_name)
        render_board(sample.board, args.image_size, sample_renderer, theme, light_square_texture=light_texture, dark_square_texture=dark_texture).save(editing_dir / f'{idx}_before.png')
        render_board(sample.board, args.image_size, sample_renderer, theme, highlighted_squares=sample.legal_targets, light_square_texture=light_texture, dark_square_texture=dark_texture).save(gt_dir / f'{idx}_after.png')
        items.append({'text': f'Highlight the squares the {PIECE_NAMES[sample.piece_type]} can move to.', 'task_id': f'task_{idx}', 'image_path': f'{dataset_name}/editing/{idx}_before.png', 'gt': f'{dataset_name}/gt/{idx}_after.png', 'sub_task': 'Chess', 'meta': {'piece_type': PIECE_NAMES[sample.piece_type], 'piece_square': chess.square_name(sample.piece_square), 'num_targets': len(sample.legal_targets), 'targets': [chess.square_name(sq) for sq in sample.legal_targets], 'fen': sample.board.fen(), 'renderer': sample_renderer, 'board_theme': theme_name, 'light_square_texture': light_texture, 'dark_square_texture': dark_texture}})
    export_json(items, output_root)
    print(f'Exported {len(items)} chess legal-move samples to {output_root}')
    return 0


def score_to_cp(score: chess.engine.Score | None, turn: chess.Color) -> int | None:
    if score is None:
        return None
    pov = score.pov(turn)
    if pov.is_mate():
        mate = pov.mate()
        if mate is None:
            return None
        return (1 if mate > 0 else -1) * MATE_CP
    return pov.score()


def analyze_position(engine: chess.engine.SimpleEngine, board: chess.Board, depth: int) -> AnalysisResult:
    infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=2)
    if not infos:
        return AnalysisResult(None, None, None)
    if isinstance(infos, dict):
        infos = [infos]
    top = infos[0]
    pv = top.get('pv') or []
    if not pv:
        return AnalysisResult(None, None, None)
    best_move = pv[0]
    best_score = score_to_cp(top.get('score'), board.turn)
    gap = None
    if len(infos) >= 2:
        second_score = score_to_cp(infos[1].get('score'), board.turn)
        if best_score is not None and second_score is not None:
            gap = best_score - second_score
    return AnalysisResult(best_move, best_score, gap)


def is_stable_candidate(shallow: AnalysisResult, deep: AnalysisResult, min_score_gap_cp: int, max_abs_score_cp: int) -> bool:
    if shallow.best_move is None or deep.best_move is None:
        return False
    if shallow.best_move != deep.best_move:
        return False
    if shallow.best_score_cp is None or deep.best_score_cp is None or shallow.score_gap_cp is None or deep.score_gap_cp is None:
        return False
    if abs(shallow.best_score_cp) >= MATE_CP or abs(deep.best_score_cp) >= MATE_CP:
        return False
    if abs(shallow.best_score_cp) > max_abs_score_cp or abs(deep.best_score_cp) > max_abs_score_cp:
        return False
    if shallow.score_gap_cp < min_score_gap_cp or deep.score_gap_cp < min_score_gap_cp:
        return False
    return True


def build_bestmove_dataset(args) -> int:
    if not args.engine:
        raise SystemExit('--engine is required for chess bestmove')
    if args.verify_depth <= args.depth:
        raise SystemExit('--verify-depth must be greater than --depth.')
    random.seed(args.seed)

    output_root = Path(args.output_root)
    dataset_name, editing_dir, gt_dir = ensure_dirs(output_root)
    json_path = output_root / f'{dataset_name}.json'
    written = 0
    checked_positions = 0
    first = True

    with json_path.open('w', encoding='utf-8') as handle:
        handle.write('[\n')
        with chess.engine.SimpleEngine.popen_uci(str(Path(args.engine))) as engine:
            for game in iter_games(Path(args.input)):
                positions = sample_positions_from_game(game, args.min_ply, args.max_ply, keep_game_over=False)
                random.shuffle(positions)
                for board in positions:
                    checked_positions += 1
                    shallow = analyze_position(engine, board, args.depth)
                    deep = analyze_position(engine, board, args.verify_depth)
                    if checked_positions % 500 == 0:
                        print(f'Checked {checked_positions} positions, kept {written} samples...')
                    if not is_stable_candidate(shallow, deep, args.min_score_gap_cp, args.max_abs_score_cp):
                        continue

                    written += 1
                    sample = BestMoveSample(
                        board=board.copy(stack=False),
                        best_move=deep.best_move,
                        side_to_move='White' if board.turn == chess.WHITE else 'Black',
                        shallow_score_cp=shallow.best_score_cp,
                        deep_score_cp=deep.best_score_cp,
                        shallow_gap_cp=shallow.score_gap_cp,
                        deep_gap_cp=deep.score_gap_cp,
                        shallow_depth=args.depth,
                        deep_depth=args.verify_depth,
                    )
                    theme_name, theme = choose_theme(getattr(args, 'board_theme', DEFAULT_BOARD_THEME), random)
                    light_texture = getattr(args, 'chess_light_square_image', '') if theme_name == 'wood_classic' else ''
                    dark_texture = getattr(args, 'chess_dark_square_image', '') if theme_name == 'wood_classic' else ''
                    sample_renderer = resolve_renderer(args.renderer, theme_name)

                    after_board = sample.board.copy(stack=False)
                    after_board.push(sample.best_move)

                    render_board(
                        sample.board,
                        args.image_size,
                        sample_renderer,
                        theme,
                        light_square_texture=light_texture,
                        dark_square_texture=dark_texture,
                    ).save(editing_dir / f'{written}_before.png')
                    render_board(
                        after_board,
                        args.image_size,
                        sample_renderer,
                        theme,
                        light_square_texture=light_texture,
                        dark_square_texture=dark_texture,
                    ).save(gt_dir / f'{written}_after.png')

                    item = {
                        'text': f"Edit the chess diagram by making {sample.side_to_move}'s best next move.",
                        'task_id': f'task_{written}',
                        'image_path': f'{dataset_name}/editing/{written}_before.png',
                        'gt': f'{dataset_name}/gt/{written}_after.png',
                        'sub_task': 'Chess',
                        'meta': {
                            'best_move_uci': sample.best_move.uci(),
                            'side_to_move': sample.side_to_move,
                            'fen': sample.board.fen(),
                            'after_fen': after_board.fen(),
                            'shallow_score_cp': sample.shallow_score_cp,
                            'deep_score_cp': sample.deep_score_cp,
                            'shallow_gap_cp': sample.shallow_gap_cp,
                            'deep_gap_cp': sample.deep_gap_cp,
                            'shallow_depth': sample.shallow_depth,
                            'deep_depth': sample.deep_depth,
                            'renderer': sample_renderer,
                            'board_theme': theme_name,
                            'light_square_texture': light_texture,
                            'dark_square_texture': dark_texture,
                        },
                    }
                    if not first:
                        handle.write(',\n')
                    handle.write(json.dumps(item, ensure_ascii=False, indent=2))
                    first = False

                    if written % 50 == 0:
                        print(f'Wrote {written} samples to {output_root}...')
                    if limit_reached(written, args.max_samples):
                        break
                if limit_reached(written, args.max_samples):
                    break
        handle.write('\n]\n')

    if written == 0:
        raise SystemExit('No chess best-move samples found.')

    print(f'Exported {written} chess best-move samples to {output_root}')
    return 0











