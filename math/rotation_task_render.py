"""
Rotation-around-point task rendering script
Generates input/GT image pairs and meta.json metadata.

"""

import json
import math
import random
from pathlib import Path
from typing import List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.patches import Polygon

OUTPUT_DIR = Path("./rotation_pairs")
INPUT_DIR = OUTPUT_DIR / "input"
GT_DIR = OUTPUT_DIR / "gt"
META_DIR = OUTPUT_DIR / "meta"
META_FILE = META_DIR / "meta_rot.json"

SAMPLE_COUNT = 5000
RANDOM_SEED = None  

FIGSIZE = (7, 7)
DPI = 150
RADIUS_RANGE = (2.0, 8.0)
ANGLE_CHOICES = [20, 45, 60, 90, 120, 150, 180, 270]
PAD_RATIO = (0.15, 0.40)


BG_COLORS = [
    "#ffffff", "#f7f8fa", "#faf8f5", "#f0f4f8",
    "#f5f5f5", "#fefefe", "#f8f6f0", "#eef2f7",
    "#fffdf5", "#f3f0eb", "#e8edf3", "#f9fafb",
]

GRID_STYLES = ["-", "--", ":", "-."]

CENTER_MARKER_COLORS = [
    "#e74c3c", "#2ecc71", "#3498db", "#9b59b6",
    "#e67e22", "#1abc9c", "#d35400", "#8e44ad",
    "#c0392b", "#27ae60", "#2980b9", "#f39c12",
]




def rotate_point(x: float, y: float, cx: float, cy: float,
                 angle_rad: float) -> Tuple[float, float]:
  
    dx = x - cx
    dy = y - cy
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    rx = cx + dx * cos_a - dy * sin_a
    ry = cy + dx * sin_a + dy * cos_a
    return (rx, ry)


def rotate_polygon(vertices: List[Tuple[float, float]],
                   cx: float, cy: float,
                   angle_rad: float) -> List[Tuple[float, float]]:
    return [rotate_point(x, y, cx, cy, angle_rad) for x, y in vertices]



def convex_hull(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) <= 1:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def gen_convex_polygon(cx: float, cy: float, min_r: float, max_r: float,
                       min_sides: int = 3, max_sides: int = 7) -> List[Tuple[float, float]]:
    for _ in range(500):
        n_pts = random.randint(15, 30)
        pts = []
        for _ in range(n_pts):
            angle = random.uniform(0, 2 * math.pi)
            r = random.uniform(min_r, max_r)
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        hull = convex_hull(pts)
        if min_sides <= len(hull) <= max_sides:
            return hull

    sides = random.randint(min_sides, max_sides)
    a0 = random.uniform(0, 2 * math.pi)
    r = random.uniform(min_r, max_r)
    return [(cx + r * math.cos(a0 + 2 * math.pi * i / sides),
             cy + r * math.sin(a0 + 2 * math.pi * i / sides)) for i in range(sides)]




def rand_color() -> str:
    r = random.randint(30, 220)
    g = random.randint(30, 220)
    b = random.randint(30, 220)
    return f"#{r:02x}{g:02x}{b:02x}"


def rand_dark_color() -> str:
    r = random.randint(20, 120)
    g = random.randint(20, 120)
    b = random.randint(20, 120)
    return f"#{r:02x}{g:02x}{b:02x}"


def combined_bbox(verts1: List[Tuple[float, float]],
                  verts2: List[Tuple[float, float]],
                  extra_points: List[Tuple[float, float]] = None
                  ) -> Tuple[float, float, float, float]:
    all_v = verts1 + verts2
    if extra_points:
        all_v += extra_points
    xs = [v[0] for v in all_v]
    ys = [v[1] for v in all_v]
    return min(xs), max(xs), min(ys), max(ys)


def bbox_to_axis_range(x_min: float, x_max: float, y_min: float, y_max: float):
   
    x_span = x_max - x_min
    y_span = y_max - y_min

    pad_ratio = random.uniform(*PAD_RATIO)

    x_pad = max(x_span * pad_ratio, 1.0)
    y_pad = max(y_span * pad_ratio, 1.0)

   
    x_left_frac = random.uniform(0.3, 0.7)
    y_bottom_frac = random.uniform(0.3, 0.7)

    x_start = x_min - x_pad * x_left_frac
    x_end = x_max + x_pad * (1 - x_left_frac)
    y_start = y_min - y_pad * y_bottom_frac
    y_end = y_max + y_pad * (1 - y_bottom_frac)

  
    total_x = x_end - x_start
    total_y = y_end - y_start
    ratio = total_x / total_y if total_y > 0 else 1.0
    if ratio > 2:
        extra = (total_x - 2 * total_y) / 2
        y_start -= extra
        y_end += extra
    elif ratio < 0.5:
        extra = (total_y - 2 * total_x) / 2
        x_start -= extra
        x_end += extra

    
    x_start = math.floor(x_start)
    x_end = math.ceil(x_end)
    y_start = math.floor(y_start)
    y_end = math.ceil(y_end)

    return (x_start, x_end), (y_start, y_end)




def generate_scene_params() -> dict:
   
    min_r = random.uniform(RADIUS_RANGE[0], RADIUS_RANGE[0] + (RADIUS_RANGE[1] - RADIUS_RANGE[0]) * 0.4)
    max_r = random.uniform(min_r * 1.1, RADIUS_RANGE[1])

   
    poly_cx = random.uniform(5, 40)
    poly_cy = random.uniform(5, 40)

   
    rot_cx = round(poly_cx + random.randint(-5, 5))
    rot_cy = round(poly_cy + random.randint(-5, 5))

   
    angle_deg = random.choice(ANGLE_CHOICES)
    direction = random.choice(["cw", "ccw"])
  
    angle_rad = math.radians(angle_deg) if direction == "ccw" else -math.radians(angle_deg)

   
    polygon = gen_convex_polygon(poly_cx, poly_cy, min_r, max_r)
    rotated = rotate_polygon(polygon, rot_cx, rot_cy, angle_rad)

    
    bx_min, bx_max, by_min, by_max = combined_bbox(
        polygon, rotated, extra_points=[(rot_cx, rot_cy)]
    )
    x_range, y_range = bbox_to_axis_range(bx_min, bx_max, by_min, by_max)

   
    center_label_offset_frac = (random.uniform(0.02, 0.05), random.uniform(0.02, 0.05))

    return {
        "x_range": x_range,
        "y_range": y_range,
        "polygon": polygon,
        "rotated": rotated,
        "num_sides": len(polygon),
        "rot_cx": rot_cx,
        "rot_cy": rot_cy,
        "angle_deg": angle_deg,
        "direction": direction,
        "angle_rad": angle_rad,
        "bg_color": random.choice(BG_COLORS),
        "grid_style": random.choice(GRID_STYLES),
        "grid_color": rand_color(),
        "grid_alpha": random.uniform(0.15, 0.5),
        "spine_color": rand_dark_color(),
        "tick_color": rand_dark_color(),
        "poly_facecolor": rand_color(),
        "poly_edgecolor": rand_dark_color(),
        "poly_linewidth": random.uniform(1.5, 3.0),
        "poly_alpha": random.uniform(0.5, 0.85),
        "rot_facecolor": rand_color(),
        "rot_edgecolor": rand_dark_color(),
        "rot_linewidth": random.uniform(1.5, 3.0),
        "rot_alpha": random.uniform(0.5, 0.85),
        "center_marker_color": random.choice(CENTER_MARKER_COLORS),
        "center_marker_size": random.uniform(8, 14),
        "center_label_offset_frac": center_label_offset_frac,
    }



def adaptive_figsize(x_range, y_range, base=7):
   
    x_span = x_range[1] - x_range[0]
    y_span = y_range[1] - y_range[0]
    if x_span <= 0 or y_span <= 0:
        return (base, base)
    ratio = x_span / y_span
    if ratio >= 1:
        return (base, base / ratio)
    else:
        return (base * ratio, base)


def draw_rotation_center(ax, params: dict):
    
    rot_cx = params["rot_cx"]
    rot_cy = params["rot_cy"]
    color = params["center_marker_color"]
    ms = params["center_marker_size"]

    ax.plot(rot_cx, rot_cy, marker="o", markersize=ms,
            color=color, markeredgecolor="white", markeredgewidth=1.5,
            zorder=10)

    x_lo, x_hi = params["x_range"]
    y_lo, y_hi = params["y_range"]
    dx_frac, dy_frac = params["center_label_offset_frac"]
    label_x = rot_cx + (x_hi - x_lo) * dx_frac
    label_y = rot_cy + (y_hi - y_lo) * dy_frac

    label = f"({rot_cx}, {rot_cy})"
    ax.text(label_x, label_y, label,
            fontsize=9, color=color, ha="left", va="bottom",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=color, alpha=0.7),
            zorder=10)


def render_image(params: dict, output_path: Path, is_gt: bool):
    figsize = adaptive_figsize(params["x_range"], params["y_range"])
    fig, ax = plt.subplots(figsize=figsize, dpi=DPI)
    ax.set_facecolor(params["bg_color"])

    
    ax.add_patch(Polygon(
        params["polygon"], closed=True,
        facecolor=params["poly_facecolor"],
        edgecolor=params["poly_edgecolor"],
        linewidth=params["poly_linewidth"],
        alpha=params["poly_alpha"],
    ))

    if is_gt:
        
        ax.add_patch(Polygon(
            params["rotated"], closed=True,
            facecolor=params["rot_facecolor"],
            edgecolor=params["rot_edgecolor"],
            linewidth=params["rot_linewidth"],
            alpha=params["rot_alpha"],
        ))

   
    draw_rotation_center(ax, params)

   
    ax.set_xlim(*params["x_range"])
    ax.set_ylim(*params["y_range"])
    ax.set_aspect("equal")

    ax.grid(True, linestyle=params["grid_style"], color=params["grid_color"],
            alpha=params["grid_alpha"])
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    for spine in ax.spines.values():
        spine.set_color(params["spine_color"])
        spine.set_linewidth(1.2)

    ax.tick_params(colors=params["tick_color"], labelsize=10)
    ax.set_xlabel("x", fontsize=11, color=params["tick_color"])
    ax.set_ylabel("y", fontsize=11, color=params["tick_color"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, pad_inches=0.15)
    plt.close(fig)



def generate_tasks():
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED)

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    GT_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    records = []

    for idx in range(10001, SAMPLE_COUNT + 10001):
        params = generate_scene_params()
        name = f"{idx:06d}"

        input_path = INPUT_DIR / f"{name}_input.png"
        gt_path = GT_DIR / f"{name}_gt.png"

        render_image(params, input_path, is_gt=False)
        render_image(params, gt_path, is_gt=True)

        records.append({
            "index": idx,
            "input_image": str(input_path),
            "gt_image": str(gt_path),
            "rotation": {
                "center": {"x": params["rot_cx"], "y": params["rot_cy"]},
                "angle_deg": params["angle_deg"],
                "direction": params["direction"],
            }
        })

        if idx % 500 == 0:
            print(f"  [{idx}/{SAMPLE_COUNT}] done")

    META_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {SAMPLE_COUNT} tasks -> {OUTPUT_DIR}")


if __name__ == "__main__":
    generate_tasks()
