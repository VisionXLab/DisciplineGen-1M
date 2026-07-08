"""
Symmetric task rendering script
Generates input/GT image pairs and meta.json metadata files.
"""

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from tqdm import tqdm

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.patches import Polygon

OUTPUT_DIR = Path("./reflection_pairs")
INPUT_DIR = OUTPUT_DIR / "input"
GT_DIR = OUTPUT_DIR / "gt"
META_DIR = OUTPUT_DIR / "meta"
META_FILE = META_DIR / "meta.json"

SAMPLE_COUNT = 5000
RANDOM_SEED = None 

FIGSIZE = (7, 7)
DPI = 150


RADIUS_RANGE = (2.0, 8.0)

PAD_RATIO = (0.15, 0.40)

BG_COLORS = [
    "#ffffff", "#f7f8fa", "#faf8f5", "#f0f4f8",
    "#f5f5f5", "#fefefe", "#f8f6f0", "#eef2f7",
    "#fffdf5", "#f3f0eb", "#e8edf3", "#f9fafb",
]

GRID_STYLES = ["-", "--", ":", "-."]

AXIS_LINE_STYLES = ["--", "-.", "-", ":"]
AXIS_LINE_COLORS = [
    "#e74c3c", "#2ecc71", "#3498db", "#9b59b6",
    "#e67e22", "#1abc9c", "#d35400", "#8e44ad",
    "#c0392b", "#27ae60", "#2980b9", "#f39c12",
]



@dataclass
class SymmetryAxis:
    kind: str
    slope: Optional[float] = None
    intercept: Optional[float] = None
    a: float = 0.0
    b: float = 0.0
    c: float = 0.0
    label: str = ""


def make_x_axis() -> SymmetryAxis:
    return SymmetryAxis(kind="x_axis", a=0, b=1, c=0, label="y = 0")


def make_y_axis() -> SymmetryAxis:
    return SymmetryAxis(kind="y_axis", a=1, b=0, c=0, label="x = 0")


def make_line_axis(slope: int, intercept: int) -> SymmetryAxis:
    a = float(slope)
    b = -1.0
    c = float(intercept)
    if slope == 0:
        label = f"y = {intercept}"
    elif intercept == 0:
        label = f"y = {slope}x"
    elif intercept > 0:
        label = f"y = {slope}x + {intercept}"
    else:
        label = f"y = {slope}x - {abs(intercept)}"
    return SymmetryAxis(kind="line", slope=slope, intercept=intercept,
                        a=a, b=b, c=c, label=label)


def make_vertical_line_axis(x_val: int) -> SymmetryAxis:
    return SymmetryAxis(kind="line", slope=None, intercept=None,
                        a=1, b=0, c=-float(x_val),
                        label=f"x = {x_val}")


def make_horizontal_line_axis(y_val: int) -> SymmetryAxis:
    return SymmetryAxis(kind="line", slope=0, intercept=y_val,
                        a=0, b=1, c=-float(y_val),
                        label=f"y = {y_val}")


def is_axis_line(axis: SymmetryAxis) -> bool:
    return axis.kind in ("x_axis", "y_axis")


def reflect_point(x: float, y: float, axis: SymmetryAxis) -> Tuple[float, float]:
    a, b, c = axis.a, axis.b, axis.c
    d = a * a + b * b
    rx = x - 2 * a * (a * x + b * y + c) / d
    ry = y - 2 * b * (a * x + b * y + c) / d
    return (rx, ry)


def reflect_polygon(vertices: List[Tuple[float, float]], axis: SymmetryAxis) -> List[Tuple[float, float]]:
    return [reflect_point(x, y, axis) for x, y in vertices]




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
                  verts2: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    all_v = verts1 + verts2
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



def choose_symmetry_axis(cx: float, cy: float) -> SymmetryAxis:
    kind = random.choice(["x_axis", "y_axis", "horizontal", "vertical", "oblique"])

    if kind == "x_axis":
        return make_x_axis()
    elif kind == "y_axis":
        return make_y_axis()
    elif kind == "horizontal":
        c = random.randint(int(round(cy - 5)), int(round(cy + 5)))
        return make_horizontal_line_axis(c)
    elif kind == "vertical":
        c = random.randint(int(round(cx - 5)), int(round(cx + 5)))
        return make_vertical_line_axis(c)
    else:
        slope = random.choice([-2, -1, 1, 2])
        b_approx = cy - slope * cx
        intercept = round(b_approx)
        return make_line_axis(slope, intercept)




def generate_scene_params() -> dict:
    
    min_r = random.uniform(RADIUS_RANGE[0], RADIUS_RANGE[0] + (RADIUS_RANGE[1] - RADIUS_RANGE[0]) * 0.4)
    max_r = random.uniform(min_r * 1.1, RADIUS_RANGE[1])

    
    cx = random.uniform(5, 40)
    cy = random.uniform(5, 40)

   
    axis = choose_symmetry_axis(cx, cy)

  
    polygon = gen_convex_polygon(cx, cy, min_r, max_r)
    reflected = reflect_polygon(polygon, axis)


    bx_min, bx_max, by_min, by_max = combined_bbox(polygon, reflected)
    x_range, y_range = bbox_to_axis_range(bx_min, bx_max, by_min, by_max)

    return {
        "x_range": x_range,
        "y_range": y_range,
        "polygon": polygon,
        "reflected": reflected,
        "num_sides": len(polygon),
        "axis": axis,
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
        "refl_facecolor": rand_color(),
        "refl_edgecolor": rand_dark_color(),
        "refl_linewidth": random.uniform(1.5, 3.0),
        "refl_alpha": random.uniform(0.5, 0.85),
        "axis_line_color": random.choice(AXIS_LINE_COLORS),
        "axis_line_style": random.choice(AXIS_LINE_STYLES),
        "axis_line_width": random.uniform(1.8, 3.5),
        "axis_label_frac": random.uniform(0.6, 0.92),
    }




def draw_symmetry_axis(ax, params: dict):
    axis: SymmetryAxis = params["axis"]
    x_lo, x_hi = params["x_range"]
    y_lo, y_hi = params["y_range"]
    color = params["axis_line_color"]
    ls = params["axis_line_style"]
    lw = params["axis_line_width"]

    if axis.kind == "x_axis" or axis.kind == "y_axis":
        return

    label_frac = params["axis_label_frac"]

    if axis.b == 0:
        x_val = -axis.c / axis.a
        ax.axvline(x=x_val, color=color, linestyle=ls, linewidth=lw, alpha=0.8, zorder=5)
        label_y = y_lo + (y_hi - y_lo) * label_frac
        ax.text(x_val + (x_hi - x_lo) * 0.02, label_y, axis.label,
                fontsize=10, color=color, ha="left", va="bottom",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=color, alpha=0.7))
    elif axis.a == 0:
        y_val = -axis.c / axis.b
        ax.axhline(y=y_val, color=color, linestyle=ls, linewidth=lw, alpha=0.8, zorder=5)
        label_x = x_lo + (x_hi - x_lo) * label_frac
        ax.text(label_x, y_val + (y_hi - y_lo) * 0.02, axis.label,
                fontsize=10, color=color, ha="left", va="bottom",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=color, alpha=0.7))
    else:
        slope = axis.slope
        intercept = axis.intercept
        plot_x = [x_lo, x_hi]
        plot_y = [slope * x_lo + intercept, slope * x_hi + intercept]
        ax.plot(plot_x, plot_y, color=color, linestyle=ls, linewidth=lw, alpha=0.8, zorder=5)
        mid_x = (x_lo + x_hi) * label_frac
        mid_y = slope * mid_x + intercept
        ax.text(mid_x, mid_y + (y_hi - y_lo) * 0.03, axis.label,
                fontsize=10, color=color, ha="left", va="bottom",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=color, alpha=0.7))


def adaptive_figsize(x_range, y_range, base=7):
   
    y_span = y_range[1] - y_range[0]
    if x_span <= 0 or y_span <= 0:
        return (base, base)
    ratio = x_span / y_span
    if ratio >= 1:
        return (base, base / ratio)
    else:
        return (base * ratio, base)


def render_image(params: dict, output_path: Path, is_gt: bool):
    figsize = adaptive_figsize(params["x_range"], params["y_range"])
    fig, ax = plt.subplots(figsize=figsize, dpi=DPI)
    ax.set_facecolor(params["bg_color"])

    # 原始多边形（input 和 gt 都画）
    ax.add_patch(Polygon(
        params["polygon"], closed=True,
        facecolor=params["poly_facecolor"],
        edgecolor=params["poly_edgecolor"],
        linewidth=params["poly_linewidth"],
        alpha=params["poly_alpha"],
    ))

    if is_gt:
        # 对称后多边形
        ax.add_patch(Polygon(
            params["reflected"], closed=True,
            facecolor=params["refl_facecolor"],
            edgecolor=params["refl_edgecolor"],
            linewidth=params["refl_linewidth"],
            alpha=params["refl_alpha"],
        ))

    # 对称轴（非坐标轴时在 input 和 gt 中都画）
    if not is_axis_line(params["axis"]):
        draw_symmetry_axis(ax, params)

    # 坐标轴范围（严格包含两个图形）
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

    for idx in range(5001, SAMPLE_COUNT + 5001):
        params = generate_scene_params()
        name = f"{idx:06d}"

        input_path = INPUT_DIR / f"{name}_input.png"
        gt_path = GT_DIR / f"{name}_gt.png"

        render_image(params, input_path, is_gt=False)
        render_image(params, gt_path, is_gt=True)

        axis: SymmetryAxis = params["axis"]
        records.append({
            "index": idx,
            "input_image": str(input_path),
            "gt_image": str(gt_path),
            "symmetry_axis": {
                "kind": axis.kind,
                "label": axis.label,
                "a": axis.a,
                "b": axis.b,
                "c": axis.c,
                "slope": axis.slope,
                "intercept": axis.intercept,
            },
            "is_axis_line": is_axis_line(axis)
        })

        if idx % 500 == 0:
            print(f"  [{idx}/{SAMPLE_COUNT}] done")

    META_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {SAMPLE_COUNT} tasks -> {OUTPUT_DIR}")


if __name__ == "__main__":
    generate_tasks()
