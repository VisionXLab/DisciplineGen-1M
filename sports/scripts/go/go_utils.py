#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

GTP_COLUMNS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"
WOOD_BG = (236, 216, 183)
GRID_COLOR = (124, 94, 58)
BLACK_STONE = (56, 45, 37)
WHITE_STONE = (248, 243, 236)
WHITE_EDGE = (195, 177, 152)
ANSWER_RED = (98, 78, 58)


@dataclass
class GoProblem:
    size: int
    black_stones: list[tuple[int, int]]
    white_stones: list[tuple[int, int]]
    to_play: str
    answer: tuple[int, int]
    category: str
    text: str | None = None
    source_id: str = ""
    meta: dict = field(default_factory=dict)


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in ["DejaVuSans-Bold.ttf", "Arial.ttf"]:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def sgf_coord_to_row_col(coord: str, size: int) -> tuple[int, int]:
    if len(coord) != 2:
        raise ValueError(f"Invalid SGF coord: {coord}")
    col = ord(coord[0]) - ord("a")
    row = ord(coord[1]) - ord("a")
    if not (0 <= row < size and 0 <= col < size):
        raise ValueError(f"SGF coord out of range: {coord} for board size {size}")
    return row, col


def gtp_to_row_col(coord: str, size: int) -> tuple[int, int]:
    coord = coord.strip().upper()
    if len(coord) < 2:
        raise ValueError(f"Invalid GTP coord: {coord}")
    col_char = coord[0]
    row_number = int(coord[1:])
    col = GTP_COLUMNS.index(col_char)
    row = size - row_number
    if not (0 <= row < size and 0 <= col < size):
        raise ValueError(f"GTP coord out of range: {coord} for board size {size}")
    return row, col


def row_col_to_gtp(row: int, col: int, size: int) -> str:
    return f"{GTP_COLUMNS[col]}{size - row}"


def normalize_coord(coord: str, size: int) -> tuple[int, int]:
    coord = coord.strip()
    if re.fullmatch(r"[a-z]{2}", coord):
        return sgf_coord_to_row_col(coord, size)
    return gtp_to_row_col(coord, size)


def _board_star_points(size: int) -> list[tuple[int, int]]:
    if size == 19:
        pts = [3, 9, 15]
    elif size == 13:
        pts = [3, 6, 9]
    elif size == 9:
        pts = [2, 4, 6]
    else:
        return []
    return [(r, c) for r in pts for c in pts]


def render_go_board(problem: GoProblem, image_size: int = 1024, show_answer: bool = False) -> Image.Image:
    board_size = problem.size
    canvas = Image.new("RGB", (image_size, image_size), WOOD_BG)
    draw = ImageDraw.Draw(canvas)

    margin = int(round(image_size * 0.07))
    step = (image_size - 2 * margin) / (board_size - 1)
    radius = max(10, int(step * 0.465))
    line_width = max(2, int(step * 0.032))
    dot_r = max(4, int(step * 0.07))
    coord_font = load_font(max(16, int(margin * 0.34)))
    coord_fill = (146, 112, 72)

    def center(row: int, col: int) -> tuple[float, float]:
        return margin + col * step, margin + row * step

    for idx in range(board_size):
        x0, y0 = center(0, idx)
        x1, y1 = center(board_size - 1, idx)
        draw.line((x0, y0, x1, y1), fill=GRID_COLOR, width=line_width)

        x0, y0 = center(idx, 0)
        x1, y1 = center(idx, board_size - 1)
        draw.line((x0, y0, x1, y1), fill=GRID_COLOR, width=line_width)

    for row, col in _board_star_points(board_size):
        cx, cy = center(row, col)
        draw.ellipse((cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r), fill=GRID_COLOR)

    for idx in range(board_size):
        label = GTP_COLUMNS[idx]
        cx, cy_top = center(0, idx)
        _, cy_bottom = center(board_size - 1, idx)
        draw.text((cx, margin * 0.38), label, font=coord_font, fill=coord_fill, anchor="mm")
        draw.text((cx, image_size - margin * 0.38), label, font=coord_font, fill=coord_fill, anchor="mm")

        row_label = str(board_size - idx)
        cx_left, cy = center(idx, 0)
        cx_right, _ = center(idx, board_size - 1)
        draw.text((margin * 0.38, cy), row_label, font=coord_font, fill=coord_fill, anchor="mm")
        draw.text((image_size - margin * 0.38, cy), row_label, font=coord_font, fill=coord_fill, anchor="mm")

    def draw_stone(row: int, col: int, color: str, answer_label: bool = False) -> None:
        cx, cy = center(row, col)
        bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
        if color == "black":
            draw.ellipse(bbox, fill=BLACK_STONE, outline=(28, 22, 18), width=max(2, radius // 10))
            label_fill = (246, 238, 224)
        else:
            draw.ellipse(bbox, fill=WHITE_STONE, outline=WHITE_EDGE, width=max(2, radius // 12))
            label_fill = ANSWER_RED

        if answer_label:
            font = load_font(max(18, int(radius * 0.95)))
            draw.text((cx, cy), "1", fill=label_fill, font=font, anchor="mm")

    for row, col in problem.black_stones:
        draw_stone(row, col, "black")
    for row, col in problem.white_stones:
        draw_stone(row, col, "white")

    if show_answer:
        draw_stone(problem.answer[0], problem.answer[1], problem.to_play, answer_label=True)

    return canvas


def build_instruction(problem: GoProblem) -> str:
    if problem.text:
        return problem.text

    side = "Black" if problem.to_play == "black" else "White"
    category = problem.category.lower()
    if "tesuji" in category:
        prefix = "A Tesuji problem."
    elif "life" in category or "death" in category:
        prefix = "A Life and Death Problem."
    elif "opening" in category:
        prefix = "An Opening Problem."
    else:
        prefix = "A Go problem."
    return f'{prefix} {side} to play. Please find the crucial first move and mark it with "1" on the board.'


def load_jsonl_problems(path: str) -> list[GoProblem]:
    problems: list[GoProblem] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        size = int(record.get("size", 19))
        answer = normalize_coord(record["answer"], size)
        to_play = (record.get("to_play") or record.get("answer_color") or "").strip().lower()
        if to_play in {"b", "black"}:
            to_play = "black"
        elif to_play in {"w", "white"}:
            to_play = "white"
        else:
            raise ValueError(f"Missing or invalid to_play in {path}:{line_no}")

        black_stones = [normalize_coord(c, size) for c in record.get("black_stones", [])]
        white_stones = [normalize_coord(c, size) for c in record.get("white_stones", [])]

        problems.append(
            GoProblem(
                size=size,
                black_stones=black_stones,
                white_stones=white_stones,
                to_play=to_play,
                answer=answer,
                category=record.get("category", "Go Problem"),
                text=record.get("text"),
                source_id=record.get("source_id", f"{Path(path).stem}_{line_no}"),
                meta=record.get("meta", {}),
            )
        )
    return problems


def split_sgf_collection(text: str) -> list[str]:
    trees: list[str] = []
    depth = 0
    start = None
    in_prop = False
    escaped = False
    for idx, ch in enumerate(text):
        if in_prop:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "]":
                in_prop = False
            continue
        if ch == "[":
            in_prop = True
            continue
        if ch == "(":
            if depth == 0:
                start = idx
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start is not None:
                trees.append(text[start:idx + 1])
                start = None
    return trees


def parse_sgf_node_props(node_text: str) -> dict[str, list[str]]:
    props: dict[str, list[str]] = {}
    i = 0
    while i < len(node_text):
        if not node_text[i].isalpha():
            i += 1
            continue
        j = i
        while j < len(node_text) and node_text[j].isalpha():
            j += 1
        key = node_text[i:j]
        values: list[str] = []
        i = j
        while i < len(node_text) and node_text[i] == "[":
            i += 1
            buf = []
            while i < len(node_text):
                ch = node_text[i]
                if ch == "\\" and i + 1 < len(node_text):
                    buf.append(node_text[i + 1])
                    i += 2
                    continue
                if ch == "]":
                    i += 1
                    break
                buf.append(ch)
                i += 1
            values.append("".join(buf))
        props[key] = values
    return props


def infer_category(*texts: str) -> str:
    merged = " ".join(t.lower() for t in texts if t)
    if any(k in merged for k in ["life and death", "live group", "死活"]):
        return "Life and Death"
    if any(k in merged for k in ["tesuji", "手筋"]):
        return "Tesuji"
    if any(k in merged for k in ["opening", "joseki", "布局"]):
        return "Opening Problem"
    return "Go Problem"


def parse_sgf_problem(tree_text: str, source_id: str) -> GoProblem | None:
    nodes = re.findall(r";([^;()]+)", tree_text, flags=re.S)
    if len(nodes) < 2:
        return None

    root = parse_sgf_node_props(nodes[0])
    move_props = None
    move_color = None
    for node in nodes[1:]:
        props = parse_sgf_node_props(node)
        if "B" in props and props["B"] and props["B"][0]:
            move_props = props
            move_color = "black"
            break
        if "W" in props and props["W"] and props["W"][0]:
            move_props = props
            move_color = "white"
            break
    if move_props is None or move_color is None:
        return None

    size = int(root.get("SZ", ["19"])[0])
    black_stones = [sgf_coord_to_row_col(v, size) for v in root.get("AB", []) if v]
    white_stones = [sgf_coord_to_row_col(v, size) for v in root.get("AW", []) if v]
    answer = sgf_coord_to_row_col(move_props["B"][0] if move_color == "black" else move_props["W"][0], size)

    comment = " ".join(root.get("C", []) + root.get("GN", []) + root.get("EV", []))
    category = infer_category(comment)
    return GoProblem(
        size=size,
        black_stones=black_stones,
        white_stones=white_stones,
        to_play=move_color,
        answer=answer,
        category=category,
        text=None,
        source_id=source_id,
        meta={"comment": comment} if comment else {},
    )


def load_sgf_problems(path: str) -> list[GoProblem]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    problems: list[GoProblem] = []
    for idx, tree in enumerate(split_sgf_collection(text), start=1):
        problem = parse_sgf_problem(tree, source_id=f"{Path(path).stem}_{idx}")
        if problem is not None:
            problems.append(problem)
    return problems




