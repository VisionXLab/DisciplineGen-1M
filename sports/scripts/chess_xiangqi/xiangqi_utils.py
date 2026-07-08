#!/usr/bin/env python3
from __future__ import annotations

import copy
import io
import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

STARTPOS_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w"

RED = "red"
BLACK = "black"
FILES = "abcdefghi"
RANKS = "0123456789"

# External binary renderer colors (used by xiangqi-setup)
XQS_LIGHT_COLOR = "#F0D9B5"
XQS_LINE_COLOR = "#5B3A29"
XQS_TEXT_COLOR = "#7A2F2F"
XQS_RED_FILL = "#F6E6D8"
XQS_BLACK_FILL = "#F0F0F0"
XQS_RED_TEXT = "#C0392B"
XQS_BLACK_TEXT = "#2C3E50"
XQS_HIGHLIGHT_FILL = "#F4D03F"
XQS_HIGHLIGHT_OUTLINE = "#C27C0E"
XQS_ARROW_COLOR = "#D35400"
XQS_SRC_OUTLINE = "#F39C12"
XQS_SETUP_FIELD_WIDTH = 53.0
XQS_SETUP_FIELD_HEIGHT = 53.0
XQS_SETUP_BORDER_GAP_WIDTH = 40.0
XQS_SETUP_BORDER_GAP_HEIGHT = 40.0
XQS_SETUP_NATURAL_WIDTH = 2 * XQS_SETUP_BORDER_GAP_WIDTH + 8 * XQS_SETUP_FIELD_WIDTH
XQS_SETUP_NATURAL_HEIGHT = 2 * XQS_SETUP_BORDER_GAP_HEIGHT + 9 * XQS_SETUP_FIELD_HEIGHT

# Simple PIL renderer colors
SIMPLE_LIGHT_SQUARE = "#F0D9B5"
SIMPLE_DARK_SQUARE = "#D0A060"
SIMPLE_LINE_COLOR = "#5B3A29"
SIMPLE_COORD_COLOR = "#7A2F2F"
SIMPLE_RIVER_COLOR = "#87CEEB"
SIMPLE_PALACE_COLOR = "#E8D4A0"
SIMPLE_RED_PIECE_FILL = "#F6E6D8"
SIMPLE_RED_PIECE_OUTLINE = "#8B0000"
SIMPLE_BLACK_PIECE_FILL = "#F0F0F0"
SIMPLE_BLACK_PIECE_OUTLINE = "#333333"
SIMPLE_HIGHLIGHT_FILL = "#F4D03F"
SIMPLE_HIGHLIGHT_OUTLINE = "#C27C0E"
SIMPLE_ARROW_COLOR = "#D35400"
SIMPLE_SRC_OUTLINE = "#F39C12"
MARKER_STYLES = {
    "green": {"fill": (103, 214, 87, 232), "outline": (76, 185, 66, 255)},
    "orange": {"fill": (242, 159, 67, 236), "outline": (222, 124, 36, 255)},
}

PIECE_LABELS = {
    "R": "车", "N": "马", "B": "相", "A": "仕", "K": "帅", "C": "炮", "P": "兵",
    "r": "車", "n": "馬", "b": "象", "a": "士", "k": "將", "c": "砲", "p": "卒",
}

PIECE_TYPE_NAME = {
    "R": "rook", "r": "rook",
    "N": "knight", "n": "knight",
    "B": "bishop", "b": "bishop",
    "A": "advisor", "a": "advisor",
    "K": "king", "k": "king",
    "C": "cannon", "c": "cannon",
    "P": "pawn", "p": "pawn",
}

ALL_PIECES = ["R", "N", "B", "A", "K", "C", "P", "r", "n", "b", "a", "k", "c", "p"]


PIECE_SVG_NAME = {
    'R': 'red_chariot.svg',
    'N': 'red_horse.svg',
    'B': 'red_elephant.svg',
    'A': 'red_advisor.svg',
    'K': 'red_king.svg',
    'C': 'red_cannon.svg',
    'P': 'red_pawn.svg',
    'r': 'black_chariot.svg',
    'n': 'black_horse.svg',
    'b': 'black_elephant.svg',
    'a': 'black_advisor.svg',
    'k': 'black_king.svg',
    'c': 'black_cannon.svg',
    'p': 'black_pawn.svg',
}

PIECE_PNG_NAME = {
    'R': '红方车.png',
    'N': '红方马.png',
    'B': '红方相.png',
    'A': '红方仕.png',
    'K': '红方帅.png',
    'C': '红方炮.png',
    'P': '红方兵.png',
    'r': '黑方車.png',
    'n': '黑方馬.png',
    'b': '黑方象.png',
    'a': '黑方士.png',
    'k': '黑方将.png',
    'c': '黑方炮.png',
    'p': '黑方卒.png',
}

DEFAULT_XIANGQI_PIECE_ASSET_DIR = Path(__file__).resolve().parent / 'assets'


@dataclass(frozen=True)
class XiangqiMove:
    from_row: int
    from_col: int
    to_row: int
    to_col: int

    def to_ucci(self) -> str:
        return coord_to_ucci(self.from_row, self.from_col) + coord_to_ucci(self.to_row, self.to_col)


class XiangqiBoard:
    def __init__(self, fen: str = STARTPOS_FEN):
        self.board, self.turn = parse_fen(fen)

    @classmethod
    def from_parts(cls, board: list[list[str]], turn: str):
        obj = cls.__new__(cls)
        obj.board = board
        obj.turn = turn
        return obj

    def copy(self) -> "XiangqiBoard":
        return XiangqiBoard.from_parts(copy.deepcopy(self.board), self.turn)

    def fen(self) -> str:
        return board_to_fen(self.board, self.turn)

    def piece_at(self, row: int, col: int) -> str:
        return self.board[row][col]

    def set_piece(self, row: int, col: int, piece: str) -> None:
        self.board[row][col] = piece

    def apply_move(self, move: XiangqiMove) -> None:
        piece = self.piece_at(move.from_row, move.from_col)
        self.set_piece(move.from_row, move.from_col, ".")
        self.set_piece(move.to_row, move.to_col, piece)
        self.turn = opposite(self.turn)

    def apply_ucci(self, ucci: str) -> None:
        self.apply_move(parse_ucci_move(ucci))

    def kings_face(self) -> bool:
        red = self.find_piece("K")
        black = self.find_piece("k")
        if red is None or black is None or red[1] != black[1]:
            return False
        col = red[1]
        r1, r2 = sorted([red[0], black[0]])
        for row in range(r1 + 1, r2):
            if self.piece_at(row, col) != ".":
                return False
        return True

    def find_piece(self, piece: str):
        for r in range(10):
            for c in range(9):
                if self.piece_at(r, c) == piece:
                    return (r, c)
        return None

    def find_pieces(self, piece: str):
        out = []
        for r in range(10):
            for c in range(9):
                if self.piece_at(r, c) == piece:
                    out.append((r, c))
        return out

    def side_pieces(self, color: str):
        out = []
        for r in range(10):
            for c in range(9):
                p = self.piece_at(r, c)
                if p != "." and color_of_piece(p) == color:
                    out.append((r, c, p))
        return out

    def in_check(self, color: str) -> bool:
        king_piece = "K" if color == RED else "k"
        king_pos = self.find_piece(king_piece)
        if king_pos is None:
            return True
        if self.kings_face():
            return True
        opponent = opposite(color)
        for r, c, p in self.side_pieces(opponent):
            for move in self.pseudo_moves_from(r, c, attacks_only=True):
                if (move.to_row, move.to_col) == king_pos:
                    return True
        return False

    def legal_moves_from(self, row: int, col: int):
        piece = self.piece_at(row, col)
        if piece == "." or color_of_piece(piece) != self.turn:
            return []
        legal = []
        for mv in self.pseudo_moves_from(row, col, attacks_only=False):
            nxt = self.copy()
            nxt.apply_move(mv)
            if not nxt.in_check(color_of_piece(piece)):
                legal.append(mv)
        return legal

    def all_legal_moves(self, color: str | None = None):
        side = self.turn if color is None else color
        original_turn = self.turn
        self.turn = side
        moves = []
        for r, c, p in self.side_pieces(side):
            moves.extend(self.legal_moves_from(r, c))
        self.turn = original_turn
        return moves

    def pseudo_moves_from(self, row: int, col: int, attacks_only: bool):
        piece = self.piece_at(row, col)
        if piece == ".":
            return []
        color = color_of_piece(piece)
        piece_u = piece.upper()
        if piece_u == "R":
            return self._rook_moves(row, col, color)
        if piece_u == "C":
            return self._cannon_moves(row, col, color)
        if piece_u == "N":
            return self._knight_moves(row, col, color)
        if piece_u == "B":
            return self._bishop_moves(row, col, color)
        if piece_u == "A":
            return self._advisor_moves(row, col, color)
        if piece_u == "K":
            return self._king_moves(row, col, color)
        if piece_u == "P":
            return self._pawn_moves(row, col, color)
        return []

    def _rook_moves(self, row: int, col: int, color: str):
        moves = []
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            r, c = row + dr, col + dc
            while inside(r, c):
                target = self.piece_at(r, c)
                if target == ".":
                    moves.append(XiangqiMove(row, col, r, c))
                else:
                    if color_of_piece(target) != color:
                        moves.append(XiangqiMove(row, col, r, c))
                    break
                r += dr
                c += dc
        return moves

    def _cannon_moves(self, row: int, col: int, color: str):
        moves = []
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            r, c = row + dr, col + dc
            screen_found = False
            while inside(r, c):
                target = self.piece_at(r, c)
                if not screen_found:
                    if target == ".":
                        moves.append(XiangqiMove(row, col, r, c))
                    else:
                        screen_found = True
                else:
                    if target != ".":
                        if color_of_piece(target) != color:
                            moves.append(XiangqiMove(row, col, r, c))
                        break
                r += dr
                c += dc
        return moves

    def _knight_moves(self, row: int, col: int, color: str):
        moves = []
        patterns = [
            (-2, -1, -1, 0), (-2, 1, -1, 0),
            (2, -1, 1, 0), (2, 1, 1, 0),
            (-1, -2, 0, -1), (1, -2, 0, -1),
            (-1, 2, 0, 1), (1, 2, 0, 1),
        ]
        for dr, dc, lr, lc in patterns:
            leg_r, leg_c = row + lr, col + lc
            tr, tc = row + dr, col + dc
            if inside(tr, tc) and self.piece_at(leg_r, leg_c) == ".":
                target = self.piece_at(tr, tc)
                if target == "." or color_of_piece(target) != color:
                    moves.append(XiangqiMove(row, col, tr, tc))
        return moves

    def _bishop_moves(self, row: int, col: int, color: str):
        moves = []
        for dr, dc in [(-2,-2),(-2,2),(2,-2),(2,2)]:
            tr, tc = row + dr, col + dc
            eye_r, eye_c = row + dr // 2, col + dc // 2
            if not inside(tr, tc) or self.piece_at(eye_r, eye_c) != ".":
                continue
            if color == RED and tr < 5:
                continue
            if color == BLACK and tr > 4:
                continue
            target = self.piece_at(tr, tc)
            if target == "." or color_of_piece(target) != color:
                moves.append(XiangqiMove(row, col, tr, tc))
        return moves

    def _advisor_moves(self, row: int, col: int, color: str):
        moves = []
        for dr, dc in [(-1,-1),(-1,1),(1,-1),(1,1)]:
            tr, tc = row + dr, col + dc
            if not inside(tr, tc) or not in_palace(tr, tc, color):
                continue
            target = self.piece_at(tr, tc)
            if target == "." or color_of_piece(target) != color:
                moves.append(XiangqiMove(row, col, tr, tc))
        return moves

    def _king_moves(self, row: int, col: int, color: str):
        moves = []
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            tr, tc = row + dr, col + dc
            if not inside(tr, tc) or not in_palace(tr, tc, color):
                continue
            target = self.piece_at(tr, tc)
            if target == "." or color_of_piece(target) != color:
                moves.append(XiangqiMove(row, col, tr, tc))
        # flying general capture
        enemy_king = "k" if color == RED else "K"
        r = row - 1 if color == RED else row + 1
        step = -1 if color == RED else 1
        while inside(r, col):
            target = self.piece_at(r, col)
            if target != ".":
                if target == enemy_king:
                    moves.append(XiangqiMove(row, col, r, col))
                break
            r += step
        return moves

    def _pawn_moves(self, row: int, col: int, color: str):
        moves = []
        dirs = [(-1,0)] if color == RED else [(1,0)]
        crossed = row <= 4 if color == RED else row >= 5
        if crossed:
            dirs.extend([(0,-1),(0,1)])
        for dr, dc in dirs:
            tr, tc = row + dr, col + dc
            if not inside(tr, tc):
                continue
            target = self.piece_at(tr, tc)
            if target == "." or color_of_piece(target) != color:
                moves.append(XiangqiMove(row, col, tr, tc))
        return moves


def inside(row: int, col: int) -> bool:
    return 0 <= row < 10 and 0 <= col < 9


def in_palace(row: int, col: int, color: str) -> bool:
    if not (3 <= col <= 5):
        return False
    return 7 <= row <= 9 if color == RED else 0 <= row <= 2


def color_of_piece(piece: str) -> str:
    return RED if piece.isupper() else BLACK


def opposite(color: str) -> str:
    return BLACK if color == RED else RED


def parse_fen(fen: str):
    parts = fen.strip().split()
    board_part = parts[0]
    turn = RED if len(parts) < 2 or parts[1] == "w" else BLACK
    rows = board_part.split("/")
    if len(rows) != 10:
        raise ValueError(f"Invalid xiangqi FEN rows: {fen}")
    board = []
    for row in rows:
        out = []
        for ch in row:
            if ch.isdigit():
                out.extend(["."] * int(ch))
            else:
                out.append(ch)
        if len(out) != 9:
            raise ValueError(f"Invalid xiangqi FEN row width: {row}")
        board.append(out)
    return board, turn


def board_to_fen(board: list[list[str]], turn: str) -> str:
    rows = []
    for row in board:
        s = []
        empty = 0
        for ch in row:
            if ch == ".":
                empty += 1
            else:
                if empty:
                    s.append(str(empty))
                    empty = 0
                s.append(ch)
        if empty:
            s.append(str(empty))
        rows.append("".join(s))
    return "/".join(rows) + (" w" if turn == RED else " b")


def coord_to_ucci(row: int, col: int) -> str:
    return FILES[col] + str(9 - row)


def ucci_to_coord(coord: str):
    if len(coord) != 2 or coord[0] not in FILES or coord[1] not in RANKS:
        raise ValueError(f"Invalid UCCI coordinate: {coord}")
    col = FILES.index(coord[0])
    row = 9 - int(coord[1])
    return row, col


def parse_ucci_move(move: str) -> XiangqiMove:
    if len(move) != 4:
        raise ValueError(f"Invalid UCCI move: {move}")
    fr, fc = ucci_to_coord(move[:2])
    tr, tc = ucci_to_coord(move[2:])
    return XiangqiMove(fr, fc, tr, tc)


def apply_moves(board: XiangqiBoard, moves_ucci: list[str], max_plies: int | None = None) -> XiangqiBoard:
    out = board.copy()
    for idx, mv in enumerate(moves_ucci, start=1):
        out.apply_ucci(mv)
        if max_plies is not None and idx >= max_plies:
            break
    return out


def iter_position_sequence(initial_fen: str, moves_ucci: list[str], min_ply: int, max_ply: int):
    board = XiangqiBoard(initial_fen)
    out = []
    for ply, mv in enumerate(moves_ucci, start=1):
        board.apply_ucci(mv)
        if min_ply <= ply <= max_ply:
            out.append((ply, board.copy()))
        if ply > max_ply:
            break
    return out


def load_jsonl_records(path: str | Path):
    records = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if "moves_ucci" in obj and isinstance(obj["moves_ucci"], str):
                obj["moves_ucci"] = [x for x in obj["moves_ucci"].split() if x]
            records.append(obj)
    return records


def load_font(size: int):
    for candidate in [
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/arphic/ukai.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "DejaVuSans-Bold.ttf",
        "arial.ttf",
        "LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyh.ttc",
    ]:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def piece_theme_dir(piece_theme: str) -> Path:
    return Path(__file__).resolve().parents[2] / 'tmp_xiangqi_setup_src' / 'unpacked' / 'xiangqi_setup' / 'themes' / 'pieces' / piece_theme


def piece_asset_dir(piece_assets_dir: str = '') -> Path:
    if piece_assets_dir:
        return Path(piece_assets_dir).expanduser()
    return DEFAULT_XIANGQI_PIECE_ASSET_DIR


def trim_transparent_border(image: Image.Image, padding: int = 0) -> Image.Image:
    bbox = image.getbbox()
    if bbox is None:
        return image
    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    return image.crop((left, top, right, bottom))


def estimate_background_color(image: Image.Image) -> tuple[int, int, int]:
    image = image.convert('RGBA')
    width, height = image.size
    sample_size = max(6, min(width, height) // 12)
    points = []
    for x0, y0 in [
        (0, 0),
        (width - sample_size, 0),
        (0, height - sample_size),
        (width - sample_size, height - sample_size),
    ]:
        for y in range(y0, y0 + sample_size):
            for x in range(x0, x0 + sample_size):
                r, g, b, a = image.getpixel((x, y))
                if a > 0:
                    points.append((r, g, b))
    if not points:
        return (255, 255, 255)
    return tuple(round(sum(p[i] for p in points) / len(points)) for i in range(3))


def is_piece_body_pixel(r: int, g: int, b: int, bg: tuple[int, int, int]) -> bool:
    avg = (r + g + b) / 3.0
    chroma = max(r, g, b) - min(r, g, b)
    bg_dist = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
    return bg_dist >= 18 and (chroma >= 18 or avg <= 160)


def detect_piece_circle(image: Image.Image) -> tuple[float, float, float]:
    image = image.convert('RGBA')
    width, height = image.size
    bg = estimate_background_color(image)
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    directions = [
        (1.0, 0.0),
        (-1.0, 0.0),
        (0.0, 1.0),
        (0.0, -1.0),
        (0.70710678, 0.70710678),
        (0.70710678, -0.70710678),
        (-0.70710678, 0.70710678),
        (-0.70710678, -0.70710678),
    ]
    radii = []
    max_steps = int(min(width, height) * 0.7)
    for dx, dy in directions:
        last_piece_distance = None
        for step in range(1, max_steps + 1):
            x = int(round(cx + dx * step))
            y = int(round(cy + dy * step))
            if x < 0 or x >= width or y < 0 or y >= height:
                break
            r, g, b, a = image.getpixel((x, y))
            if a > 0 and is_piece_body_pixel(r, g, b, bg):
                last_piece_distance = step
        if last_piece_distance is not None:
            radii.append(last_piece_distance)
    if not radii:
        return cx, cy, min(width, height) * 0.42
    radii.sort()
    radius = radii[len(radii) // 2]
    return cx, cy, max(8.0, float(radius))


def apply_circular_piece_mask(image: Image.Image, feather: float = 1.5, shrink: float = 0.0) -> Image.Image:
    image = image.convert('RGBA')
    cx, cy, radius = detect_piece_circle(image)
    radius = max(4.0, radius - max(3.0, radius * 0.035, shrink))
    masked = Image.new('RGBA', image.size, (0, 0, 0, 0))
    width, height = image.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = image.getpixel((x, y))
            if a == 0:
                continue
            dist = math.hypot(x - cx, y - cy)
            if dist <= radius:
                alpha_scale = 1.0
            elif dist >= radius + feather:
                alpha_scale = 0.0
            else:
                alpha_scale = max(0.0, min(1.0, (radius + feather - dist) / max(feather, 1e-6)))
            if alpha_scale <= 0.0:
                continue
            masked.putpixel((x, y), (r, g, b, int(round(a * alpha_scale))))
    return trim_transparent_border(masked, padding=1)


def make_piece_background_transparent(image: Image.Image) -> Image.Image:
    image = image.convert('RGBA')
    pixels = []
    for r, g, b, a in image.getdata():
        avg = (r + g + b) / 3.0
        saturation = max(r, g, b) - min(r, g, b)
        if avg >= 248 and saturation <= 18:
            alpha = 0
        elif avg >= 236 and saturation <= 24:
            alpha = max(0, min(255, int(round((248 - avg) * 16))))
        elif avg >= 224 and saturation <= 32:
            alpha = max(0, min(255, int(round((240 - avg) * 10))))
        else:
            alpha = a
        pixels.append((r, g, b, alpha))
    image.putdata(pixels)
    return trim_transparent_border(image, padding=2)


def fit_piece_to_square(image: Image.Image, target_size: int, scale_ratio: float = 0.9) -> Image.Image:
    max_side = max(1, target_size)
    image = trim_transparent_border(image)
    usable = max(1, round(max_side * scale_ratio))
    scale = min(usable / image.width, usable / image.height)
    resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (max_side, max_side), (0, 0, 0, 0))
    offset = ((max_side - resized.width) // 2, (max_side - resized.height) // 2)
    canvas.alpha_composite(resized, offset)
    return canvas


def normalize_piece_asset_image(
    image: Image.Image,
    canvas_size: int,
    scale_ratio: float = 0.9,
) -> Image.Image:
    image = apply_circular_piece_mask(image)
    image = make_piece_background_transparent(image)
    return fit_piece_to_square(image, canvas_size, scale_ratio=scale_ratio)


def load_piece_asset_image(piece: str, target_size: int, piece_assets_dir: str = '') -> Image.Image | None:
    asset_name = PIECE_PNG_NAME.get(piece)
    if not asset_name:
        return None
    asset_path = piece_asset_dir(piece_assets_dir) / asset_name
    if not asset_path.is_file():
        return None
    image = Image.open(asset_path).convert('RGBA')
    if image.getchannel('A').getextrema() == (255, 255):
        return normalize_piece_asset_image(image, canvas_size=target_size, scale_ratio=0.9)
    return fit_piece_to_square(image, target_size, scale_ratio=0.9)


def load_piece_svg_image(piece: str, piece_theme: str, svg_converter: str, target_size: int) -> Image.Image | None:
    theme_dir = piece_theme_dir(piece_theme)
    svg_name = PIECE_SVG_NAME.get(piece)
    if not svg_name:
        return None
    svg_path = theme_dir / svg_name
    if not svg_path.is_file():
        return None
    try:
        image = svg_to_image(svg_path, svg_converter)
    except Exception:
        return None
    image = image.convert('RGBA')
    return fit_piece_to_square(image, target_size, scale_ratio=0.9)


def load_piece_font(size: int):
    for candidate in [
        str((Path(__file__).resolve().parents[2] / 'tmp_xiangqi_setup_src' / 'unpacked' / 'xiangqi_setup' / 'themes' / 'pieces' / 'latex_xqlarge_2006_chinese_potrace' / 'original' / 'xqlarge-potrace.ttf')),
        str((Path(__file__).resolve().parents[2] / 'tmp_xiangqi_setup_src' / 'unpacked' / 'xiangqi_setup' / 'themes' / 'pieces' / 'latex_xqlarge_2006_chinese_potrace' / 'original' / 'xqlarge-autotrace.ttf')),
    ]:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return load_font(size)


def _draw_centered_text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font, fill: str):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((xy[0] - w / 2, xy[1] - h / 2), text, font=font, fill=fill)


def _board_line(draw_obj, x0: float, y0: float, x1: float, y1: float, color: str, width: int) -> None:
    draw_obj.line(
        [(int(round(x0)), int(round(y0))), (int(round(x1)), int(round(y1)))],
        fill=color,
        width=max(1, width),
    )


def _draw_corner_mark(draw_obj, cx: float, cy: float, show_left: bool, show_right: bool, size: float, color: str, width: int) -> None:
    arm = size * 0.14
    gap = size * 0.12

    def corner(anchor_x: float, anchor_y: float, sx: int, sy: int) -> None:
        _board_line(draw_obj, anchor_x, anchor_y, anchor_x + sx * arm, anchor_y, color, width)
        _board_line(draw_obj, anchor_x, anchor_y, anchor_x, anchor_y + sy * arm, color, width)

    if show_left:
        corner(cx - gap, cy - gap, -1, -1)
        corner(cx - gap, cy + gap, -1, 1)
    if show_right:
        corner(cx + gap, cy - gap, 1, -1)
        corner(cx + gap, cy + gap, 1, 1)


def _draw_piece_disc(canvas: Image.Image, cx: float, cy: float, radius: float, is_red: bool) -> tuple[str, str]:
    accent = '#D95A33' if is_red else '#2E302E'
    ring = '#F4D76A' if is_red else '#E6D36B'
    text_fill = '#D84C2F' if is_red else '#151515'
    shadow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sx = radius * 0.12
    sy = radius * 0.16
    sd.ellipse([cx - radius + sx, cy - radius + sy, cx + radius + sx, cy + radius + sy], fill=(0, 0, 0, 42))
    sd.ellipse([cx - radius * 0.96 + sx * 1.2, cy - radius * 0.96 + sy * 1.2, cx + radius * 0.96 + sx * 1.2, cy + radius * 0.96 + sy * 1.2], fill=(0, 0, 0, 22))
    canvas.alpha_composite(shadow)

    draw = ImageDraw.Draw(canvas)
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill='#F4E188', outline=accent, width=max(2, round(radius * 0.08)))
    inner = radius * 0.86
    draw.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], outline='#2E2A21', width=max(1, round(radius * 0.045)))
    glow = radius * 0.75
    draw.ellipse([cx - glow, cy - glow * 1.05, cx + glow, cy + glow * 0.55], fill=(255, 248, 210, 70))
    draw.ellipse([cx - radius * 0.96, cy - radius * 0.96, cx + radius * 0.96, cy + radius * 0.96], outline=ring, width=max(1, round(radius * 0.035)))
    return text_fill, accent


def render_xiangqi_board_template(
    board: XiangqiBoard,
    image_size: int,
    marker_squares: list[tuple[int, int]] | None = None,
    marker_style: str = 'green',
    board_image_path: str = '',
    piece_assets_dir: str = '',
    piece_theme: str = 'latex_xqlarge_2006_chinese_potrace',
    svg_converter: str = 'auto',
) -> Image.Image:
    board_path = Path(board_image_path).expanduser()
    if not board_path.is_file():
        raise RuntimeError(f'Xiangqi board image not found: {board_path}')

    base = Image.open(board_path).convert('RGBA')
    canvas, _offset, _content_size = fit_image_to_square(base, image_size)
    grid = detect_xiangqi_grid(canvas)
    spacing = min(average_spacing(grid[0]), average_spacing(grid[1]))
    piece_size = max(12, round(spacing * 0.92))

    for row in range(10):
        for col in range(9):
            piece = board.piece_at(row, col)
            if piece == '.':
                continue
            cx, cy = board_center(row, col, grid)
            piece_img = load_piece_asset_image(piece, piece_size, piece_assets_dir)
            if piece_img is None:
                piece_img = load_piece_svg_image(piece, piece_theme, svg_converter, piece_size)
            if piece_img is not None:
                canvas.alpha_composite(piece_img, (int(round(cx - piece_img.width / 2)), int(round(cy - piece_img.height / 2))))
                continue
            radius = spacing * 0.385
            is_red = piece.isupper()
            text_fill, accent = _draw_piece_disc(canvas, cx, cy, radius, is_red)
            piece_draw = ImageDraw.Draw(canvas)
            piece_font = load_piece_font(max(20, round(spacing * 0.57)))
            label = PIECE_LABELS[piece]
            stroke_width = max(1, round(radius * 0.055))
            bbox = piece_draw.textbbox((0, 0), label, font=piece_font, stroke_width=stroke_width)
            tx = cx - (bbox[2] - bbox[0]) / 2.0
            ty = cy - (bbox[3] - bbox[1]) / 2.0 - radius * 0.03
            piece_draw.text(
                (tx, ty),
                label,
                font=piece_font,
                fill=text_fill,
                stroke_width=stroke_width,
                stroke_fill='#FFF6D8' if is_red else '#FBF6DA',
            )

    rendered = canvas.convert('RGB')
    if marker_squares:
        rendered = overlay_marker_dots(rendered, marker_squares, marker_style)
    return rendered


def render_xiangqi_board_simple(
    board: XiangqiBoard,
    image_size: int,
    highlight_squares: list[tuple[int, int]] | None = None,
    arrow: XiangqiMove | None = None,
    marker_squares: list[tuple[int, int]] | None = None,
    marker_style: str = 'green',
    board_image_path: str = '',
    piece_assets_dir: str = '',
) -> Image.Image:
    highlight_squares = highlight_squares or []
    marker_squares = marker_squares or []
    if board_image_path:
        return render_xiangqi_board_template(
            board,
            image_size,
            marker_squares=marker_squares,
            marker_style=marker_style,
            board_image_path=board_image_path,
            piece_assets_dir=piece_assets_dir,
            piece_theme='latex_xqlarge_2006_chinese_potrace',
            svg_converter='auto',
        )

    bg = '#F1E4CD'
    board_bg = '#F3E8D2'
    line_color = '#2E3130'
    river_text_color = '#161616'
    line_width = max(2, round(image_size * 0.0026))
    margin_x = round(image_size * 0.07)
    margin_y = round(image_size * 0.068)
    square = min((image_size - margin_x * 2) / 8.0, (image_size - margin_y * 2) / 9.0)
    board_w = square * 8.0
    board_h = square * 9.0
    offset_x = (image_size - board_w) / 2.0
    offset_y = (image_size - board_h) / 2.0

    canvas = Image.new('RGBA', (image_size, image_size), bg)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, image_size - 1, image_size - 1], fill=board_bg)

    river_top = offset_y + 4 * square
    river_bottom = offset_y + 5 * square

    for row in range(10):
        y = offset_y + row * square
        _board_line(draw, offset_x, y, offset_x + board_w, y, line_color, line_width)

    for col in range(9):
        x = offset_x + col * square
        if col in {0, 8}:
            _board_line(draw, x, offset_y, x, offset_y + board_h, line_color, line_width)
        else:
            _board_line(draw, x, offset_y, x, river_top, line_color, line_width)
            _board_line(draw, x, river_bottom, x, offset_y + board_h, line_color, line_width)

    _board_line(draw, offset_x + 3 * square, offset_y, offset_x + 5 * square, offset_y + 2 * square, line_color, line_width)
    _board_line(draw, offset_x + 5 * square, offset_y, offset_x + 3 * square, offset_y + 2 * square, line_color, line_width)
    _board_line(draw, offset_x + 3 * square, offset_y + 7 * square, offset_x + 5 * square, offset_y + 9 * square, line_color, line_width)
    _board_line(draw, offset_x + 5 * square, offset_y + 7 * square, offset_x + 3 * square, offset_y + 9 * square, line_color, line_width)

    mark_points = [
        (2, 1, True, True), (2, 7, True, True),
        (3, 0, False, True), (3, 2, True, True), (3, 4, True, True), (3, 6, True, True), (3, 8, True, False),
        (6, 0, False, True), (6, 2, True, True), (6, 4, True, True), (6, 6, True, True), (6, 8, True, False),
        (7, 1, True, True), (7, 7, True, True),
    ]
    for row, col, show_left, show_right in mark_points:
        cx = offset_x + col * square
        cy = offset_y + row * square
        _draw_corner_mark(draw, cx, cy, show_left, show_right, square, line_color, line_width)

    river_font = load_font(max(22, round(square * 0.58)))
    river_y = (river_top + river_bottom) / 2.0
    _draw_centered_text(draw, (offset_x + board_w * 0.18, river_y), '楚河', river_font, river_text_color)
    _draw_centered_text(draw, (offset_x + board_w * 0.82, river_y), '漢界', river_font, river_text_color)

    piece_font = load_piece_font(max(20, round(square * 0.55)))
    for row in range(10):
        for col in range(9):
            piece = board.piece_at(row, col)
            if piece == '.':
                continue
            cx = offset_x + col * square
            cy = offset_y + row * square
            radius = square * 0.38
            is_red = piece.isupper()
            text_fill, accent = _draw_piece_disc(canvas, cx, cy, radius, is_red)
            piece_draw = ImageDraw.Draw(canvas)
            bbox = piece_draw.textbbox((0, 0), PIECE_LABELS[piece], font=piece_font, stroke_width=max(1, round(radius * 0.05)))
            tx = cx - (bbox[2] - bbox[0]) / 2
            ty = cy - (bbox[3] - bbox[1]) / 2 - radius * 0.02
            piece_draw.text((tx, ty), PIECE_LABELS[piece], font=piece_font, fill=text_fill, stroke_width=max(1, round(radius * 0.05)), stroke_fill='#FFF6D7' if is_red else '#FAF2C7')

    canvas = canvas.convert('RGB')
    if marker_squares:
        canvas = overlay_marker_dots(canvas, marker_squares, marker_style)
    return canvas


def render_xiangqi_board(
    board: XiangqiBoard,
    image_size: int = 900,
    highlight_squares: list[tuple[int, int]] | None = None,
    arrow: XiangqiMove | None = None,
    marker_squares: list[tuple[int, int]] | None = None,
    marker_style: str = "green",
    renderer: str = "auto",
    xiangqi_setup_bin: str = "xiangqi-setup",
    svg_converter: str = "auto",
    board_theme: str = "clean_alpha",
    pieces_theme: str = "playok_2014_chinese",
    annotations_theme: str = "colors_alpha",
    board_image_path: str = "",
    piece_assets_dir: str = "",
    require_native_annotations: bool = False,
) -> Image.Image:
    highlight_squares = highlight_squares or []
    marker_squares = marker_squares or []
    use_annotations = bool(highlight_squares or arrow is not None)
    renderer = renderer.lower()

    if renderer == 'simple':
        return render_xiangqi_board_simple(
            board,
            image_size,
            highlight_squares,
            arrow,
            marker_squares=marker_squares,
            marker_style=marker_style,
            board_image_path=board_image_path,
            piece_assets_dir=piece_assets_dir,
        )

    if renderer == 'svg':
        rendered = _render_xiangqi_board_binary(
            board, image_size, highlight_squares, arrow,
            xiangqi_setup_bin, svg_converter, board_theme, pieces_theme, annotations_theme
        )
        if marker_squares:
            return overlay_marker_dots(rendered, marker_squares, marker_style)
        return rendered

    if xiangqi_setup_bin and xiangqi_setup_bin != "":
        try:
            rendered = _render_xiangqi_board_binary(
                board, image_size, highlight_squares, arrow,
                xiangqi_setup_bin, svg_converter, board_theme, pieces_theme, annotations_theme
            )
            if marker_squares:
                return overlay_marker_dots(rendered, marker_squares, marker_style)
            return rendered
        except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError):
            if require_native_annotations and use_annotations:
                raise

    if require_native_annotations and use_annotations:
        raise RuntimeError("Native xiangqi annotations require a working xiangqi-setup binary.")

    return render_xiangqi_board_simple(
        board,
        image_size,
        highlight_squares,
        arrow,
        marker_squares=marker_squares,
        marker_style=marker_style,
        board_image_path=board_image_path,
        piece_assets_dir=piece_assets_dir,
    )


def overlay_marker_dots(image: Image.Image, marker_squares: list[tuple[int, int]], marker_style: str = "green") -> Image.Image:
    if not marker_squares:
        return image.convert("RGB")

    style = MARKER_STYLES.get(marker_style.lower(), MARKER_STYLES["green"])
    canvas = image.convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    grid = detect_xiangqi_grid(canvas)
    spacing = min(average_spacing(grid[0]), average_spacing(grid[1]))
    radius = max(6.0, spacing * 0.11)
    outline_width = max(1, round(radius * 0.16))

    for row, col in marker_squares:
        cx, cy = board_center(row, col, grid)
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=style["fill"],
            outline=style["outline"],
            width=outline_width,
        )

    return Image.alpha_composite(canvas, overlay).convert("RGB")


def _render_xiangqi_board_binary(
    board: XiangqiBoard,
    image_size: int,
    highlight_squares: list[tuple[int, int]],
    arrow: XiangqiMove | None,
    xiangqi_setup_bin: str,
    svg_converter: str,
    board_theme: str,
    pieces_theme: str,
    annotations_theme: str,
) -> Image.Image:
    render_width_px = max(256, round(image_size * XQS_SETUP_NATURAL_WIDTH / XQS_SETUP_NATURAL_HEIGHT))

    with tempfile.TemporaryDirectory(prefix="xiangqi_setup_") as tmp_dir:
        tmp = Path(tmp_dir)
        use_annotations = bool(highlight_squares or arrow is not None)
        input_path = tmp / ("position.xay" if use_annotations else "position.fen")
        svg_path = tmp / "position.svg"

        if use_annotations:
            input_path.write_text(build_xay_document(board, highlight_squares, arrow), encoding="utf-8")
        else:
            input_path.write_text(board.fen() + "\n", encoding="utf-8")

        cmd = [
            xiangqi_setup_bin,
            "--board", board_theme,
            "--pieces", pieces_theme,
            "--annotations", annotations_theme,
            "--width-px", str(render_width_px),
            str(input_path),
            str(svg_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise RuntimeError(f"Cannot find '{xiangqi_setup_bin}'. Install xiangqi-setup or pass --xiangqi-setup-bin.") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise RuntimeError(f"xiangqi-setup failed: {stderr}") from exc

        rendered = svg_to_image(svg_path, svg_converter)

    canvas, _offset, _content_size = fit_image_to_square(rendered, image_size)
    return canvas.convert("RGB")


def build_xay_document(
    board: XiangqiBoard,
    highlight_squares: list[tuple[int, int]] | None = None,
    arrow: XiangqiMove | None = None,
) -> str:
    highlight_squares = highlight_squares or []
    use_annotations = bool(highlight_squares or arrow is not None)
    matrix: list[list[list[str]]] = []

    highlight_set = {(row, col) for row, col in highlight_squares}
    source_square = None if arrow is None else (arrow.from_row, arrow.from_col)
    target_square = None if arrow is None else (arrow.to_row, arrow.to_col)

    for row in range(10):
        row_cells: list[list[str]] = []
        for col in range(9):
            atoms: list[str] = []
            piece = board.piece_at(row, col)
            if piece != ".":
                atoms.append(piece)

            if (row, col) in highlight_set:
                atoms.append(annotation_code_for_square(board, row, col))

            if source_square == (row, col):
                atoms.append(annotation_code_for_square(board, row, col))
                dx = arrow.to_col - arrow.from_col
                dy = arrow.from_row - arrow.to_row
                atoms.append(arrow_annotation_code(dx, dy))

            if target_square == (row, col):
                atoms.append(annotation_code_for_square(board, row, col))

            row_cells.append(atoms)
        matrix.append(row_cells)

    return json.dumps({"version": "1", "setup": matrix}, ensure_ascii=False)


def annotation_code_for_square(board: XiangqiBoard, row: int, col: int) -> str:
    return "pm" if board.piece_at(row, col) != "." else "bm"


def arrow_annotation_code(dx: int, dy: int) -> str:
    if dx == 0:
        x_part = "+0"
    elif dx > 0:
        x_part = f"+{dx}"
    else:
        x_part = str(dx)

    if dy == 0:
        y_part = "+0"
    elif dy > 0:
        y_part = f"+{dy}"
    else:
        y_part = str(dy)

    return f"a{x_part}{y_part}"

def svg_to_image(svg_path: Path, svg_converter: str) -> Image.Image:
    svg_converter = svg_converter.lower()
    last_error = None

    if svg_converter in {"auto", "cairosvg"}:
        try:
            import cairosvg

            png_bytes = cairosvg.svg2png(url=str(svg_path))
            return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        except Exception as exc:
            if svg_converter != "auto":
                raise RuntimeError(f"cairosvg failed to convert SVG: {exc}") from exc
            last_error = exc

    for name, command in [
        ("rsvg-convert", lambda src, dst: ["rsvg-convert", "-o", str(dst), str(src)]),
        ("magick", lambda src, dst: ["magick", str(src), str(dst)]),
        ("inkscape", lambda src, dst: ["inkscape", str(src), "--export-type=png", "--export-filename", str(dst)]),
    ]:
        if svg_converter not in {"auto", name}:
            continue
        binary = shutil.which(name)
        if not binary:
            continue
        png_path = svg_path.with_suffix(f".{name}.png")
        try:
            subprocess.run(command(svg_path, png_path), check=True, capture_output=True, text=True)
            return Image.open(png_path).convert("RGBA")
        except Exception as exc:
            if svg_converter != "auto":
                raise RuntimeError(f"{name} failed to convert SVG: {exc}") from exc
            last_error = exc

    raise RuntimeError(
        "No SVG->PNG converter available. Install cairosvg, librsvg2-bin (rsvg-convert), ImageMagick, or Inkscape."
        + (f" Last error: {last_error}" if last_error else "")
    )


def fit_image_to_square(image: Image.Image, image_size: int):
    scale = min(image_size / image.width, image_size / image.height)
    resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (image_size, image_size), (255, 255, 255, 255))
    offset = ((image_size - resized.width) // 2, (image_size - resized.height) // 2)
    canvas.alpha_composite(resized, offset)
    return canvas, offset, resized.size


def board_center(row: int, col: int, grid: tuple[list[float], list[float]]):
    xs, ys = grid
    return xs[col], ys[row]


def average_spacing(points: list[float]) -> float:
    if len(points) < 2:
        return 40.0
    return sum(points[i + 1] - points[i] for i in range(len(points) - 1)) / (len(points) - 1)


def detect_xiangqi_grid(image: Image.Image) -> tuple[list[float], list[float]]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()

    x_scores = [0] * width
    y_scores = [0] * height

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            if not is_line_color(r, g, b):
                continue
            x_scores[x] += 1
            y_scores[y] += 1

    xs = select_grid_peaks(x_scores, expected=9, min_index=int(width * 0.04), max_index=int(width * 0.96))
    ys = select_grid_peaks(y_scores, expected=10, min_index=int(height * 0.04), max_index=int(height * 0.96))

    if len(xs) == 9 and len(ys) == 10:
        return xs, ys

    return fallback_grid_from_constants(width, height)


def is_line_color(r: int, g: int, b: int) -> bool:
    brightness = (r + g + b) / 3.0
    spread = max(r, g, b) - min(r, g, b)
    if brightness < 120:
        return True
    if brightness < 155 and spread < 48:
        return True
    return False


def select_grid_peaks(scores: list[int], expected: int, min_index: int, max_index: int) -> list[float]:
    if max_index <= min_index:
        return []
    trimmed = scores[min_index:max_index]
    if not trimmed:
        return []

    peak_threshold = max(trimmed) * 0.45
    groups: list[list[int]] = []
    current: list[int] = []
    for idx in range(min_index, max_index):
        if scores[idx] >= peak_threshold:
            current.append(idx)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    centers = [sum(group) / len(group) for group in groups if len(group) >= 2]
    if len(centers) < expected:
        ranked = sorted(range(min_index, max_index), key=lambda i: scores[i], reverse=True)
        selected: list[int] = []
        min_gap = max(8, (max_index - min_index) // (expected * 3))
        for idx in ranked:
            if any(abs(idx - prev) < min_gap for prev in selected):
                continue
            selected.append(idx)
            if len(selected) >= expected:
                break
        centers = sorted(float(x) for x in selected)
    else:
        centers = sorted(centers)

    if len(centers) > expected:
        centers = resample_evenly(centers, expected)
    return centers


def resample_evenly(points: list[float], expected: int) -> list[float]:
    if len(points) <= expected:
        return points
    if expected <= 1:
        return [points[len(points) // 2]]
    out = []
    for i in range(expected):
        pos = i * (len(points) - 1) / (expected - 1)
        out.append(points[round(pos)])
    return out


def fallback_grid_from_constants(width: int, height: int) -> tuple[list[float], list[float]]:
    scale_x = width / XQS_SETUP_NATURAL_WIDTH
    scale_y = height / XQS_SETUP_NATURAL_HEIGHT
    xs = [scale_x * (XQS_SETUP_BORDER_GAP_WIDTH + col * XQS_SETUP_FIELD_WIDTH) for col in range(9)]
    ys = [scale_y * (XQS_SETUP_BORDER_GAP_HEIGHT + row * XQS_SETUP_FIELD_HEIGHT) for row in range(10)]
    return xs, ys


def piece_descriptor(board: XiangqiBoard, row: int, col: int) -> str:
    piece = board.piece_at(row, col)
    color = "Red" if piece.isupper() else "Black"
    ptype = PIECE_TYPE_NAME[piece]

    if ptype == "king":
        return f"the {color} king"

    same = [(r, c) for r, c, p in board.side_pieces(color_of_piece(piece)) if p == piece]
    if ptype == "pawn":
        return f"the {color} pawn on {coord_to_ucci(row, col)}"

    if len(same) == 1:
        return f"the {color} {ptype}"

    ordered = sort_same_piece_positions(same, color_of_piece(piece))
    if len(ordered) == 2:
        label = "left" if ordered[0] == (row, col) else "right"
        return f"the {color} {label} {ptype}"
    if len(ordered) == 3:
        labels = ["left", "middle", "right"]
        label = labels[ordered.index((row, col))]
        return f"the {color} {label} {ptype}"
    return f"the {color} {ptype} on {coord_to_ucci(row, col)}"


def sort_same_piece_positions(positions: list[tuple[int, int]], color: str):
    if color == RED:
        return sorted(positions, key=lambda x: x[1])
    return sorted(positions, key=lambda x: -x[1])








