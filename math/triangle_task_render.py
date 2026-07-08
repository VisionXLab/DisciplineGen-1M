"""
Triange task rendering script
Generates input/GT image pairs and meta.json metadata files.
"""

import json
import math
import random
import string
from pathlib import Path
from typing import List, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


OUTPUT_DIR = Path("./triangle_pairs")
INPUT_DIR = OUTPUT_DIR / "input"
GT_DIR = OUTPUT_DIR / "gt"
META_DIR = OUTPUT_DIR / "meta"
META_FILE = META_DIR / "meta.json"

SAMPLE_COUNT = 10000
RANDOM_SEED = None  

DPI = 150
MIN_ANGLE_DEG = 10  


SIDE_RANGE = (4.0, 15.0)


PAD_RATIO = (0.15, 0.40)


BG_COLORS = [
    "#ffffff", "#f7f8fa", "#faf8f5", "#f0f4f8",
    "#f5f5f5", "#fefefe", "#f8f6f0", "#eef2f7",
    "#fffdf5", "#f3f0eb", "#e8edf3", "#f9fafb",
]

GRID_STYLES = ["-", "--", ":", "-."]

TASK_TYPES = ["altitude", "median", "midsegment", "bisector"]

TASK_LABELS = {
    "altitude": "高",
    "median": "中线",
    "midsegment": "中位线",
    "bisector": "角平分线",
}


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


def rand_bright_color() -> str:
    
    r = random.randint(150, 255)
    g = random.randint(30, 150)
    b = random.randint(30, 150)
    channels = [r, g, b]
    random.shuffle(channels)
    return f"#{channels[0]:02x}{channels[1]:02x}{channels[2]:02x}"




def angle_at_vertex(p: Tuple[float, float],
                    q: Tuple[float, float],
                    r: Tuple[float, float]) -> float:
   
    v1 = (p[0] - q[0], p[1] - q[1])
    v2 = (r[0] - q[0], r[1] - q[1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag1 = math.hypot(*v1)
    mag2 = math.hypot(*v2)
    if mag1 < 1e-9 or mag2 < 1e-9:
        return 0.0
    cos_val = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos_val))


def all_angles_ok(tri: List[Tuple[float, float]]) -> bool:
    a, b, c = tri
    return (angle_at_vertex(c, a, b) >= MIN_ANGLE_DEG and
            angle_at_vertex(a, b, c) >= MIN_ANGLE_DEG and
            angle_at_vertex(b, c, a) >= MIN_ANGLE_DEG)


def triangle_area(tri: List[Tuple[float, float]]) -> float:
    a, b, c = tri
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2.0


def gen_triangle(cx: float, cy: float) -> List[Tuple[float, float]]:
    
    for _ in range(2000):
        pts = []
        for _ in range(3):
            r = random.uniform(*SIDE_RANGE) * 0.5
            angle = random.uniform(0, 2 * math.pi)
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        if triangle_area(pts) < 2.0:
            continue
        if all_angles_ok(pts):
            return pts
   
    r = random.uniform(*SIDE_RANGE) * 0.5
    a0 = random.uniform(0, 2 * math.pi)
    return [(cx + r * math.cos(a0 + 2 * math.pi * i / 3),
             cy + r * math.sin(a0 + 2 * math.pi * i / 3)) for i in range(3)]


def choose_vertex_labels() -> List[str]:
   
    letters = random.sample(string.ascii_uppercase, 3)
    return letters




def foot_of_perpendicular(p: Tuple[float, float],
                          a: Tuple[float, float],
                          b: Tuple[float, float]) -> Tuple[float, float]:
   
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    return (a[0] + t * dx, a[1] + t * dy)


def midpoint(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float]:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def angle_bisector_foot(vertex: Tuple[float, float],
                        p1: Tuple[float, float],
                        p2: Tuple[float, float]) -> Tuple[float, float]:
   
    d1 = math.hypot(p1[0] - vertex[0], p1[1] - vertex[1])
    d2 = math.hypot(p2[0] - vertex[0], p2[1] - vertex[1])
    if d1 + d2 < 1e-9:
        return midpoint(p1, p2)
    
    fx = (d2 * p1[0] + d1 * p2[0]) / (d1 + d2)
    fy = (d2 * p1[1] + d1 * p2[1]) / (d1 + d2)
    return (fx, fy)




def points_bbox(points: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
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
   
    cx = random.uniform(5, 35)
    cy = random.uniform(5, 35)

    
    triangle = gen_triangle(cx, cy)
    labels = choose_vertex_labels()

   
    task_type = random.choice(TASK_TYPES)

  
    vertex_idx = random.randint(0, 2)
    opposite_idxs = [(vertex_idx + 1) % 3, (vertex_idx + 2) % 3]

    A = triangle[vertex_idx]
    B = triangle[opposite_idxs[0]]
    C = triangle[opposite_idxs[1]]

    aux_points = []  
    task_desc = ""

    if task_type == "altitude":
        
        foot = foot_of_perpendicular(A, B, C)
        aux_points = [A, foot]
        task_desc = f"Draw the altitude from vertex {labels[vertex_idx]} to side {labels[opposite_idxs[0]]}{labels[opposite_idxs[1]]}."

    elif task_type == "median":
        
        mid = midpoint(B, C)
        aux_points = [A, mid]
        task_desc = f"Draw the median from vertex {labels[vertex_idx]} to the midpoint of side {labels[opposite_idxs[0]]}{labels[opposite_idxs[1]]}."

    elif task_type == "midsegment":
        
        mid1 = midpoint(A, B)
        mid2 = midpoint(A, C)
        aux_points = [mid1, mid2]
        task_desc = f"Draw the midsegment parallel to side {labels[opposite_idxs[0]]}{labels[opposite_idxs[1]]}."

    elif task_type == "bisector":
        
        foot = angle_bisector_foot(A, B, C)
        aux_points = [A, foot]
        task_desc = f"Draw the angle bisector from vertex {labels[vertex_idx]} to side {labels[opposite_idxs[0]]}{labels[opposite_idxs[1]]}."

    
    all_points = list(triangle) + aux_points
    bx_min, bx_max, by_min, by_max = points_bbox(all_points)
    x_range, y_range = bbox_to_axis_range(bx_min, bx_max, by_min, by_max)

    
    show_axes = random.random() < 0.5
    show_grid = random.random() < 0.5

    return {
        "triangle": triangle,
        "labels": labels,
        "task_type": task_type,
        "task_desc": task_desc,
        "vertex_idx": vertex_idx,
        "opposite_idxs": opposite_idxs,
        "aux_points": aux_points,
        "x_range": x_range,
        "y_range": y_range,
        "show_axes": show_axes,
        "show_grid": show_grid,
        "bg_color": random.choice(BG_COLORS),
        "grid_style": random.choice(GRID_STYLES),
        "grid_color": rand_color(),
        "grid_alpha": random.uniform(0.15, 0.5),
        "spine_color": rand_dark_color(),
        "tick_color": rand_dark_color(),
        "tri_edgecolor": rand_dark_color(),
        "tri_linewidth": random.uniform(1.5, 3.5),
        "tri_facecolor": rand_color(),
        "tri_alpha": random.uniform(0.15, 0.45),
        "vertex_size": random.uniform(30, 70),
        "vertex_color": rand_dark_color(),
        "label_fontsize": random.uniform(12, 16),
        "label_color": rand_dark_color(),
        "aux_color": rand_bright_color(),
        "aux_linewidth": random.uniform(1.5, 3.5),
        "aux_linestyle": random.choice(["-", "--", "-."]),
        "mark_color": rand_dark_color(),
        "mark_size": random.uniform(6, 12),
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


def draw_right_angle_mark(ax, vertex, p1, p2, size, color, linewidth=1.2):
   
    d1 = (p1[0] - vertex[0], p1[1] - vertex[1])
    d2 = (p2[0] - vertex[0], p2[1] - vertex[1])
    mag1 = math.hypot(*d1)
    mag2 = math.hypot(*d2)
    if mag1 < 1e-9 or mag2 < 1e-9:
        return
    u1 = (d1[0] / mag1 * size, d1[1] / mag1 * size)
    u2 = (d2[0] / mag2 * size, d2[1] / mag2 * size)
    sq = [
        (vertex[0] + u1[0], vertex[1] + u1[1]),
        (vertex[0] + u1[0] + u2[0], vertex[1] + u1[1] + u2[1]),
        (vertex[0] + u2[0], vertex[1] + u2[1]),
    ]
    xs = [vertex[0] + u1[0], sq[1][0], vertex[0] + u2[0]]
    ys = [vertex[1] + u1[1], sq[1][1], vertex[1] + u2[1]]
    ax.plot(xs, ys, color=color, linewidth=linewidth, zorder=8)


def draw_midpoint_mark(ax, p1, p2, color, size=0.3, linewidth=1.5):
    
    mx, my = midpoint(p1, p2)
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    mag = math.hypot(dx, dy)
    if mag < 1e-9:
        return
    
    nx = -dy / mag * size
    ny = dx / mag * size
    ax.plot([mx - nx, mx + nx], [my - ny, my + ny],
            color=color, linewidth=linewidth, zorder=8)


def render_image(params: dict, output_path: Path, is_gt: bool):
    figsize = adaptive_figsize(params["x_range"], params["y_range"])
    fig, ax = plt.subplots(figsize=figsize, dpi=DPI)
    ax.set_facecolor(params["bg_color"])

    tri = params["triangle"]
    labels = params["labels"]

    
    tri_closed = list(tri) + [tri[0]]
    tri_xs = [p[0] for p in tri_closed]
    tri_ys = [p[1] for p in tri_closed]

    
    ax.fill([p[0] for p in tri], [p[1] for p in tri],
            color=params["tri_facecolor"], alpha=params["tri_alpha"], zorder=2)
    
    ax.plot(tri_xs, tri_ys,
            color=params["tri_edgecolor"],
            linewidth=params["tri_linewidth"],
            zorder=3)

   
    for i, (px, py) in enumerate(tri):
        ax.scatter(px, py, s=params["vertex_size"],
                   color=params["vertex_color"], zorder=6)

       
        cx_tri = sum(p[0] for p in tri) / 3
        cy_tri = sum(p[1] for p in tri) / 3
        dx = px - cx_tri
        dy = py - cy_tri
        mag = math.hypot(dx, dy)
        if mag > 1e-9:
            offset_x = dx / mag * 0.55
            offset_y = dy / mag * 0.55
        else:
            offset_x, offset_y = 0.5, 0.5

        ax.text(px + offset_x, py + offset_y, labels[i],
                fontsize=params["label_fontsize"],
                fontweight="bold",
                color=params["label_color"],
                ha="center", va="center",
                zorder=7)

    
    if is_gt:
        aux = params["aux_points"]
        task_type = params["task_type"]

        if task_type == "altitude":
           
            ax.plot([aux[0][0], aux[1][0]], [aux[0][1], aux[1][1]],
                    color=params["aux_color"],
                    linewidth=params["aux_linewidth"],
                    linestyle=params["aux_linestyle"],
                    zorder=5)
           
            ax.scatter(aux[1][0], aux[1][1], s=params["mark_size"] ** 2,
                       color=params["aux_color"], marker="o", zorder=6)
           
            foot = aux[1]
            vertex = aux[0]
            B = tri[params["opposite_idxs"][0]]
            x_span = params["x_range"][1] - params["x_range"][0]
            mark_sz = x_span * 0.025
            draw_right_angle_mark(ax, foot, vertex, B, mark_sz,
                                  params["aux_color"], linewidth=1.5)

        elif task_type == "median":
            
            ax.plot([aux[0][0], aux[1][0]], [aux[0][1], aux[1][1]],
                    color=params["aux_color"],
                    linewidth=params["aux_linewidth"],
                    linestyle=params["aux_linestyle"],
                    zorder=5)
            
            ax.scatter(aux[1][0], aux[1][1], s=params["mark_size"] ** 2,
                       color=params["aux_color"], marker="o", zorder=6)
            
            B = tri[params["opposite_idxs"][0]]
            C = tri[params["opposite_idxs"][1]]
            x_span = params["x_range"][1] - params["x_range"][0]
            draw_midpoint_mark(ax, B, aux[1], params["aux_color"],
                               size=x_span * 0.02, linewidth=1.5)
            draw_midpoint_mark(ax, aux[1], C, params["aux_color"],
                               size=x_span * 0.02, linewidth=1.5)

        elif task_type == "midsegment":
            
            ax.plot([aux[0][0], aux[1][0]], [aux[0][1], aux[1][1]],
                    color=params["aux_color"],
                    linewidth=params["aux_linewidth"],
                    linestyle=params["aux_linestyle"],
                    zorder=5)
            
            ax.scatter(aux[0][0], aux[0][1], s=params["mark_size"] ** 2,
                       color=params["aux_color"], marker="o", zorder=6)
            ax.scatter(aux[1][0], aux[1][1], s=params["mark_size"] ** 2,
                       color=params["aux_color"], marker="o", zorder=6)

        elif task_type == "bisector":
            
            ax.plot([aux[0][0], aux[1][0]], [aux[0][1], aux[1][1]],
                    color=params["aux_color"],
                    linewidth=params["aux_linewidth"],
                    linestyle=params["aux_linestyle"],
                    zorder=5)
            
            ax.scatter(aux[1][0], aux[1][1], s=params["mark_size"] ** 2,
                       color=params["aux_color"], marker="o", zorder=6)
            
            A = aux[0]
            B = tri[params["opposite_idxs"][0]]
            C = tri[params["opposite_idxs"][1]]
            x_span = params["x_range"][1] - params["x_range"][0]
            arc_r = x_span * 0.06
            ang_b = math.atan2(B[1] - A[1], B[0] - A[0])
            ang_c = math.atan2(C[1] - A[1], C[0] - A[0])
            
            if ang_c < ang_b:
                ang_b, ang_c = ang_c, ang_b
            if ang_c - ang_b > math.pi:
                ang_b, ang_c = ang_c, ang_b + 2 * math.pi
            arc_angles = [ang_b + (ang_c - ang_b) * t / 30 for t in range(31)]
            arc_xs = [A[0] + arc_r * math.cos(a) for a in arc_angles]
            arc_ys = [A[1] + arc_r * math.sin(a) for a in arc_angles]
            ax.plot(arc_xs, arc_ys, color=params["aux_color"],
                    linewidth=1.2, zorder=5)

    
    ax.set_xlim(*params["x_range"])
    ax.set_ylim(*params["y_range"])
    ax.set_aspect("equal")

    
    if params["show_grid"]:
        ax.grid(True, linestyle=params["grid_style"],
                color=params["grid_color"], alpha=params["grid_alpha"])
    else:
        ax.grid(False)

    if params["show_axes"]:
        ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        for spine in ax.spines.values():
            spine.set_color(params["spine_color"])
            spine.set_linewidth(1.2)
        ax.tick_params(colors=params["tick_color"], labelsize=10)
        ax.set_xlabel("x", fontsize=11, color=params["tick_color"])
        ax.set_ylabel("y", fontsize=11, color=params["tick_color"])
    else:
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)




def generate_tasks():
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED)

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    GT_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    records = []

    for idx in range(2001, 2000+SAMPLE_COUNT + 1):
        params = generate_scene_params()
        name = f"{idx:05d}"

        input_path = INPUT_DIR / f"{name}_input.png"
        gt_path = GT_DIR / f"{name}_gt.png"

        render_image(params, input_path, is_gt=False)
        render_image(params, gt_path, is_gt=True)

        records.append({
            "index": idx,
            "input_image": str(input_path),
            "gt_image": str(gt_path),
            "prompt": params["task_desc"],
        })

        if idx % 500 == 0:
            print(f"  [{idx}/{SAMPLE_COUNT}] done")

    META_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {SAMPLE_COUNT} tasks -> {OUTPUT_DIR}")

    
    from collections import Counter
    def _type_from_prompt(p):
        for k in TASK_TYPES:
            if k in p.lower():
                return k
        return "unknown"
    type_counts = Counter(_type_from_prompt(r["prompt"]) for r in records)
    print("Task distribution:")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")


if __name__ == "__main__":
    generate_tasks()
