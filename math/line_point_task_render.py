"""
point & line task rendering script
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


OUTPUT_DIR = Path("./line_point_pairs")
INPUT_DIR = OUTPUT_DIR / "input"
GT_DIR = OUTPUT_DIR / "gt"
META_DIR = OUTPUT_DIR / "meta"
META_FILE = META_DIR / "meta.json"

SAMPLE_COUNT = 2000
RANDOM_SEED = None

DPI = 150


LINE_LEN_RANGE = (5.0, 14.0)
POINT_DIST_RANGE = (3.0, 10.0)
PAD_RATIO = (0.15, 0.40)

BG_COLORS = [
    "#ffffff", "#f7f8fa", "#faf8f5", "#f0f4f8",
    "#f5f5f5", "#fefefe", "#f8f6f0", "#eef2f7",
    "#fffdf5", "#f3f0eb", "#e8edf3", "#f9fafb",
]

GRID_STYLES = ["-", "--", ":", "-."]

TASK_TYPES = ["parallel", "perpendicular"]



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




def choose_labels(n: int = 3) -> List[str]:
    return random.sample(string.ascii_uppercase, n)


def gen_line_and_point(cx: float, cy: float):

   
    angle = random.uniform(0, math.pi)

    half_len = random.uniform(*LINE_LEN_RANGE) / 2

    
    mx = cx + random.uniform(-3, 3)
    my = cy + random.uniform(-3, 3)

    ax_pt = (mx - half_len * math.cos(angle), my - half_len * math.sin(angle))
    bx_pt = (mx + half_len * math.cos(angle), my + half_len * math.sin(angle))

    
    nx = -math.sin(angle)
    ny = math.cos(angle)

    
    dist = random.uniform(*POINT_DIST_RANGE)
    side = random.choice([-1, 1])

   
    t = random.uniform(-0.3, 1.3)
    px = mx + (t - 0.5) * 2 * half_len * math.cos(angle) * random.uniform(0.2, 0.6)
    py = my + (t - 0.5) * 2 * half_len * math.sin(angle) * random.uniform(0.2, 0.6)
    px += side * dist * nx
    py += side * dist * ny

    return ax_pt, bx_pt, (px, py), angle


def foot_of_perpendicular(p: Tuple[float, float],
                          a: Tuple[float, float],
                          b: Tuple[float, float]) -> Tuple[float, float]:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    return (a[0] + t * dx, a[1] + t * dy)




def points_bbox(points: List[Tuple[float, float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), max(xs), min(ys), max(ys)


def bbox_to_axis_range(x_min: float, x_max: float, y_min: float, y_max: float):
    x_span = x_max - x_min
    y_span = y_max - y_min

    pad_ratio = random.uniform(*PAD_RATIO)
    x_pad = max(x_span * pad_ratio, 1.5)
    y_pad = max(y_span * pad_ratio, 1.5)

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




def clip_line_to_rect(px, py, dx, dy, x_lo, x_hi, y_lo, y_hi):
    """
    给定过点 (px,py) 方向 (dx,dy) 的直线,
    裁剪到矩形 [x_lo,x_hi]x[y_lo,y_hi] 内的线段端点。
    """
    ts = []
    if abs(dx) > 1e-12:
        ts.append((x_lo - px) / dx)
        ts.append((x_hi - px) / dx)
    if abs(dy) > 1e-12:
        ts.append((y_lo - py) / dy)
        ts.append((y_hi - py) / dy)
    if not ts:
        return None

    valid = []
    for t in ts:
        ix = px + t * dx
        iy = py + t * dy
        if x_lo - 0.01 <= ix <= x_hi + 0.01 and y_lo - 0.01 <= iy <= y_hi + 0.01:
            valid.append(t)

    if len(valid) < 2:
        return None

    t_min = min(valid)
    t_max = max(valid)
    return ((px + t_min * dx, py + t_min * dy),
            (px + t_max * dx, py + t_max * dy))



def generate_scene_params() -> dict:
    cx = random.uniform(8, 30)
    cy = random.uniform(8, 30)

    A, B, P, line_angle = gen_line_and_point(cx, cy)
    labels = choose_labels(3)  

    task_type = random.choice(TASK_TYPES)

    
    ldx = math.cos(line_angle)
    ldy = math.sin(line_angle)

    if task_type == "parallel":
        
        result_dx = ldx
        result_dy = ldy
        task_desc = (f"Draw a line through point {labels[2]} "
                     f"parallel to line {labels[0]}{labels[1]}.")

    else: 
       
        result_dx = -ldy
        result_dy = ldx
       
        foot = foot_of_perpendicular(P, A, B)
        task_desc = (f"Draw a line through point {labels[2]} "
                     f"perpendicular to line {labels[0]}{labels[1]}.")

    
    all_key_points = [A, B, P]
    if task_type == "perpendicular":
        all_key_points.append(foot)

    bx_min, bx_max, by_min, by_max = points_bbox(all_key_points)
    x_range, y_range = bbox_to_axis_range(bx_min, bx_max, by_min, by_max)

    show_axes = random.random() < 0.5
    show_grid = random.random() < 0.5


    extend_line = random.random() < 0.5

    return {
        "line_A": A,
        "line_B": B,
        "point_P": P,
        "labels": labels,
        "task_type": task_type,
        "task_desc": task_desc,
        "line_angle": line_angle,
        "result_dx": result_dx,
        "result_dy": result_dy,
        "foot": foot if task_type == "perpendicular" else None,
        "x_range": x_range,
        "y_range": y_range,
        "show_axes": show_axes,
        "show_grid": show_grid,
        "extend_line": extend_line,
        "bg_color": random.choice(BG_COLORS),
        "grid_style": random.choice(GRID_STYLES),
        "grid_color": rand_color(),
        "grid_alpha": random.uniform(0.15, 0.5),
        "spine_color": rand_dark_color(),
        "tick_color": rand_dark_color(),
        "line_color": rand_dark_color(),
        "line_linewidth": random.uniform(1.8, 3.5),
        "line_linestyle": random.choice(["-", "-"]),  
        "point_size": random.uniform(40, 80),
        "point_color": rand_dark_color(),
        "label_fontsize": random.uniform(12, 16),
        "label_color": rand_dark_color(),
        "aux_color": rand_bright_color(),
        "aux_linewidth": random.uniform(1.5, 3.5),
        "aux_linestyle": random.choice(["-", "--", "-."]),
        "mark_color": rand_dark_color(),
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
    """在垂足处画直角标记"""
    d1 = (p1[0] - vertex[0], p1[1] - vertex[1])
    d2 = (p2[0] - vertex[0], p2[1] - vertex[1])
    mag1 = math.hypot(*d1)
    mag2 = math.hypot(*d2)
    if mag1 < 1e-9 or mag2 < 1e-9:
        return
    u1 = (d1[0] / mag1 * size, d1[1] / mag1 * size)
    u2 = (d2[0] / mag2 * size, d2[1] / mag2 * size)
    xs = [vertex[0] + u1[0],
          vertex[0] + u1[0] + u2[0],
          vertex[0] + u2[0]]
    ys = [vertex[1] + u1[1],
          vertex[1] + u1[1] + u2[1],
          vertex[1] + u2[1]]
    ax.plot(xs, ys, color=color, linewidth=linewidth, zorder=8)


def render_image(params: dict, output_path: Path, is_gt: bool):
    figsize = adaptive_figsize(params["x_range"], params["y_range"])
    fig, ax = plt.subplots(figsize=figsize, dpi=DPI)
    ax.set_facecolor(params["bg_color"])

    A = params["line_A"]
    B = params["line_B"]
    P = params["point_P"]
    labels = params["labels"]
    x_lo, x_hi = params["x_range"]
    y_lo, y_hi = params["y_range"]

   
    if params["extend_line"]:
        
        ldx = math.cos(params["line_angle"])
        ldy = math.sin(params["line_angle"])
        clipped = clip_line_to_rect(A[0], A[1], ldx, ldy, x_lo, x_hi, y_lo, y_hi)
        if clipped:
            ax.plot([clipped[0][0], clipped[1][0]],
                    [clipped[0][1], clipped[1][1]],
                    color=params["line_color"],
                    linewidth=params["line_linewidth"],
                    zorder=3)
       
        ax.scatter(A[0], A[1], s=params["point_size"],
                   color=params["point_color"], zorder=6)
        ax.scatter(B[0], B[1], s=params["point_size"],
                   color=params["point_color"], zorder=6)
    else: 
        ax.plot([A[0], B[0]], [A[1], B[1]],
                color=params["line_color"],
                linewidth=params["line_linewidth"],
                zorder=3)
        ax.scatter(A[0], A[1], s=params["point_size"],
                   color=params["point_color"], zorder=6)
        ax.scatter(B[0], B[1], s=params["point_size"],
                   color=params["point_color"], zorder=6)

   
    ax.scatter(P[0], P[1], s=params["point_size"],
               color=params["point_color"], zorder=6)

    
    line_angle = params["line_angle"]
    
    nx = -math.sin(line_angle)
    ny = math.cos(line_angle)
    
    mid_line = ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2)
    side_p = (P[0] - mid_line[0]) * nx + (P[1] - mid_line[1]) * ny
   
    sign_away = -1 if side_p > 0 else 1
    label_offset = 0.7
    x_span = x_hi - x_lo

    for i, (px, py) in enumerate([A, B, P]):
        if i < 2:
            
            ldx = math.cos(line_angle)
            ldy = math.sin(line_angle)
            along = (-1 if i == 0 else 1)
            offset_x = sign_away * nx * label_offset + along * ldx * label_offset * 0.3
            offset_y = sign_away * ny * label_offset + along * ldy * label_offset * 0.3
        else:
           
            sign_p = 1 if side_p > 0 else -1
            offset_x = sign_p * nx * label_offset
            offset_y = sign_p * ny * label_offset

        ax.text(px + offset_x, py + offset_y, labels[i],
                fontsize=params["label_fontsize"],
                fontweight="bold",
                color=params["label_color"],
                ha="center", va="center",
                zorder=7)

    
    if is_gt:
        rdx = params["result_dx"]
        rdy = params["result_dy"]

        
        clipped = clip_line_to_rect(P[0], P[1], rdx, rdy, x_lo, x_hi, y_lo, y_hi)
        if clipped:
            ax.plot([clipped[0][0], clipped[1][0]],
                    [clipped[0][1], clipped[1][1]],
                    color=params["aux_color"],
                    linewidth=params["aux_linewidth"],
                    linestyle=params["aux_linestyle"],
                    zorder=5)

        if params["task_type"] == "perpendicular" and params["foot"] is not None:
            foot = params["foot"]
            
            ax.scatter(foot[0], foot[1], s=50,
                       color=params["aux_color"], marker="o", zorder=6)
            
            x_span = x_hi - x_lo
            mark_sz = x_span * 0.025
           
            draw_right_angle_mark(
                ax, foot,
                P,  
                B,  
                mark_sz, params["aux_color"], linewidth=1.5)



    
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

    for idx in range(1, SAMPLE_COUNT + 1):
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

        if idx % 5 == 0:
            print(f"  [{idx}/{SAMPLE_COUNT}] done")

    META_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {SAMPLE_COUNT} tasks -> {OUTPUT_DIR}")

    from collections import Counter
    type_counts = Counter(
        "parallel" if "parallel" in r["prompt"].lower() else "perpendicular"
        for r in records
    )
    print("Task distribution:")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")


if __name__ == "__main__":
    generate_tasks()
