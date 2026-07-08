#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from itertools import combinations, permutations
from pathlib import Path
from typing import Any, Callable, Iterator

from PIL import Image, ImageDraw

from nutrition_utils import (
    FoodRecord,
    category_color,
    category_label,
    choose_distinct,
    draw_food_tile,
    lighten,
    load_font,
    load_food_records,
    load_object_image_for_box,
    normalize_text,
    point_on_curve,
    rounded_mask,
    sample_by_category,
    sample_by_predicate,
)


TASK_CHOICES = [
    "classify_grouping",
    "pie_chart_integration",
    "nutrition_pyramid",
    "highlight_high_gi",
    "glucose_curve_low_gi",
    "curve_label_gi",
    "low_intensity_distribution",
    "highlight_high_protein",
    "protein_curve_label",
    "fat_curve_draw",
    "all",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Sports Nutrition image-editing datasets from canonical nutrition JSON or JSONL.")
    parser.add_argument("--input-jsonl", default="", help="Canonical nutrition JSON/JSONL from the food assets pipeline.")
    parser.add_argument("--task", default="all", choices=TASK_CHOICES, help="Task to enumerate or render. Ignored when --render-plan-jsonl is used.")
    parser.add_argument("--output-root", default="", help="Render output directory.")
    parser.add_argument("--plan-jsonl", default="", help="If set, write the enumerated sample plan to this JSONL path without rendering.")
    parser.add_argument("--render-plan-jsonl", default="", help="If set, render dataset images from an existing plan JSONL.")
    parser.add_argument("--max-samples", type=int, default=100, help="Maximum number of plan entries or rendered samples. Use 0 for no cap.")
    parser.add_argument("--image-size", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def ensure_dirs(output_root: Path) -> tuple[str, Path, Path]:
    dataset_name = output_root.name
    editing_dir = output_root / "editing"
    gt_dir = output_root / "gt"
    editing_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)
    return dataset_name, editing_dir, gt_dir


def new_canvas(image_size: int) -> Image.Image:
    return Image.new("RGB", (image_size, image_size), "#F7F2E8")


def new_plain_canvas(image_size: int) -> Image.Image:
    return Image.new("RGB", (image_size, image_size), "#FFFFFF")


def draw_header(draw: ImageDraw.ImageDraw, image_size: int, title: str, subtitle: str = "") -> None:
    title_font = load_font(34)
    subtitle_font = load_font(20)
    draw.text((52, 40), title, font=title_font, fill="#20242B")
    if subtitle:
        draw.text((52, 88), subtitle, font=subtitle_font, fill="#5F6775")
    draw.line((48, 126, image_size - 48, 126), fill="#C8BDA8", width=3)


def grid_boxes(x0: int, y0: int, x1: int, y1: int, rows: int, cols: int, gap: int) -> list[tuple[int, int, int, int]]:
    total_w = x1 - x0
    total_h = y1 - y0
    card_w = (total_w - gap * (cols - 1)) // cols
    card_h = (total_h - gap * (rows - 1)) // rows
    boxes: list[tuple[int, int, int, int]] = []
    for row in range(rows):
        for col in range(cols):
            left = x0 + col * (card_w + gap)
            top = y0 + row * (card_h + gap)
            boxes.append((left, top, left + card_w, top + card_h))
    return boxes


def square_grid_boxes(x0: int, y0: int, x1: int, rows: int, cols: int, gap: int) -> list[tuple[int, int, int, int]]:
    total_w = x1 - x0
    tile = (total_w - gap * (cols - 1)) // cols
    boxes: list[tuple[int, int, int, int]] = []
    for row in range(rows):
        top = y0 + row * (tile + gap)
        for col in range(cols):
            left = x0 + col * (tile + gap)
            boxes.append((left, top, left + tile, top + tile))
    return boxes


def draw_stage_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str) -> None:
    draw.rounded_rectangle(box, radius=34, fill="#FBF7EF", outline="#D8CDBA", width=3)
    draw.text((box[0] + 20, box[1] + 16), title, font=load_font(24), fill="#20242B")


def draw_zone_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, color: str) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=30, fill=lighten(color, 0.82), outline=color, width=4)
    pill = (x0 + 16, y0 + 14, min(x0 + 250, x1 - 16), y0 + 58)
    draw.rounded_rectangle(pill, radius=18, fill=color)
    draw.text((pill[0] + 18, pill[1] + 10), label, font=load_font(20), fill="#FFFFFF")


def draw_pyramid_tier(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, color: str) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=28, fill=color, outline="#FFFFFF", width=3)
    draw.text((x0 + 18, y0 + 12), title, font=load_font(20), fill="#1E232B")


def draw_pie(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: int, distribution: list[tuple[str, float]]) -> list[tuple[str, float, float]]:
    x, y = center
    box = (x - radius, y - radius, x + radius, y + radius)
    start = -90.0
    slices: list[tuple[str, float, float]] = []
    for category, fraction in distribution:
        extent = fraction * 360.0
        draw.pieslice(box, start=start, end=start + extent, fill=category_color(category), outline="#FFFFFF", width=4)
        slices.append((category, start, start + extent))
        start += extent
    return slices


def draw_pie_labels(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: int, slices: list[tuple[str, float, float]]) -> None:
    cx, cy = center
    font = load_font(20)
    for category, start, end in slices:
        angle = math.radians((start + end) / 2)
        tx = int(cx + math.cos(angle) * radius * 0.62)
        ty = int(cy + math.sin(angle) * radius * 0.62)
        label = category_label(category).replace(" & ", "\n")
        draw.multiline_text((tx, ty), label, font=font, fill="#FFFFFF", anchor="mm", align="center")


def draw_curve_axes(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], y_label: str, x_label: str) -> None:
    x0, y0, x1, y1 = box
    draw.line((x0, y1, x1, y1), fill="#1F2430", width=4)
    draw.line((x0, y1, x0, y0), fill="#1F2430", width=4)
    font = load_font(20)
    draw.text((x1 - 80, y1 + 18), x_label, font=font, fill="#4F5968")
    draw.text((x0 - 16, y0 - 8), y_label, font=font, fill="#4F5968", anchor="rs")
    for idx in range(1, 5):
        y = int(y1 - (y1 - y0) * idx / 5)
        draw.line((x0, y, x1, y), fill="#D7CEBE", width=1)


def curve_xy(box: tuple[int, int, int, int], points: list[tuple[float, float]]) -> list[tuple[int, int]]:
    x0, y0, x1, y1 = box
    return [(int(x0 + (x1 - x0) * x), int(y1 - (y1 - y0) * y)) for x, y in points]


def generate_curve(kind: str, steps: int = 80) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for index in range(steps):
        x = index / (steps - 1)
        if kind == "high_gi":
            y = point_on_curve(x, 0.06, 0.18, 0.72, 0.18, 0.012)
        elif kind == "medium_gi":
            y = point_on_curve(x, 0.06, 0.28, 0.50, 0.14, 0.025)
        elif kind == "low_gi":
            y = point_on_curve(x, 0.06, 0.40, 0.32, 0.10, 0.055)
        elif kind == "whey":
            y = point_on_curve(x, 0.03, 0.18, 0.78, 0.10, 0.014)
        elif kind == "meat":
            y = point_on_curve(x, 0.03, 0.32, 0.46, 0.10, 0.035)
        elif kind == "casein":
            y = point_on_curve(x, 0.03, 0.48, 0.26, 0.09, 0.08)
        elif kind == "carb":
            y = point_on_curve(x, 0.05, 0.18, 0.68, 0.18, 0.018)
        elif kind == "protein":
            y = point_on_curve(x, 0.04, 0.35, 0.38, 0.09, 0.05)
        elif kind == "fat":
            y = point_on_curve(x, 0.03, 0.60, 0.18, 0.07, 0.12)
        else:
            y = 0.1
        out.append((x, max(0.03, min(0.95, y))))
    return out


def draw_curve(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], kind: str, color: str, width: int = 7) -> None:
    draw.line(curve_xy(box, generate_curve(kind)), fill=color, width=width, joint="curve")


def draw_legend(draw: ImageDraw.ImageDraw, items: list[tuple[str, str]], anchor: tuple[int, int]) -> None:
    x, y = anchor
    font = load_font(22)
    row_h = 34
    for index, (label, color) in enumerate(items):
        yy = y + index * row_h
        draw.line((x, yy + 12, x + 32, yy + 12), fill=color, width=7)
        draw.text((x + 44, yy), label, font=font, fill="#1F2430")


def draw_food_badge(canvas: Image.Image, center: tuple[int, int], record: FoodRecord, size: int = 86) -> None:
    draw = ImageDraw.Draw(canvas)
    cx, cy = center
    half = size // 2
    image_box = (cx - half, cy - half, cx + half, cy + half)
    loaded = load_object_image_for_box(record.preferred_image_path, (size, size), fill_ratio=0.84)
    if loaded is not None:
        mask = loaded.getchannel("A") if "A" in loaded.getbands() else rounded_mask(loaded.size, 18)
        canvas.paste(loaded, (image_box[0], image_box[1]), mask)
    else:
        draw.rounded_rectangle(image_box, radius=18, fill=lighten(category_color(record.primary_macro_category), 0.74), outline="#FFFFFF", width=2)
        draw.text((cx, cy - 3), record.title_text[:1].upper() or "F", font=load_font(28), fill="#FFFFFF", anchor="mm")
    draw.rounded_rectangle(image_box, radius=18, outline="#FFFFFF", width=3)


def resolve_object_box(box: tuple[int, int, int, int], object_size: int | None = None) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    if object_size is None:
        return box
    side = min(object_size, x1 - x0, y1 - y0)
    left = x0 + ((x1 - x0) - side) // 2
    top = y0 + ((y1 - y0) - side) // 2
    return (left, top, left + side, top + side)


def draw_food_object(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    record: FoodRecord,
    object_size: int | None = None,
) -> tuple[int, int, int, int]:
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = resolve_object_box(box, object_size)
    loaded = load_object_image_for_box(record.preferred_image_path, (x1 - x0, y1 - y0), fill_ratio=0.97)
    if loaded is not None:
        mask = loaded.getchannel("A") if "A" in loaded.getbands() else None
        if mask is None:
            canvas.paste(loaded, (x0, y0))
        else:
            canvas.paste(loaded, (x0, y0), mask)
        return (x0, y0, x1, y1)
    fallback = lighten(category_color(record.primary_macro_category), 0.65)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=fallback, outline="#E8E8E8", width=2)
    draw.text(((x0 + x1) // 2, (y0 + y1) // 2), record.title_text[:1].upper() or "F", font=load_font(32), fill="#FFFFFF", anchor="mm")
    return (x0, y0, x1, y1)


def apply_object_highlight_mask(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    record: FoodRecord,
    color: tuple[int, int, int] = (228, 63, 63),
    opacity: int = 118,
) -> None:
    x0, y0, x1, y1 = box
    loaded = load_object_image_for_box(record.preferred_image_path, (x1 - x0, y1 - y0), fill_ratio=0.97)
    if loaded is None:
        overlay = Image.new("RGBA", (x1 - x0, y1 - y0), color + (opacity,))
        mask = rounded_mask((x1 - x0, y1 - y0), 18)
        canvas.paste(overlay, (x0, y0), mask)
        return
    alpha = loaded.getchannel("A") if "A" in loaded.getbands() else Image.new("L", loaded.size, 255)
    mask = alpha.point(lambda p: int(p * opacity / 255))
    overlay = Image.new("RGBA", loaded.size, color + (0,))
    overlay.putalpha(mask)
    canvas.paste(overlay, (x0, y0), overlay)


def centered_positions(box: tuple[int, int, int, int], rows: int, cols: int, item_size: int, gap: int) -> list[tuple[int, int]]:
    x0, y0, x1, y1 = box
    total_w = cols * item_size + (cols - 1) * gap
    total_h = rows * item_size + (rows - 1) * gap
    start_x = x0 + max(0, (x1 - x0 - total_w) // 2) + item_size // 2
    start_y = y0 + max(0, (y1 - y0 - total_h) // 2) + item_size // 2
    points: list[tuple[int, int]] = []
    for row in range(rows):
        for col in range(cols):
            points.append((start_x + col * (item_size + gap), start_y + row * (item_size + gap)))
    return points


def draw_scrim(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str = "#F1E8D9") -> None:
    draw.rounded_rectangle(box, radius=22, fill=fill)


def auto_grid(rows_or_count: int, count: int | None = None) -> tuple[int, int]:
    total = rows_or_count if count is None else count
    cols = max(1, math.ceil(math.sqrt(total)))
    rows = max(1, math.ceil(total / cols))
    return rows, cols


def uniform_grid_boxes(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    count: int,
    gap: int = 18,
    square: bool = True,
) -> list[tuple[int, int, int, int]]:
    rows, cols = auto_grid(count)
    total_w = x1 - x0
    total_h = y1 - y0
    if square:
        tile = min(
            (total_w - gap * (cols - 1)) // cols,
            (total_h - gap * (rows - 1)) // rows,
        )
        used_w = cols * tile + gap * (cols - 1)
        used_h = rows * tile + gap * (rows - 1)
        start_x = x0 + max(0, (total_w - used_w) // 2)
        start_y = y0 + max(0, (total_h - used_h) // 2)
        boxes: list[tuple[int, int, int, int]] = []
        for idx in range(count):
            row = idx // cols
            col = idx % cols
            left = start_x + col * (tile + gap)
            top = start_y + row * (tile + gap)
            boxes.append((left, top, left + tile, top + tile))
        return boxes

    card_w = (total_w - gap * (cols - 1)) // cols
    card_h = (total_h - gap * (rows - 1)) // rows
    boxes = []
    for idx in range(count):
        row = idx // cols
        col = idx % cols
        left = x0 + col * (card_w + gap)
        top = y0 + row * (card_h + gap)
        boxes.append((left, top, left + card_w, top + card_h))
    return boxes


def draw_food_grid(
    canvas: Image.Image,
    records: list[FoodRecord],
    area: tuple[int, int, int, int],
    gap: int = 18,
    object_fill: float = 0.92,
) -> list[tuple[int, int, int, int]]:
    boxes = uniform_grid_boxes(*area, count=len(records), gap=gap, square=True)
    for box, record in zip(boxes, records):
        side = int(min(box[2] - box[0], box[3] - box[1]) * object_fill)
        draw_food_object(canvas, box, record, object_size=side)
    return boxes


def draw_highlight_block(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: str = "#E54880",
    padding: int = 16,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    highlight_box = (x0 - padding, y0 - padding, x1 + padding, y1 + padding)
    draw.rectangle(highlight_box, fill=fill)
    return highlight_box


def relative_box(center: tuple[float, float], side: int) -> tuple[int, int, int, int]:
    cx, cy = center
    half = side / 2.0
    return (
        int(round(cx - half)),
        int(round(cy - half)),
        int(round(cx + half)),
        int(round(cy + half)),
    )


def scaled_centers(image_size: int, centers: list[tuple[int, int]], base_size: int = 1024) -> list[tuple[int, int]]:
    return [
        (int(round(image_size * x / base_size)), int(round(image_size * y / base_size)))
        for x, y in centers
    ]


def scattered_food_boxes(image_size: int, count: int, layout: str) -> list[tuple[int, int, int, int]]:
    if layout == "grouping":
        base_centers = [
            (146, 196), (372, 184), (620, 188), (866, 194),
            (182, 430), (396, 450), (646, 430), (858, 448),
            (150, 708), (388, 718), (634, 700), (870, 714),
        ]
        side = int(round(image_size * 0.16))
    else:
        base_centers = [
            (152, 182), (392, 172), (642, 178), (864, 188),
            (208, 446), (482, 438), (782, 432),
            (310, 746), (680, 744),
        ]
        side = int(round(image_size * 0.155))
    centers = scaled_centers(image_size, base_centers[:count])
    return [relative_box(center, side) for center in centers]


def draw_grouping_reference_layout(canvas: Image.Image, grouped: list[tuple[str, list[FoodRecord]]], image_size: int) -> None:
    draw = ImageDraw.Draw(canvas)
    margin = int(round(image_size * 0.09))
    center_x = image_size // 2
    center_y = image_size // 2
    line_width = max(8, image_size // 110)
    draw.line((margin, center_y, image_size - margin, center_y), fill="#57AEF3", width=line_width)
    draw.line((center_x, margin, center_x, image_size - margin), fill="#57AEF3", width=line_width)

    gap = int(round(image_size * 0.05))
    quadrants = {
        "carb": (margin, margin, center_x - gap, center_y - gap),
        "protein": (center_x + gap, margin, image_size - margin, center_y - gap),
        "fruit_veg": (margin, center_y + gap, center_x - gap, image_size - margin),
        "fat": (center_x + gap, center_y + gap, image_size - margin, image_size - margin),
    }
    for category, items in grouped:
        boxes = uniform_grid_boxes(*quadrants[category], count=len(items), gap=int(round(image_size * 0.035)), square=True)
        for box, record in zip(boxes, items):
            side = int(min(box[2] - box[0], box[3] - box[1]) * 0.9)
            draw_food_object(canvas, box, record, object_size=side)


def group_panel_layout(image_size: int) -> dict[str, tuple[int, int, int, int]]:
    margin = 44
    gap = 22
    mid = image_size // 2
    return {
        'carb': (margin, margin, mid - gap // 2, mid - gap // 2),
        'protein': (mid + gap // 2, margin, image_size - margin, mid - gap // 2),
        'fruit_veg': (margin, mid + gap // 2, mid - gap // 2, image_size - margin),
        'fat': (mid + gap // 2, mid + gap // 2, image_size - margin, image_size - margin),
    }


def draw_group_panels(canvas: Image.Image, grouped: list[tuple[str, list[FoodRecord]]], image_size: int) -> None:
    draw = ImageDraw.Draw(canvas)
    panels = group_panel_layout(image_size)
    for category, items in grouped:
        panel = panels[category]
        draw.rounded_rectangle(panel, radius=30, fill=lighten(category_color(category), 0.82), outline=category_color(category), width=4)
        inner = (panel[0] + 18, panel[1] + 18, panel[2] - 18, panel[3] - 18)
        boxes = uniform_grid_boxes(*inner, count=len(items), gap=16, square=True)
        for box, record in zip(boxes, items):
            side = int(min(box[2] - box[0], box[3] - box[1]) * 0.88)
            draw_food_object(canvas, box, record, object_size=side)

def _interp_x(p0: tuple[int, int], p1: tuple[int, int], y: float) -> float:
    x0, y0 = p0
    x1, y1 = p1
    if y1 == y0:
        return float(min(x0, x1))
    t = (y - y0) / (y1 - y0)
    return x0 + (x1 - x0) * t


def triangle_x_bounds(triangle: list[tuple[int, int]], y: float) -> tuple[float, float]:
    apex = min(triangle, key=lambda p: p[1])
    base_points = sorted([p for p in triangle if p != apex], key=lambda p: p[0])
    left_base, right_base = base_points
    left_x = _interp_x(apex, left_base, y)
    right_x = _interp_x(apex, right_base, y)
    return left_x, right_x


def pyramid_square_slots(
    triangle: list[tuple[int, int]],
    y_top: int,
    side: int,
    count: int,
    margin: int = 10,
) -> list[tuple[int, int, int, int]]:
    safe_left, safe_right = triangle_x_bounds(triangle, y_top)
    left_edge = safe_left + margin
    right_edge = safe_right - margin
    if count == 1:
        cx = (left_edge + right_edge) / 2.0
        return [(int(round(cx - side / 2)), y_top, int(round(cx + side / 2)), y_top + side)]

    start = left_edge + side / 2.0
    end = right_edge - side / 2.0
    if end < start:
        cx = (left_edge + right_edge) / 2.0
        centers = [cx for _ in range(count)]
    else:
        step = (end - start) / (count - 1)
        centers = [start + idx * step for idx in range(count)]
    return [
        (int(round(cx - side / 2)), y_top, int(round(cx + side / 2)), y_top + side)
        for cx in centers
    ]


def normalize_angle_deg(angle: float) -> float:
    return angle % 360.0


def point_in_sector(
    point: tuple[float, float],
    center: tuple[int, int],
    radius: float,
    start_deg: float,
    end_deg: float,
    radial_margin: float = 0.0,
    angle_margin_deg: float = 0.0,
) -> bool:
    px, py = point
    cx, cy = center
    dx = px - cx
    dy = py - cy
    if dx * dx + dy * dy > max(0.0, radius - radial_margin) ** 2:
        return False
    angle = normalize_angle_deg(math.degrees(math.atan2(dy, dx)))
    start = normalize_angle_deg(start_deg + angle_margin_deg)
    end = normalize_angle_deg(end_deg - angle_margin_deg)
    if start <= end:
        return start <= angle <= end
    return angle >= start or angle <= end


def square_in_sector(
    box: tuple[int, int, int, int],
    center: tuple[int, int],
    radius: float,
    start_deg: float,
    end_deg: float,
    radial_margin: float = 0.0,
    angle_margin_deg: float = 0.0,
) -> bool:
    x0, y0, x1, y1 = box
    corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    return all(point_in_sector(corner, center, radius, start_deg, end_deg, radial_margin, angle_margin_deg) for corner in corners)


def sector_square_slots(
    center: tuple[int, int],
    radius: int,
    start_deg: float,
    end_deg: float,
    side: int,
    count: int,
    radial_margin: int = 12,
    angle_margin_deg: float = 6.0,
) -> list[tuple[int, int, int, int]]:
    span = (end_deg - start_deg) % 360.0
    if span == 0:
        span = 360.0
    mid = normalize_angle_deg(start_deg + span / 2.0)
    angle_offsets = [0.0, -14.0, 14.0, -24.0, 24.0, -32.0, 32.0]
    radial_fracs = [0.50, 0.68, 0.34, 0.80]
    candidates: list[tuple[int, int, int, int]] = []
    for frac in radial_fracs:
        r = radius * frac
        for offset in angle_offsets:
            angle = math.radians(mid + offset)
            cx = center[0] + math.cos(angle) * r
            cy = center[1] + math.sin(angle) * r
            box = (
                int(round(cx - side / 2)),
                int(round(cy - side / 2)),
                int(round(cx + side / 2)),
                int(round(cy + side / 2)),
            )
            if not square_in_sector(box, center, radius, start_deg, end_deg, radial_margin=radial_margin, angle_margin_deg=angle_margin_deg):
                continue
            candidates.append(box)
    picked: list[tuple[int, int, int, int]] = []
    for candidate in candidates:
        x0, y0, x1, y1 = candidate
        overlaps = False
        for px0, py0, px1, py1 in picked:
            if not (x1 <= px0 or px1 <= x0 or y1 <= py0 or py1 <= y0):
                overlaps = True
                break
        if overlaps:
            continue
        picked.append(candidate)
        if len(picked) >= count:
            break
    return picked


def build_classify_grouping(records: list[FoodRecord], rng: random.Random, image_size: int) -> dict[str, Any] | None:
    grouped: list[tuple[str, list[FoodRecord]]] = []
    for category in ["carb", "protein", "fruit_veg", "fat"]:
        picked = sample_by_category(records, category, 3, rng)
        if len(picked) < 3:
            return None
        grouped.append((category, picked[:3]))

    cards = [record for _, items in grouped for record in items]
    rng.shuffle(cards)

    before = new_plain_canvas(image_size)
    after = new_plain_canvas(image_size)

    for box, record in zip(scattered_food_boxes(image_size, len(cards), "grouping"), cards):
        side = int(min(box[2] - box[0], box[3] - box[1]) * 0.96)
        draw_food_object(before, box, record, object_size=side)
    draw_grouping_reference_layout(after, grouped, image_size)

    return {
        "before": before,
        "after": after,
        "text": "Classify the following foods according to their primary nutritional components, and visually group foods from the same category together in the image.",
        "meta": {
            "task_type": "classify_grouping",
            "foods": [record.food_name for record in cards],
            "source_ids": [record.source_id for record in cards],
            "used_real_images": sum(1 for record in cards if record.has_local_image),
        },
    }

def build_pie_chart_integration(records: list[FoodRecord], rng: random.Random, image_size: int) -> dict[str, Any] | None:
    grouped = {}
    selected: list[FoodRecord] = []
    for category in ["carb", "protein", "fruit_veg"]:
        picked = sample_by_category(records, category, 2, rng)
        if len(picked) < 2:
            return None
        grouped[category] = picked[:2]
        selected.extend(picked[:2])

    pending = [grouped[category][0] for category in ["protein", "carb", "fruit_veg"]]
    preplaced = [grouped[category][1] for category in ["protein", "carb", "fruit_veg"]]

    before = new_plain_canvas(image_size)
    after = new_plain_canvas(image_size)
    db = ImageDraw.Draw(before)
    da = ImageDraw.Draw(after)

    left_boxes = [
        (42, 140, 274, 372),
        (36, 410, 268, 642),
        (54, 680, 286, 912),
    ]
    for box, record in zip(left_boxes, pending):
        side = int(min(box[2] - box[0], box[3] - box[1]) * 0.96)
        draw_food_object(before, box, record, object_size=side)

    distribution = [("protein", 1 / 3), ("carb", 1 / 3), ("fruit_veg", 1 / 3)]
    before_center = (730, image_size // 2)
    after_center = (image_size // 2, image_size // 2)
    before_radius = 250
    after_radius = 340

    slices_before = draw_pie(db, before_center, before_radius, distribution)
    slices_after = draw_pie(da, after_center, after_radius, distribution)

    before_slice_map = {category: (start, end) for category, start, end in slices_before}
    after_slice_map = {category: (start, end) for category, start, end in slices_after}

    for category, record in zip(["protein", "carb", "fruit_veg"], preplaced):
        slots = sector_square_slots(before_center, before_radius, before_slice_map[category][0], before_slice_map[category][1], side=104, count=1, radial_margin=14, angle_margin_deg=7.0)
        if not slots:
            return None
        draw_food_object(before, slots[0], record, object_size=104)

    gt_side = None
    gt_slots_by_category = None
    for candidate_side in [136, 128, 120, 112, 104]:
        candidate_slots: dict[str, list[tuple[int, int, int, int]]] = {}
        valid = True
        for category in ["protein", "carb", "fruit_veg"]:
            items = grouped[category]
            slots = sector_square_slots(
                after_center,
                after_radius,
                after_slice_map[category][0],
                after_slice_map[category][1],
                side=candidate_side,
                count=len(items),
                radial_margin=10,
                angle_margin_deg=6.0,
            )
            if len(slots) < len(items):
                valid = False
                break
            candidate_slots[category] = slots
        if valid:
            gt_side = candidate_side
            gt_slots_by_category = candidate_slots
            break

    if gt_side is None or gt_slots_by_category is None:
        return None

    for category in ["protein", "carb", "fruit_veg"]:
        items = grouped[category]
        for box, record in zip(gt_slots_by_category[category], items):
            draw_food_object(after, box, record, object_size=gt_side)

    return {
        "before": before,
        "after": after,
        "text": "Take the foods listed on the left side of the pie chart, classify them by nutritional composition, and correctly integrate them into the existing pie chart.",
        "meta": {
            "task_type": "pie_chart_integration",
            "foods": [record.food_name for record in selected],
            "source_ids": [record.source_id for record in selected],
            "used_real_images": sum(1 for record in selected if record.has_local_image),
        },
    }

def build_nutrition_pyramid(records: list[FoodRecord], rng: random.Random, image_size: int) -> dict[str, Any] | None:
    base = sample_by_category(records, "carb", 4, rng)
    middle = sample_by_category(records, "fruit_veg", 4, rng)
    protein_upper = sample_by_category(records, "protein", 3, rng)
    fat_top = sample_by_category(records, "fat", 1, rng)
    if len(base) < 4 or len(middle) < 4 or len(protein_upper) < 3 or len(fat_top) < 1:
        return None

    foods = choose_distinct(base + middle + protein_upper + fat_top, 12, rng)
    if len(foods) < 12:
        return None

    before = new_plain_canvas(image_size)
    after = new_plain_canvas(image_size)
    draw_food_grid(before, foods, (40, 40, image_size - 40, image_size - 40), gap=16, object_fill=0.94)

    da = ImageDraw.Draw(after)
    triangle = [(130, image_size - 86), (image_size - 130, image_size - 86), (image_size // 2, 118)]
    da.polygon(triangle, fill="#C7C7C7")
    da.line(triangle + [triangle[0]], fill="#FFFFFF", width=8)
    da.line((236, 722, image_size - 236, 722), fill="#FFFFFF", width=8)
    da.line((318, 520, image_size - 318, 520), fill="#FFFFFF", width=8)
    da.line((402, 322, image_size - 402, 322), fill="#FFFFFF", width=8)

    top_box = pyramid_square_slots(triangle, y_top=182, side=82, count=1, margin=10)[0]
    upper_boxes = pyramid_square_slots(triangle, y_top=362, side=108, count=3, margin=10)
    mid_boxes = pyramid_square_slots(triangle, y_top=554, side=104, count=4, margin=12)
    base_boxes = pyramid_square_slots(triangle, y_top=752, side=118, count=4, margin=14)

    draw_food_object(after, top_box, fat_top[0], object_size=82)
    for box, record in zip(upper_boxes, protein_upper[:3]):
        draw_food_object(after, box, record, object_size=108)
    for box, record in zip(mid_boxes, middle[:4]):
        draw_food_object(after, box, record, object_size=104)
    for box, record in zip(base_boxes, base[:4]):
        draw_food_object(after, box, record, object_size=118)

    return {
        "before": before,
        "after": after,
        "text": "Based on the nutritional properties of the foods shown in the image, draw a nutrition pyramid that follows principles of sports nutrition.",
        "meta": {
            "task_type": "nutrition_pyramid",
            "foods": [record.food_name for record in foods],
            "source_ids": [record.source_id for record in foods],
            "used_real_images": sum(1 for record in foods if record.has_local_image),
        },
    }

def build_highlight_task(records: list[FoodRecord], rng: random.Random, image_size: int, mode: str) -> dict[str, Any] | None:
    if mode == "gi":
        positives = choose_distinct(sample_by_predicate(records, lambda record: record.is_high_gi, 4, rng), 4, rng)
        negatives = choose_distinct(sample_by_predicate(records, lambda record: record.gi_level in {"low", "medium"}, 5, rng), 5, rng)
        prompt = "Highlight all foods with a high Glycemic Index (GI) in red within the image."
        meta_key = "gi"
    else:
        positives = choose_distinct(sample_by_predicate(records, lambda record: record.is_high_protein, 4, rng), 4, rng)
        negatives = choose_distinct(sample_by_predicate(records, lambda record: not record.is_high_protein, 5, rng), 5, rng)
        prompt = "Highlight all foods with a high protein content in red within the image."
        meta_key = "protein"

    if len(positives) < 3 or len(negatives) < 4:
        return None

    selected = choose_distinct(positives + negatives, 9, rng)
    selected_positive_keys = {record.food_name for record in positives}
    positive_count = sum(1 for record in selected if record.food_name in selected_positive_keys)
    if len(selected) < 8 or positive_count < 3:
        return None
    rng.shuffle(selected)

    before = new_plain_canvas(image_size)
    after = new_plain_canvas(image_size)
    boxes = scattered_food_boxes(image_size, len(selected), "highlight")
    for box, record in zip(boxes, selected):
        side = int(min(box[2] - box[0], box[3] - box[1]) * 0.92)
        draw_food_object(before, box, record, object_size=side)
        if record.food_name in selected_positive_keys:
            draw_highlight_block(ImageDraw.Draw(after), box, fill="#E54880", padding=max(14, image_size // 60))
        draw_food_object(after, box, record, object_size=side)

    return {
        "before": before,
        "after": after,
        "text": prompt,
        "meta": {
            "task_type": f"highlight_high_{meta_key}",
            "foods": [record.food_name for record in selected],
            "positives": [record.food_name for record in selected if record.food_name in selected_positive_keys],
            "source_ids": [record.source_id for record in selected],
            "used_real_images": sum(1 for record in selected if record.has_local_image),
        },
    }

def build_glucose_curve_low_gi(_: list[FoodRecord], __: random.Random, image_size: int) -> dict[str, Any]:
    before = new_canvas(image_size)
    after = new_canvas(image_size)
    db = ImageDraw.Draw(before)
    da = ImageDraw.Draw(after)
    draw_header(db, image_size, "Blood Glucose Response", "High-GI response is shown; low-GI curve is missing.")
    draw_header(da, image_size, "Blood Glucose Response", "Low-GI response curve has been added.")
    chart_box = (120, 210, image_size - 110, image_size - 140)
    draw_curve_axes(db, chart_box, "Glucose", "Time")
    draw_curve_axes(da, chart_box, "Glucose", "Time")
    draw_curve(db, chart_box, "high_gi", "#D24C39")
    draw_curve(da, chart_box, "high_gi", "#D24C39")
    draw_curve(da, chart_box, "low_gi", "#4E88C7")
    draw_legend(db, [("High GI", "#D24C39")], (690, 210))
    draw_legend(da, [("High GI", "#D24C39"), ("Low GI", "#4E88C7")], (650, 210))
    return {
        "before": before,
        "after": after,
        "text": "Given a graph showing blood glucose levels over time after consuming high-GI foods, draw the corresponding blood glucose response curve for consuming low-GI foods.",
        "meta": {"task_type": "glucose_curve_low_gi"},
    }


def build_curve_label_gi(_: list[FoodRecord], __: random.Random, image_size: int) -> dict[str, Any]:
    before = new_canvas(image_size)
    after = new_canvas(image_size)
    db = ImageDraw.Draw(before)
    da = ImageDraw.Draw(after)
    draw_header(db, image_size, "Label GI Curves", "The three glucose curves are visible but unlabeled.")
    draw_header(da, image_size, "Label GI Curves", "Legend labels are added in the top-right corner.")
    chart_box = (120, 210, image_size - 110, image_size - 140)
    draw_curve_axes(db, chart_box, "Glucose", "Time")
    draw_curve_axes(da, chart_box, "Glucose", "Time")
    for kind, color in [("high_gi", "#D24C39"), ("medium_gi", "#DAA23A"), ("low_gi", "#4E88C7")]:
        draw_curve(db, chart_box, kind, color)
        draw_curve(da, chart_box, kind, color)
    draw_legend(da, [("High", "#D24C39"), ("Medium", "#DAA23A"), ("Low", "#4E88C7")], (700, 208))
    return {
        "before": before,
        "after": after,
        "text": "Label the top-right corner of the image with the GI level (High, Medium, Low) corresponding to each blood glucose curve.",
        "meta": {"task_type": "curve_label_gi"},
    }


def build_low_intensity_distribution(_: list[FoodRecord], __: random.Random, image_size: int) -> dict[str, Any]:
    before = new_canvas(image_size)
    after = new_canvas(image_size)
    db = ImageDraw.Draw(before)
    da = ImageDraw.Draw(after)
    draw_header(db, image_size, "Training Nutrition Distribution", "Normal training intensity distribution is shown.")
    draw_header(da, image_size, "Training Nutrition Distribution", "Pie chart is redrawn for low-intensity training.")
    normal = [("carb", 0.55), ("protein", 0.20), ("fat", 0.25)]
    low_intensity = [("carb", 0.45), ("protein", 0.25), ("fat", 0.30)]
    center = (512, 560)
    draw_pie(db, center, 270, normal)
    draw_pie(da, center, 270, low_intensity)
    draw_legend(db, [("Carb 55%", category_color("carb")), ("Protein 20%", category_color("protein")), ("Fat 25%", category_color("fat"))], (90, 210))
    draw_legend(da, [("Carb 45%", category_color("carb")), ("Protein 25%", category_color("protein")), ("Fat 30%", category_color("fat"))], (90, 210))
    return {
        "before": before,
        "after": after,
        "text": "Based on the nutrition distribution diagram for normal training intensity, redraw the nutrition distribution for a low-intensity training scenario.",
        "meta": {"task_type": "low_intensity_distribution"},
    }


def build_protein_curve_label(_: list[FoodRecord], __: random.Random, image_size: int) -> dict[str, Any]:
    before = new_canvas(image_size)
    after = new_canvas(image_size)
    db = ImageDraw.Draw(before)
    da = ImageDraw.Draw(after)
    draw_header(db, image_size, "Protein Source Curves", "Curves are drawn but not assigned to protein sources.")
    draw_header(da, image_size, "Protein Source Curves", "Legend labels whey, meat, and casein are added.")
    chart_box = (120, 210, image_size - 110, image_size - 140)
    draw_curve_axes(db, chart_box, "Amino acids", "Time")
    draw_curve_axes(da, chart_box, "Amino acids", "Time")
    for kind, color in [("whey", "#D24C39"), ("meat", "#D0A83C"), ("casein", "#5D8AC7")]:
        draw_curve(db, chart_box, kind, color)
        draw_curve(da, chart_box, kind, color)
    draw_legend(da, [("whey", "#D24C39"), ("meat", "#D0A83C"), ("casein", "#5D8AC7")], (690, 210))
    return {
        "before": before,
        "after": after,
        "text": "Label the top-right corner of the line chart with the protein source corresponding to each curve (whey, meat, casein).",
        "meta": {"task_type": "protein_curve_label"},
    }


def build_fat_curve_draw(_: list[FoodRecord], __: random.Random, image_size: int) -> dict[str, Any]:
    before = new_canvas(image_size)
    after = new_canvas(image_size)
    db = ImageDraw.Draw(before)
    da = ImageDraw.Draw(after)
    draw_header(db, image_size, "Macronutrient Intake Curves", "Carbohydrate and protein curves are present; FAT is missing.")
    draw_header(da, image_size, "Macronutrient Intake Curves", "The FAT curve is added to the chart.")
    chart_box = (120, 210, image_size - 110, image_size - 140)
    draw_curve_axes(db, chart_box, "Relative response", "Time")
    draw_curve_axes(da, chart_box, "Relative response", "Time")
    for kind, color in [("carb", "#E0A23A"), ("protein", "#C75A46")]:
        draw_curve(db, chart_box, kind, color)
        draw_curve(da, chart_box, kind, color)
    draw_curve(da, chart_box, "fat", "#4C7AB8")
    draw_legend(db, [("CARB", "#E0A23A"), ("PROTEIN", "#C75A46")], (660, 210))
    draw_legend(da, [("CARB", "#E0A23A"), ("PROTEIN", "#C75A46"), ("FAT", "#4C7AB8")], (660, 210))
    return {
        "before": before,
        "after": after,
        "text": "Draw the curve corresponding to FAT intake in the line chart.",
        "meta": {"task_type": "fat_curve_draw"},
    }


BUILDERS: dict[str, Callable[[list[FoodRecord], random.Random, int], dict[str, Any] | None]] = {
    "classify_grouping": build_classify_grouping,
    "pie_chart_integration": build_pie_chart_integration,
    "nutrition_pyramid": build_nutrition_pyramid,
    "highlight_high_gi": lambda records, rng, image_size: build_highlight_task(records, rng, image_size, "gi"),
    "glucose_curve_low_gi": build_glucose_curve_low_gi,
    "curve_label_gi": build_curve_label_gi,
    "low_intensity_distribution": build_low_intensity_distribution,
    "highlight_high_protein": lambda records, rng, image_size: build_highlight_task(records, rng, image_size, "protein"),
    "protein_curve_label": build_protein_curve_label,
    "fat_curve_draw": build_fat_curve_draw,
}


def required_food_data(task: str) -> bool:
    return task in {"classify_grouping", "pie_chart_integration", "nutrition_pyramid", "highlight_high_gi", "highlight_high_protein"}


TASK_ORDER = [task for task in TASK_CHOICES if task != "all"]


def _record_sort_key(record: FoodRecord) -> tuple[str, str]:
    return normalize_text(record.food_name), record.source_id


def _record_quality(record: FoodRecord) -> tuple[int, int, int, int, str]:
    return (
        1 if record.has_cutout_image else 0,
        1 if record.has_local_image else 0,
        1 if (record.display_name_zh or record.display_name) else 0,
        len(record.food_name),
        record.source_id,
    )


def canonicalize_food_records(records: list[FoodRecord]) -> list[FoodRecord]:
    chosen: dict[str, FoodRecord] = {}
    for record in records:
        key = normalize_text(record.food_name)
        if not key:
            continue
        existing = chosen.get(key)
        if existing is None or _record_quality(record) > _record_quality(existing):
            chosen[key] = record
    return sorted(chosen.values(), key=lambda record: (record.primary_macro_category, *_record_sort_key(record)))


def build_record_index(records: list[FoodRecord]) -> dict[str, FoodRecord]:
    return {record.source_id: record for record in records if record.source_id}


def category_pool(records: list[FoodRecord], category: str) -> list[FoodRecord]:
    return sorted((record for record in records if record.primary_macro_category == category), key=_record_sort_key)


def predicate_pool(records: list[FoodRecord], predicate) -> list[FoodRecord]:
    return sorted((record for record in records if predicate(record)), key=_record_sort_key)


def _source_ids(records: tuple[FoodRecord, ...] | list[FoodRecord]) -> list[str]:
    return [record.source_id for record in records]


def iter_classify_grouping_plans(records: list[FoodRecord]) -> Iterator[dict[str, Any]]:
    carb = category_pool(records, "carb")
    protein = category_pool(records, "protein")
    fruit_veg = category_pool(records, "fruit_veg")
    fat = category_pool(records, "fat")
    if len(carb) < 3 or len(protein) < 3 or len(fruit_veg) < 3 or len(fat) < 3:
        return
    for carb_group in combinations(carb, 3):
        carb_ids = _source_ids(carb_group)
        for protein_group in combinations(protein, 3):
            protein_ids = _source_ids(protein_group)
            for fruit_veg_group in combinations(fruit_veg, 3):
                fruit_veg_ids = _source_ids(fruit_veg_group)
                for fat_group in combinations(fat, 3):
                    yield {
                        "task_type": "classify_grouping",
                        "groups": {
                            "carb": carb_ids,
                            "protein": protein_ids,
                            "fruit_veg": fruit_veg_ids,
                            "fat": _source_ids(fat_group),
                        },
                    }


def iter_pie_chart_integration_plans(records: list[FoodRecord]) -> Iterator[dict[str, Any]]:
    carb = category_pool(records, "carb")
    protein = category_pool(records, "protein")
    fruit_veg = category_pool(records, "fruit_veg")
    if len(carb) < 2 or len(protein) < 2 or len(fruit_veg) < 2:
        return
    for carb_pair in permutations(carb, 2):
        for protein_pair in permutations(protein, 2):
            for fruit_veg_pair in permutations(fruit_veg, 2):
                yield {
                    "task_type": "pie_chart_integration",
                    "groups": {
                        "carb": {"pending": carb_pair[0].source_id, "preplaced": carb_pair[1].source_id},
                        "protein": {"pending": protein_pair[0].source_id, "preplaced": protein_pair[1].source_id},
                        "fruit_veg": {"pending": fruit_veg_pair[0].source_id, "preplaced": fruit_veg_pair[1].source_id},
                    },
                }


def iter_nutrition_pyramid_plans(records: list[FoodRecord]) -> Iterator[dict[str, Any]]:
    carb = category_pool(records, "carb")
    fruit_veg = category_pool(records, "fruit_veg")
    protein = category_pool(records, "protein")
    fat = category_pool(records, "fat")
    if len(carb) < 4 or len(fruit_veg) < 4 or len(protein) < 3 or len(fat) < 1:
        return
    for carb_group in combinations(carb, 4):
        carb_ids = _source_ids(carb_group)
        for fruit_veg_group in combinations(fruit_veg, 4):
            fruit_veg_ids = _source_ids(fruit_veg_group)
            for protein_group in combinations(protein, 3):
                protein_ids = _source_ids(protein_group)
                for fat_group in combinations(fat, 1):
                    yield {
                        "task_type": "nutrition_pyramid",
                        "tiers": {
                            "carb": carb_ids,
                            "fruit_veg": fruit_veg_ids,
                            "protein": protein_ids,
                            "fat": _source_ids(fat_group),
                        },
                    }


def iter_highlight_task_plans(records: list[FoodRecord], mode: str) -> Iterator[dict[str, Any]]:
    if mode == "gi":
        task_type = "highlight_high_gi"
        positives = predicate_pool(records, lambda record: record.is_high_gi)
        negatives = predicate_pool(records, lambda record: record.gi_level in {"low", "medium"})
    else:
        task_type = "highlight_high_protein"
        positives = predicate_pool(records, lambda record: record.is_high_protein)
        negatives = predicate_pool(records, lambda record: not record.is_high_protein)
    if len(positives) < 4 or len(negatives) < 5:
        return
    for positive_group in combinations(positives, 4):
        positive_ids = _source_ids(positive_group)
        for negative_group in combinations(negatives, 5):
            yield {
                "task_type": task_type,
                "positive_ids": positive_ids,
                "negative_ids": _source_ids(negative_group),
            }


def iter_static_task_plans(task_type: str) -> Iterator[dict[str, Any]]:
    yield {"task_type": task_type}


TASK_PLANNERS: dict[str, Callable[[list[FoodRecord]], Iterator[dict[str, Any]]]] = {
    "classify_grouping": iter_classify_grouping_plans,
    "pie_chart_integration": iter_pie_chart_integration_plans,
    "nutrition_pyramid": iter_nutrition_pyramid_plans,
    "highlight_high_gi": lambda records: iter_highlight_task_plans(records, "gi"),
    "glucose_curve_low_gi": lambda records: iter_static_task_plans("glucose_curve_low_gi"),
    "curve_label_gi": lambda records: iter_static_task_plans("curve_label_gi"),
    "low_intensity_distribution": lambda records: iter_static_task_plans("low_intensity_distribution"),
    "highlight_high_protein": lambda records: iter_highlight_task_plans(records, "protein"),
    "protein_curve_label": lambda records: iter_static_task_plans("protein_curve_label"),
    "fat_curve_draw": lambda records: iter_static_task_plans("fat_curve_draw"),
}


def iter_task_plans(task: str, records: list[FoodRecord]) -> Iterator[dict[str, Any]]:
    task_order = TASK_ORDER if task == "all" else [task]
    for current_task in task_order:
        if required_food_data(current_task) and not records:
            raise SystemExit(f"Task {current_task} requires --input-jsonl.")
        yield from TASK_PLANNERS[current_task](records)


def limit_iter(items: Iterator[dict[str, Any]], max_samples: int) -> Iterator[dict[str, Any]]:
    if max_samples <= 0:
        yield from items
        return
    for idx, item in enumerate(items):
        if idx >= max_samples:
            return
        yield item


def write_plan_jsonl(task: str, records: list[FoodRecord], output_path: Path, max_samples: int) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for count, plan in enumerate(limit_iter(iter_task_plans(task, records), max_samples), start=1):
            payload = {"plan_id": count, **plan}
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    if count == 0:
        raise SystemExit("No sports nutrition plan entries were generated.")
    print(f"Wrote {count} nutrition plan entries to {output_path}")
    return 0


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def stable_seed(source: str, seed: int) -> int:
    digest = hashlib.sha256(f"{source}|{seed}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def stable_shuffle(source_ids: list[str], label: str, seed: int) -> list[str]:
    shuffled = source_ids[:]
    random.Random(stable_seed(f"{label}|{'|'.join(source_ids)}", seed)).shuffle(shuffled)
    return shuffled


def resolve_records(record_index: dict[str, FoodRecord], source_ids: list[str]) -> list[FoodRecord]:
    resolved: list[FoodRecord] = []
    for source_id in source_ids:
        record = record_index.get(source_id)
        if record is None:
            raise SystemExit(f"Source id not found in --input-jsonl: {source_id}")
        resolved.append(record)
    return resolved


def count_real_images(records: list[FoodRecord]) -> int:
    return sum(1 for record in records if record.has_local_image)


def render_classify_grouping_plan(plan: dict[str, Any], record_index: dict[str, FoodRecord], image_size: int, seed: int) -> dict[str, Any]:
    grouped = [(category, resolve_records(record_index, plan["groups"][category])) for category in ["carb", "protein", "fruit_veg", "fat"]]
    card_ids = stable_shuffle([source_id for _, records in grouped for source_id in [record.source_id for record in records]], "classify_grouping", seed)
    cards = resolve_records(record_index, card_ids)

    before = new_plain_canvas(image_size)
    after = new_plain_canvas(image_size)
    for box, record in zip(scattered_food_boxes(image_size, len(cards), "grouping"), cards):
        side = int(min(box[2] - box[0], box[3] - box[1]) * 0.96)
        draw_food_object(before, box, record, object_size=side)
    draw_grouping_reference_layout(after, grouped, image_size)

    return {
        "before": before,
        "after": after,
        "text": "Classify the following foods according to their primary nutritional components, and visually group foods from the same category together in the image.",
        "meta": {
            "task_type": "classify_grouping",
            "foods": [record.food_name for record in cards],
            "source_ids": card_ids,
            "used_real_images": count_real_images(cards),
        },
    }


def render_pie_chart_integration_plan(plan: dict[str, Any], record_index: dict[str, FoodRecord], image_size: int) -> dict[str, Any]:
    groups = plan["groups"]
    pending = resolve_records(record_index, [groups[category]["pending"] for category in ["protein", "carb", "fruit_veg"]])
    preplaced = resolve_records(record_index, [groups[category]["preplaced"] for category in ["protein", "carb", "fruit_veg"]])
    selected_ids: list[str] = []
    for category in ["carb", "protein", "fruit_veg"]:
        selected_ids.extend([groups[category]["pending"], groups[category]["preplaced"]])
    selected = resolve_records(record_index, selected_ids)

    before = new_plain_canvas(image_size)
    after = new_plain_canvas(image_size)
    db = ImageDraw.Draw(before)
    da = ImageDraw.Draw(after)

    left_boxes = [
        (42, 140, 274, 372),
        (36, 410, 268, 642),
        (54, 680, 286, 912),
    ]
    for box, record in zip(left_boxes, pending):
        side = int(min(box[2] - box[0], box[3] - box[1]) * 0.96)
        draw_food_object(before, box, record, object_size=side)

    distribution = [("protein", 1 / 3), ("carb", 1 / 3), ("fruit_veg", 1 / 3)]
    before_center = (730, image_size // 2)
    after_center = (image_size // 2, image_size // 2)
    before_radius = 250
    after_radius = 340

    slices_before = draw_pie(db, before_center, before_radius, distribution)
    slices_after = draw_pie(da, after_center, after_radius, distribution)
    before_slice_map = {category: (start, end) for category, start, end in slices_before}
    after_slice_map = {category: (start, end) for category, start, end in slices_after}

    for category, record in zip(["protein", "carb", "fruit_veg"], preplaced):
        slots = sector_square_slots(before_center, before_radius, before_slice_map[category][0], before_slice_map[category][1], side=104, count=1, radial_margin=14, angle_margin_deg=7.0)
        if not slots:
            raise SystemExit("Could not find a valid preplaced slot for pie_chart_integration.")
        draw_food_object(before, slots[0], record, object_size=104)

    gt_side = None
    gt_slots_by_category = None
    for candidate_side in [136, 128, 120, 112, 104]:
        candidate_slots: dict[str, list[tuple[int, int, int, int]]] = {}
        valid = True
        for category in ["protein", "carb", "fruit_veg"]:
            items = [groups[category]["pending"], groups[category]["preplaced"]]
            slots = sector_square_slots(
                after_center,
                after_radius,
                after_slice_map[category][0],
                after_slice_map[category][1],
                side=candidate_side,
                count=len(items),
                radial_margin=10,
                angle_margin_deg=6.0,
            )
            if len(slots) < len(items):
                valid = False
                break
            candidate_slots[category] = slots
        if valid:
            gt_side = candidate_side
            gt_slots_by_category = candidate_slots
            break

    if gt_side is None or gt_slots_by_category is None:
        raise SystemExit("Could not resolve target slots for pie_chart_integration.")

    for category in ["protein", "carb", "fruit_veg"]:
        items = resolve_records(record_index, [groups[category]["pending"], groups[category]["preplaced"]])
        for box, record in zip(gt_slots_by_category[category], items):
            draw_food_object(after, box, record, object_size=gt_side)

    return {
        "before": before,
        "after": after,
        "text": "Take the foods listed on the left side of the pie chart, classify them by nutritional composition, and correctly integrate them into the existing pie chart.",
        "meta": {
            "task_type": "pie_chart_integration",
            "foods": [record.food_name for record in selected],
            "source_ids": selected_ids,
            "used_real_images": count_real_images(selected),
        },
    }


def render_nutrition_pyramid_plan(plan: dict[str, Any], record_index: dict[str, FoodRecord], image_size: int, seed: int) -> dict[str, Any]:
    tiers = plan["tiers"]
    base = resolve_records(record_index, tiers["carb"])
    middle = resolve_records(record_index, tiers["fruit_veg"])
    protein_upper = resolve_records(record_index, tiers["protein"])
    fat_top = resolve_records(record_index, tiers["fat"])
    food_ids = stable_shuffle(tiers["carb"] + tiers["fruit_veg"] + tiers["protein"] + tiers["fat"], "nutrition_pyramid", seed)
    foods = resolve_records(record_index, food_ids)

    before = new_plain_canvas(image_size)
    after = new_plain_canvas(image_size)
    draw_food_grid(before, foods, (40, 40, image_size - 40, image_size - 40), gap=16, object_fill=0.94)

    da = ImageDraw.Draw(after)
    triangle = [(130, image_size - 86), (image_size - 130, image_size - 86), (image_size // 2, 118)]
    da.polygon(triangle, fill="#C7C7C7")
    da.line(triangle + [triangle[0]], fill="#FFFFFF", width=8)
    da.line((236, 722, image_size - 236, 722), fill="#FFFFFF", width=8)
    da.line((318, 520, image_size - 318, 520), fill="#FFFFFF", width=8)
    da.line((402, 322, image_size - 402, 322), fill="#FFFFFF", width=8)

    top_box = pyramid_square_slots(triangle, y_top=182, side=82, count=1, margin=10)[0]
    upper_boxes = pyramid_square_slots(triangle, y_top=362, side=108, count=3, margin=10)
    mid_boxes = pyramid_square_slots(triangle, y_top=554, side=104, count=4, margin=12)
    base_boxes = pyramid_square_slots(triangle, y_top=752, side=118, count=4, margin=14)

    draw_food_object(after, top_box, fat_top[0], object_size=82)
    for box, record in zip(upper_boxes, protein_upper):
        draw_food_object(after, box, record, object_size=108)
    for box, record in zip(mid_boxes, middle):
        draw_food_object(after, box, record, object_size=104)
    for box, record in zip(base_boxes, base):
        draw_food_object(after, box, record, object_size=118)

    return {
        "before": before,
        "after": after,
        "text": "Based on the nutritional properties of the foods shown in the image, draw a nutrition pyramid that follows principles of sports nutrition.",
        "meta": {
            "task_type": "nutrition_pyramid",
            "foods": [record.food_name for record in foods],
            "source_ids": food_ids,
            "used_real_images": count_real_images(foods),
        },
    }


def render_highlight_plan(plan: dict[str, Any], record_index: dict[str, FoodRecord], image_size: int, seed: int) -> dict[str, Any]:
    task_type = str(plan["task_type"])
    if task_type == "highlight_high_gi":
        prompt = "Highlight all foods with a high Glycemic Index (GI) in red within the image."
        meta_key = "gi"
    else:
        prompt = "Highlight all foods with a high protein content in red within the image."
        meta_key = "protein"

    positive_ids = list(plan["positive_ids"])
    negative_ids = list(plan["negative_ids"])
    selected_ids = stable_shuffle(positive_ids + negative_ids, task_type, seed)
    selected = resolve_records(record_index, selected_ids)
    positive_set = set(positive_ids)

    before = new_plain_canvas(image_size)
    after = new_plain_canvas(image_size)
    boxes = scattered_food_boxes(image_size, len(selected), "highlight")
    for box, record in zip(boxes, selected):
        side = int(min(box[2] - box[0], box[3] - box[1]) * 0.92)
        draw_food_object(before, box, record, object_size=side)
        if record.source_id in positive_set:
            draw_highlight_block(ImageDraw.Draw(after), box, fill="#E54880", padding=max(14, image_size // 60))
        draw_food_object(after, box, record, object_size=side)

    return {
        "before": before,
        "after": after,
        "text": prompt,
        "meta": {
            "task_type": f"highlight_high_{meta_key}",
            "foods": [record.food_name for record in selected],
            "positives": [record.food_name for record in selected if record.source_id in positive_set],
            "source_ids": selected_ids,
            "used_real_images": count_real_images(selected),
        },
    }


def render_sample_from_plan(plan: dict[str, Any], record_index: dict[str, FoodRecord], image_size: int, seed: int) -> dict[str, Any]:
    task_type = str(plan.get("task_type", ""))
    if task_type == "classify_grouping":
        return render_classify_grouping_plan(plan, record_index, image_size, seed)
    if task_type == "pie_chart_integration":
        return render_pie_chart_integration_plan(plan, record_index, image_size)
    if task_type == "nutrition_pyramid":
        return render_nutrition_pyramid_plan(plan, record_index, image_size, seed)
    if task_type in {"highlight_high_gi", "highlight_high_protein"}:
        return render_highlight_plan(plan, record_index, image_size, seed)
    builder = BUILDERS.get(task_type)
    if builder is None:
        raise SystemExit(f"Unsupported task_type in plan: {task_type}")
    sample = builder([], random.Random(seed), image_size)
    if sample is None:
        raise SystemExit(f"Could not render task_type from plan: {task_type}")
    return sample


def render_dataset_from_plans(
    plans: Iterator[dict[str, Any]],
    output_root: Path,
    image_size: int,
    seed: int,
    record_index: dict[str, FoodRecord],
) -> int:
    dataset_name, editing_dir, gt_dir = ensure_dirs(output_root)
    json_path = output_root / f"{dataset_name}.json"
    count = 0
    first = True
    with json_path.open("w", encoding="utf-8") as handle:
        handle.write("[\n")
        for count, plan in enumerate(plans, start=1):
            sample = render_sample_from_plan(plan, record_index, image_size, seed)
            sample["before"].save(editing_dir / f"{count}_before.png")
            sample["after"].save(gt_dir / f"{count}_after.png")
            meta = dict(sample.get("meta", {}))
            if "plan_id" in plan:
                meta["plan_id"] = plan["plan_id"]
            item = {
                "text": sample["text"],
                "task_id": f"task_{count}",
                "image_path": f"{dataset_name}/editing/{count}_before.png",
                "gt": f"{dataset_name}/gt/{count}_after.png",
                "sub_task": "Sports Nutrition",
                "meta": meta,
            }
            if not first:
                handle.write(",\n")
            handle.write(json.dumps(item, ensure_ascii=False, indent=2))
            first = False
        handle.write("\n]\n")
    if count == 0:
        raise SystemExit("No sports nutrition samples were rendered.")
    print(f"Exported {count} sports nutrition samples to {output_root}")
    print(f"JSON written to {json_path}")
    return 0


def main() -> int:
    args = parse_args()
    raw_records = load_food_records(Path(args.input_jsonl)) if args.input_jsonl else []
    records = canonicalize_food_records(raw_records)
    record_index = build_record_index(records)

    if args.plan_jsonl:
        return write_plan_jsonl(args.task, records, Path(args.plan_jsonl), args.max_samples)

    if not args.output_root:
        raise SystemExit("--output-root is required when rendering.")

    if args.render_plan_jsonl:
        plan_iter = limit_iter(iter_jsonl(Path(args.render_plan_jsonl)), args.max_samples)
    else:
        plan_iter = limit_iter(iter_task_plans(args.task, records), args.max_samples)
    return render_dataset_from_plans(plan_iter, Path(args.output_root), args.image_size, args.seed, record_index)


if __name__ == "__main__":
    raise SystemExit(main())


