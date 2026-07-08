#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


POSITION_COORDS: dict[int, tuple[float, float]] = {
    1: (0.50, 0.90),
    2: (0.78, 0.74),
    3: (0.62, 0.76),
    4: (0.50, 0.77),
    5: (0.38, 0.76),
    6: (0.22, 0.74),
    7: (0.84, 0.68),
    8: (0.16, 0.68),
    9: (0.62, 0.63),
    10: (0.50, 0.64),
    11: (0.38, 0.63),
    12: (0.80, 0.54),
    13: (0.62, 0.55),
    14: (0.50, 0.54),
    15: (0.38, 0.55),
    16: (0.20, 0.54),
    17: (0.84, 0.34),
    18: (0.62, 0.43),
    19: (0.50, 0.42),
    20: (0.38, 0.43),
    21: (0.16, 0.34),
    22: (0.62, 0.24),
    23: (0.50, 0.20),
    24: (0.38, 0.24),
    25: (0.50, 0.31),
}

DEFAULT_CORNERS = ((170, 72), (854, 72), (968, 954), (56, 954))


@dataclass
class PlayerSlot:
    player_id: int
    player_name: str
    position_id: int
    position_name: str
    jersey_number: int | None = None


@dataclass
class FormationRecord:
    source_id: str
    match_id: int
    team_id: int
    team_name: str
    formation: str
    players: list[PlayerSlot]


@dataclass
class HighlightRecord:
    source_id: str
    match_id: int
    team_id: int
    team_name: str
    opponent_team_id: int
    opponent_team_name: str
    formation: str
    opponent_formation: str
    players: list[PlayerSlot]
    opponent_players: list[PlayerSlot]
    ball_handler_player_id: int
    ball_handler_name: str
    event_type: str
    event_minute: int
    event_second: int
    location: tuple[float, float]


def load_json_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding='utf-8').strip()
    if not text:
        return []
    if text[0] == '[':
        payload = json.loads(text)
        return [item for item in payload if isinstance(item, dict)]
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def dump_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def format_formation(value: Any) -> str:
    text = ''.join(ch for ch in str(value or '') if ch.isdigit())
    if len(text) <= 1:
        return text or 'unknown'
    return '-'.join(text)


def statsbomb_location_to_board(location: list[float] | tuple[float, float]) -> tuple[float, float]:
    if not location or len(location) < 2:
        return (0.5, 0.5)
    x = float(location[0])
    y = float(location[1])
    nx = max(0.04, min(0.96, y / 80.0))
    ny = max(0.04, min(0.96, 1.0 - x / 120.0))
    return nx, ny


def clamp_board_coord(value: float) -> float:
    return max(0.04, min(0.96, float(value)))


def metrica_location_to_board(location: list[float] | tuple[float, float]) -> tuple[float, float]:
    if not location or len(location) < 2:
        return (0.5, 0.5)
    x = clamp_board_coord(location[0])
    y = clamp_board_coord(location[1])
    return x, y


def canonical_position(position_id: int, mirror: bool = False) -> tuple[float, float]:
    nx, ny = POSITION_COORDS.get(position_id, (0.5, 0.55))
    if mirror:
        return (1.0 - nx, 1.0 - ny)
    return (nx, ny)


def project_point(nx: float, ny: float, corners: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]] = DEFAULT_CORNERS) -> tuple[int, int]:
    tl, tr, br, bl = corners
    left_x = tl[0] + (bl[0] - tl[0]) * ny
    left_y = tl[1] + (bl[1] - tl[1]) * ny
    right_x = tr[0] + (br[0] - tr[0]) * ny
    right_y = tr[1] + (br[1] - tr[1]) * ny
    x = left_x + (right_x - left_x) * nx
    y = left_y + (right_y - left_y) * nx
    return int(round(x)), int(round(y))


def _polyline(points: list[tuple[float, float]], corners=DEFAULT_CORNERS) -> list[tuple[int, int]]:
    return [project_point(nx, ny, corners) for nx, ny in points]


def _sample_circle(cx: float, cy: float, rx: float, ry: float, steps: int = 80) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for idx in range(steps + 1):
        t = (2.0 * math.pi * idx) / steps
        pts.append((cx + math.cos(t) * rx, cy + math.sin(t) * ry))
    return pts


def render_soccer_pitch(image_size: int = 1024) -> Image.Image:
    image = Image.new('RGB', (image_size, image_size), '#F2F2F2')
    draw = ImageDraw.Draw(image)
    corners = DEFAULT_CORNERS
    tl, tr, br, bl = corners
    pitch = [tl, tr, br, bl]
    draw.polygon(pitch, fill='#6EA63D')

    stripe_colors = ['#7CB547', '#6FA73F']
    for idx in range(10):
        y0 = idx / 10.0
        y1 = (idx + 1) / 10.0
        poly = [
            project_point(0.0, y0, corners),
            project_point(1.0, y0, corners),
            project_point(1.0, y1, corners),
            project_point(0.0, y1, corners),
        ]
        draw.polygon(poly, fill=stripe_colors[idx % 2])

    line_color = '#FFFFFF'
    draw.line(pitch + [pitch[0]], fill=line_color, width=5)
    draw.line([project_point(0.0, 0.5, corners), project_point(1.0, 0.5, corners)], fill=line_color, width=5)

    center_circle = _polyline(_sample_circle(0.5, 0.5, 0.11, 0.11), corners)
    draw.line(center_circle, fill=line_color, width=4)
    center_spot = project_point(0.5, 0.5, corners)
    draw.ellipse((center_spot[0] - 4, center_spot[1] - 4, center_spot[0] + 4, center_spot[1] + 4), fill=line_color)

    for y0, y1 in [(0.0, 0.18), (0.82, 1.0)]:
        pen_left = 0.21
        pen_right = 0.79
        six_left = 0.36
        six_right = 0.64
        pen_poly = [
            project_point(pen_left, y0, corners),
            project_point(pen_right, y0, corners),
            project_point(pen_right, y1, corners),
            project_point(pen_left, y1, corners),
            project_point(pen_left, y0, corners),
        ]
        draw.line(pen_poly, fill=line_color, width=4)
        goal_poly = [
            project_point(six_left, y0, corners),
            project_point(six_right, y0, corners),
            project_point(six_right, y0 + (y1 - y0) * 0.42, corners),
            project_point(six_left, y0 + (y1 - y0) * 0.42, corners),
            project_point(six_left, y0, corners),
        ] if y0 == 0.0 else [
            project_point(six_left, y1, corners),
            project_point(six_right, y1, corners),
            project_point(six_right, y1 - (y1 - y0) * 0.42, corners),
            project_point(six_left, y1 - (y1 - y0) * 0.42, corners),
            project_point(six_left, y1, corners),
        ]
        draw.line(goal_poly, fill=line_color, width=4)
        spot_y = y0 + 0.12 if y0 == 0.0 else y1 - 0.12
        spot = project_point(0.5, spot_y, corners)
        draw.ellipse((spot[0] - 4, spot[1] - 4, spot[0] + 4, spot[1] + 4), fill=line_color)

    return image


def draw_dot(canvas: Image.Image, coord: tuple[float, float], color: str = '#2AA7FF', radius: int = 15) -> None:
    draw = ImageDraw.Draw(canvas)
    x, y = project_point(coord[0], coord[1])
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline='#FFFFFF', width=3)


def draw_highlight_ring(canvas: Image.Image, coord: tuple[float, float], radius: int = 26, color: str = '#F28C28') -> None:
    draw = ImageDraw.Draw(canvas)
    x, y = project_point(coord[0], coord[1])
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=8)


def draw_ball(canvas: Image.Image, coord: tuple[float, float], radius: int = 10, fill: str = '#F6C445', outline: str = '#6B4E16') -> None:
    draw = ImageDraw.Draw(canvas)
    x, y = project_point(coord[0], coord[1])
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill, outline=outline, width=3)


def draw_trace(canvas: Image.Image, coords: list[tuple[float, float]], color: str = '#F28C28', width: int = 8) -> None:
    if len(coords) < 2:
        return
    draw = ImageDraw.Draw(canvas)
    points = [project_point(coord[0], coord[1]) for coord in coords]
    draw.line(points, fill=color, width=width)
    for point in points[:-1]:
        r = max(3, width // 2)
        draw.ellipse((point[0] - r, point[1] - r, point[0] + r, point[1] + r), fill=color)

    end = points[-1]
    prev = points[-2]
    dx = end[0] - prev[0]
    dy = end[1] - prev[1]
    norm = math.hypot(dx, dy)
    if norm < 1e-6:
        return
    ux = dx / norm
    uy = dy / norm
    arrow_len = 20
    arrow_half = 10
    base_x = end[0] - ux * arrow_len
    base_y = end[1] - uy * arrow_len
    px = -uy
    py = ux
    arrow = [
        end,
        (int(round(base_x + px * arrow_half)), int(round(base_y + py * arrow_half))),
        (int(round(base_x - px * arrow_half)), int(round(base_y - py * arrow_half))),
    ]
    draw.polygon(arrow, fill=color)


def draw_jersey(canvas: Image.Image, coord: tuple[float, float], fill: str = '#FFFFFF', outline: str = '#1F2430', scale: float = 1.0) -> None:
    draw = ImageDraw.Draw(canvas)
    x, y = project_point(coord[0], coord[1])
    body_half_w = int(18 * scale)
    body_half_h = int(24 * scale)
    shoulder_half_w = int(12 * scale)
    sleeve_out = int(12 * scale)
    sleeve_drop = int(6 * scale)
    hem_inset = int(5 * scale)
    neck_half = int(5 * scale)
    pts = [
        (x - shoulder_half_w, y - body_half_h),
        (x - shoulder_half_w - sleeve_out, y - body_half_h + sleeve_drop),
        (x - body_half_w, y - body_half_h + sleeve_drop + 5),
        (x - body_half_w + hem_inset, y + body_half_h),
        (x + body_half_w - hem_inset, y + body_half_h),
        (x + body_half_w, y - body_half_h + sleeve_drop + 5),
        (x + shoulder_half_w + sleeve_out, y - body_half_h + sleeve_drop),
        (x + shoulder_half_w, y - body_half_h),
        (x + neck_half, y - body_half_h),
        (x, y - body_half_h + 6),
        (x - neck_half, y - body_half_h),
    ]
    draw.polygon(pts, fill=fill, outline=outline)
    collar_y = y - body_half_h + 2
    draw.arc((x - 7, collar_y - 2, x + 7, collar_y + 8), start=0, end=180, fill=outline, width=2)


def slots_from_players(players: list[PlayerSlot | dict[str, Any]], mirror: bool = False) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for player in players:
        position_id = player.position_id if hasattr(player, 'position_id') else safe_int((player or {}).get('position_id'))
        coord = canonical_position(position_id, mirror=mirror)
        if coord in seen:
            coord = (coord[0] + 0.02, coord[1])
        seen.add(coord)
        out.append(coord)
    return out


def coords_from_tracking_players(players: list[dict[str, Any]]) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    for player in players:
        x = player.get('x')
        y = player.get('y')
        if x is None or y is None:
            continue
        coords.append(metrica_location_to_board((float(x), float(y))))
    return coords


def load_tactics_records(path: Path) -> list[dict[str, Any]]:
    return load_json_records(path)
