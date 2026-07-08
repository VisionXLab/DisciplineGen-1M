"""
Translation task rendering script
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
from matplotlib.patches import FancyArrowPatch, Polygon
from tqdm import tqdm


OUTPUT_DIR = Path("./translation_pairs")
INPUT_DIR = OUTPUT_DIR / "input"
GT_DIR = OUTPUT_DIR / "gt"
META_DIR = OUTPUT_DIR / "meta"
META_FILE = META_DIR / "meta.json"

SAMPLE_COUNT = 5000
RANDOM_SEED = None  

FIGSIZE = (7, 7)
DPI = 150

RADIUS_RANGE = (2.0, 8.0)


SHIFT_RANGE = (3, 15)


PAD_RATIO = (0.15, 0.40)


BG_COLORS = [
    "#ffffff", "#f7f8fa", "#faf8f5", "#f0f4f8",
    "#f5f5f5", "#fefefe", "#f8f6f0", "#eef2f7",
    "#fffdf5", "#f3f0eb", "#e8edf3", "#f9fafb",
]

GRID_STYLES = ["-", "--", ":", "-."]



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



def generate_scene_params() -> dict:
    
    min_r = random.uniform(*RADIUS_RANGE[:1], RADIUS_RANGE[0] + (RADIUS_RANGE[1] - RADIUS_RANGE[0]) * 0.4)
    max_r = random.uniform(min_r * 1.1, RADIUS_RANGE[1])

    
    cx = random.uniform(5, 40)
    cy = random.uniform(5, 40)

    
    dx = dy = 0
    while dx == 0 and dy == 0:
        dx = random.randint(-SHIFT_RANGE[1], SHIFT_RANGE[1])
        dy = random.randint(-SHIFT_RANGE[1], SHIFT_RANGE[1])
    
    if abs(dx) < SHIFT_RANGE[0] and abs(dy) < SHIFT_RANGE[0]:
        if random.random() < 0.5:
            dx = random.choice([-1, 1]) * random.randint(*SHIFT_RANGE)
        else:
            dy = random.choice([-1, 1]) * random.randint(*SHIFT_RANGE)

   
    polygon = gen_convex_polygon(cx, cy, min_r, max_r)
    translated = [(x + dx, y + dy) for x, y in polygon]

    
    bx_min, bx_max, by_min, by_max = combined_bbox(polygon, translated)
    x_range, y_range = bbox_to_axis_range(bx_min, bx_max, by_min, by_max)

    return {
        "x_range": x_range,
        "y_range": y_range,
        "polygon": polygon,
        "translated": translated,
        "dx": dx,
        "dy": dy,
        "num_sides": len(polygon),
        "draw_vector": random.random() < 0.5,
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
        "trans_facecolor": rand_color(),
        "trans_edgecolor": rand_dark_color(),
        "trans_linewidth": random.uniform(1.5, 3.0),
        "trans_alpha": random.uniform(0.5, 0.85),
        "vector_color": rand_dark_color(),
    }



def adaptive_figsize(x_range, y_range, base=7):
    """根据坐标轴宽高比动态计算 figsize，避免 aspect=equal 时出现大面积空白"""
    x_span = x_range[1] - x_range[0]
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

   
    ax.add_patch(Polygon(
        params["polygon"], closed=True,
        facecolor=params["poly_facecolor"],
        edgecolor=params["poly_edgecolor"],
        linewidth=params["poly_linewidth"],
        alpha=params["poly_alpha"],
    ))

    if is_gt:
        
        ax.add_patch(Polygon(
            params["translated"], closed=True,
            facecolor=params["trans_facecolor"],
            edgecolor=params["trans_edgecolor"],
            linewidth=params["trans_linewidth"],
            alpha=params["trans_alpha"],
        ))

        
        if params["draw_vector"]:
            ox = sum(x for x, y in params["polygon"]) / len(params["polygon"])
            oy = sum(y for x, y in params["polygon"]) / len(params["polygon"])
            arrow = FancyArrowPatch(
                (ox, oy),
                (ox + params["dx"], oy + params["dy"]),
                arrowstyle='->,head_width=6,head_length=4',
                linewidth=2.0,
                color=params["vector_color"],
                zorder=10,
            )
            ax.add_patch(arrow)

    
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

    for idx in tqdm(range(1, SAMPLE_COUNT + 1), total=SAMPLE_COUNT, desc = "rendering"):
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
            "x_range": list(params["x_range"]),
            "y_range": list(params["y_range"]),
            "num_sides": params["num_sides"],
            "polygon": params["polygon"],
            "translated_polygon": params["translated"],
            "translation_vector": {"dx": params["dx"], "dy": params["dy"]},
            "draw_vector": params["draw_vector"],
            "style": {
                "bg_color": params["bg_color"],
                "grid_style": params["grid_style"],
                "grid_color": params["grid_color"],
                "grid_alpha": params["grid_alpha"],
                "spine_color": params["spine_color"],
                "tick_color": params["tick_color"],
                "original": {
                    "facecolor": params["poly_facecolor"],
                    "edgecolor": params["poly_edgecolor"],
                    "linewidth": params["poly_linewidth"],
                    "alpha": params["poly_alpha"],
                },
                "translated": {
                    "facecolor": params["trans_facecolor"],
                    "edgecolor": params["trans_edgecolor"],
                    "linewidth": params["trans_linewidth"],
                    "alpha": params["trans_alpha"],
                },
                "vector_color": params["vector_color"],
            },
        })

        

    META_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {SAMPLE_COUNT} tasks -> {OUTPUT_DIR}")


if __name__ == "__main__":
    generate_tasks()
