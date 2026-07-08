import json
import os
import random
import re
import glob as glob_mod

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import matplotlib.font_manager as fm
import numpy as np
from shapely.geometry import box
from shapely.errors import GEOSException


AVAILABLE_FONTS = [
    "DejaVu Sans",
    "Liberation Sans",
    "FreeSans",
    "Arial",
    "Helvetica",
    "Times New Roman",
    "Georgia",
    "Courier New",
    "Palatino Linotype",
    "Segoe UI",
]

OCEAN_COLORS = [
    "#A8D5E5",
    "#87CEEB",
    "#B0E0E6",
    "#ADD8E6",
    "#E6F3FF",
    "#D4E6F1",
    "#F5F5DC",
    "#FAF0E6",
    "#F0F8FF",
    "#E8F4F8",
    "#1a1a2e",
    "#16213e",
    "#0f3460",
    "#1b262c",
]

LAND_COLORMAPS = [
    "Set3",
    "Pastel1",
    "Pastel2",
    "tab20",
    "tab20b",
    "tab20c",
    "Accent",
    "Paired",
]

BORDER_STYLES = [
    {"color": "black", "linewidth": 0.8},
    {"color": "#333333", "linewidth": 1.0},
    {"color": "#555555", "linewidth": 0.6},
    {"color": "#8B4513", "linewidth": 1.2},
    {"color": "#2F4F4F", "linewidth": 0.8},
]

LABEL_STYLES = [
    {
        "fontsize": 9,
        "fontweight": "bold",
        "color": "black",
        "stroke_color": "white",
        "stroke_width": 3,
    },
    {
        "fontsize": 10,
        "fontweight": "bold",
        "color": "#1a1a1a",
        "stroke_color": "white",
        "stroke_width": 2.5,
    },
    {
        "fontsize": 8,
        "fontweight": "normal",
        "color": "#333333",
        "stroke_color": "white",
        "stroke_width": 2,
    },
    {
        "fontsize": 9,
        "fontweight": "bold",
        "color": "#2F4F4F",
        "stroke_color": "#F5F5F5",
        "stroke_width": 3,
    },
    {
        "fontsize": 10,
        "fontweight": "bold",
        "color": "#8B0000",
        "stroke_color": "white",
        "stroke_width": 3,
    },
    {
        "fontsize": 9,
        "fontweight": "bold",
        "color": "#00008B",
        "stroke_color": "white",
        "stroke_width": 2.5,
    },
]

STYLE_THEMES = [
    "classic",
    "vintage",
    "modern",
    "parchment",
    "midnight",
    "pastel",
]


def get_system_fonts():
    try:
        fonts = set([f.name for f in fm.fontManager.ttflist])
        available = [f for f in AVAILABLE_FONTS if f in fonts]
        if not available:
            available = ["DejaVu Sans"]
        return available
    except:
        return ["DejaVu Sans"]


def generate_random_style():
    theme = random.choice(STYLE_THEMES)

    if theme == "classic":
        ocean_color = random.choice(["#A8D5E5", "#87CEEB", "#B0E0E6", "#ADD8E6"])
        cmap_name = random.choice(["Set3", "Pastel1"])
        border = {"color": "black", "linewidth": 0.8}
        label_style = random.choice(LABEL_STYLES[:2])
    elif theme == "vintage":
        ocean_color = random.choice(["#F5F5DC", "#FAF0E6", "#D4C4A8", "#E8DCC4"])
        cmap_name = random.choice(["YlOrBr", "YlOrRd", "OrRd"])
        border = {"color": "#8B4513", "linewidth": 1.2}
        label_style = {
            "fontsize": 10,
            "fontweight": "bold",
            "color": "#4A3728",
            "stroke_color": "#F5E6D3",
            "stroke_width": 2.5,
        }
    elif theme == "modern":
        ocean_color = random.choice(["#E6F3FF", "#F0F8FF", "#E8F4F8", "#F5F5F5"])
        cmap_name = random.choice(["tab20", "tab20b", "tab20c"])
        border = {"color": "#333333", "linewidth": 0.6}
        label_style = {
            "fontsize": 9,
            "fontweight": "normal",
            "color": "#333333",
            "stroke_color": "white",
            "stroke_width": 2,
        }
    elif theme == "parchment":
        ocean_color = random.choice(["#F5E6C8", "#E8D4A8", "#DCC89C", "#F0E4C8"])
        cmap_name = random.choice(["YlOrBr", "OrRd", "PuOr"])
        border = {"color": "#6B4423", "linewidth": 1.0}
        label_style = {
            "fontsize": 10,
            "fontweight": "bold",
            "color": "#3D2914",
            "stroke_color": "#F5E6C8",
            "stroke_width": 2,
        }
    elif theme == "midnight":
        ocean_color = random.choice(["#1a1a2e", "#16213e", "#0f3460", "#1b262c"])
        cmap_name = random.choice(["viridis", "plasma", "coolwarm"])
        border = {"color": "#4a4a6a", "linewidth": 0.8}
        label_style = {
            "fontsize": 9,
            "fontweight": "bold",
            "color": "#E8E8E8",
            "stroke_color": "#1a1a2e",
            "stroke_width": 2.5,
        }
    else:  # pastel
        ocean_color = random.choice(["#FFE4E1", "#E6E6FA", "#F0FFF0", "#FFF0F5", "#F5F5DC"])
        cmap_name = random.choice(["Pastel1", "Pastel2", "Set3"])
        border = {"color": "#888888", "linewidth": 0.6}
        label_style = {
            "fontsize": 9,
            "fontweight": "bold",
            "color": "#555555",
            "stroke_color": "white",
            "stroke_width": 2,
        }

    available_fonts = get_system_fonts()
    font_family = random.choice(available_fonts)

    return {
        "theme": theme,
        "ocean_color": ocean_color,
        "cmap_name": cmap_name,
        "border": border,
        "label_style": label_style,
        "font_family": font_family,
    }


def _estimate_text_bbox(x, y, text, fontsize, ax, fig):
    disp_to_data = ax.transData.inverted()
    data_to_disp = ax.transData

    cx_disp, cy_disp = data_to_disp.transform((x, y))

    char_w_px = fontsize * 0.6
    char_h_px = fontsize * 1.2
    tw = len(text) * char_w_px
    th = char_h_px

    x0, y0 = disp_to_data.transform((cx_disp - tw / 2, cy_disp - th / 2))
    x1, y1 = disp_to_data.transform((cx_disp + tw / 2, cy_disp + th / 2))
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def _bboxes_overlap(a, b, padding=0.2):
    aw = (a[2] - a[0]) * padding
    ah = (a[3] - a[1]) * padding
    bw = (b[2] - b[0]) * padding
    bh = (b[3] - b[1]) * padding
    ax0, ay0, ax1, ay1 = a[0] - aw, a[1] - ah, a[2] + aw, a[3] + ah
    bx0, by0, bx1, by1 = b[0] - bw, b[1] - bh, b[2] + bw, b[3] + bh
    return ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0


def _repel_labels(labels, ax, fig, iterations=100, step_factor=0.3):
    for _ in range(iterations):
        moved = False
        bboxes = [
            _estimate_text_bbox(lb["x"], lb["y"], lb["name"], lb["fontsize"], ax, fig)
            for lb in labels
        ]
        for i in range(len(labels)):
            dx, dy = 0.0, 0.0
            bi = bboxes[i]
            wi = bi[2] - bi[0]
            hi = bi[3] - bi[1]
            for j in range(len(labels)):
                if i == j:
                    continue
                bj = bboxes[j]
                if not _bboxes_overlap(bi, bj):
                    continue
                cx_i = (bi[0] + bi[2]) / 2
                cy_i = (bi[1] + bi[3]) / 2
                cx_j = (bj[0] + bj[2]) / 2
                cy_j = (bj[1] + bj[3]) / 2
                diff_x = cx_i - cx_j
                diff_y = cy_i - cy_j
                if abs(diff_x) < 1e-12 and abs(diff_y) < 1e-12:
                    diff_x = random.uniform(-1, 1) * wi
                    diff_y = random.uniform(-1, 1) * hi
                overlap_x = (wi + bj[2] - bj[0]) / 2 - abs(diff_x)
                overlap_y = (hi + bj[3] - bj[1]) / 2 - abs(diff_y)
                if overlap_x > 0:
                    dx += (1 if diff_x >= 0 else -1) * overlap_x * step_factor
                if overlap_y > 0:
                    dy += (1 if diff_y >= 0 else -1) * overlap_y * step_factor
            if abs(dx) > 1e-12 or abs(dy) > 1e-12:
                labels[i]["x"] += dx
                labels[i]["y"] += dy
                moved = True
        if not moved:
            break


def _process_labels(cropped, label_col, view_bounds, fig, ax, style):
    view_area = (view_bounds[2] - view_bounds[0]) * (view_bounds[3] - view_bounds[1])
    area_threshold = view_area * 0.002

    label_style = style["label_style"]

    labels = []
    for _, row in cropped.iterrows():
        name = row[label_col]
        if name is None or str(name).strip() == "":
            continue
        area = row.geometry.area
        if area < area_threshold:
            continue
        pt = row.geometry.representative_point()
        labels.append({
            "name": str(name),
            "orig_x": pt.x, "orig_y": pt.y,
            "x": pt.x, "y": pt.y,
            "fontsize": label_style["fontsize"],
            "area": area,
        })

    if not labels:
        return [], [], []

    labels.sort(key=lambda lb: -lb["area"])
    _repel_labels(labels, ax, fig, iterations=300, step_factor=0.4)

    final_bboxes = [
        _estimate_text_bbox(lb["x"], lb["y"], lb["name"], lb["fontsize"], ax, fig)
        for lb in labels
    ]

    keep = [True] * len(labels)
    for i in range(len(labels) - 1, -1, -1):
        if not keep[i]:
            continue
        for j in range(i):
            if not keep[j]:
                continue
            if _bboxes_overlap(final_bboxes[i], final_bboxes[j], padding=0.1):
                keep[i] = False
                break

    visible = [i for i in range(len(labels)) if keep[i]]
    return labels, visible, final_bboxes


def _try_crop_with_scale(gdf, label_col, crop_scale, style):
    try:
        minx, miny, maxx, maxy = gdf.total_bounds
        full_w = maxx - minx
        full_h = maxy - miny

        crop_w = full_w * crop_scale
        crop_h = full_h * crop_scale

        if crop_w <= 0 or crop_h <= 0:
            return None

        x1 = random.uniform(minx, maxx - crop_w)
        y1 = random.uniform(miny, maxy - crop_h)
        crop_geom = box(x1, y1, x1 + crop_w, y1 + crop_h)

        candidate = gdf[gdf.intersects(crop_geom)].copy()
        if candidate.empty:
            return None

        candidate = gpd.clip(candidate, crop_geom)
        candidate = candidate[~candidate.geometry.is_empty & candidate.geometry.notnull()]

        if candidate.empty:
            return None

        fb = candidate.total_bounds
        if (fb[2] - fb[0]) < crop_w * 0.1 or (fb[3] - fb[1]) < crop_h * 0.1:
            return None

        cropped = candidate
        total_features = len(cropped)

        fw, fh = fb[2] - fb[0], fb[3] - fb[1]
        pad_x, pad_y = fw * 0.05, fh * 0.05
        view_bounds = (fb[0] - pad_x, fb[1] - pad_y, fb[2] + pad_x, fb[3] + pad_y)

        fig, ax = plt.subplots(figsize=(8, 8))
        ax.set_facecolor(style["ocean_color"])

        temp_cmap = plt.get_cmap("Set3").resampled(max(total_features, 12))
        temp_colors = [temp_cmap(i % temp_cmap.N) for i in range(total_features)]
        cropped.plot(ax=ax, edgecolor=style["border"]["color"],
                     linewidth=style["border"]["linewidth"], color=temp_colors)
        ax.set_xlim(view_bounds[0], view_bounds[2])
        ax.set_ylim(view_bounds[1], view_bounds[3])
        fig.canvas.draw()

        labels, visible, bboxes = _process_labels(cropped, label_col, view_bounds, fig, ax, style)

        plt.close(fig)

        if not visible:
            return None

        cmap = plt.get_cmap(style["cmap_name"]).resampled(max(total_features, 12))
        colors = [cmap(i % cmap.N) for i in range(total_features)]
        random.shuffle(colors)

        return cropped, view_bounds, colors, labels, visible, bboxes, total_features

    except GEOSException:
        return None


def _find_scale_for_visible_count(gdf, label_col, min_visible, max_visible,
                                   max_tries=100, min_scale=0.01, max_scale=0.99, style=None):
    if style is None:
        style = generate_random_style()

    target_visible = random.randint(min_visible, max_visible)

    low, high = min_scale, max_scale
    best_result = None
    best_score = float('inf')  # 综合评分，越小越好

    for attempt in range(max_tries):
        mid = (low + high) / 2

        for _ in range(3):
            result = _try_crop_with_scale(gdf, label_col, mid, style)
            if result is None:
                continue

            cropped, view_bounds, colors, labels, visible, bboxes, total_features = result
            visible_count = len(visible)

            visible_diff = abs(visible_count - target_visible)

            feature_visible_gap = total_features - visible_count

            if feature_visible_gap > 3:
                gap_penalty = feature_visible_gap * 2
            else:
                gap_penalty = feature_visible_gap * 0.5

            score = visible_diff * 10 + gap_penalty

            if min_visible <= visible_count <= max_visible:
                if feature_visible_gap <= 2:
                    if score < best_score:
                        best_score = score
                        best_result = (mid, cropped, view_bounds, colors, labels, visible, bboxes)
                        if visible_diff <= 1 and feature_visible_gap <= 1:
                            return best_result

            if score < best_score:
                best_score = score
                best_result = (mid, cropped, view_bounds, colors, labels, visible, bboxes)

        if best_result:
            _, _, _, _, _, visible, _ = best_result
            visible_count = len(visible)
            if visible_count < min_visible:
                low = mid
            elif visible_count > max_visible:
                high = mid
            else:
                if visible_count < target_visible:
                    low = mid
                else:
                    high = mid
        else:
            low = mid

        if high - low < 0.001:
            break

    if best_result:
        mid, cropped, view_bounds, colors, labels, visible, bboxes = best_result
        visible_count = len(visible)

        if visible_count < min_visible:
            for _ in range(5):
                result = _try_crop_with_scale(gdf, label_col, max_scale, style)
                if result is None:
                    continue
                cropped, view_bounds, colors, labels, visible, bboxes, total_features = result
                visible_count = len(visible)
                if visible_count >= min_visible and (total_features - visible_count) <= 2:
                    return (max_scale, cropped, view_bounds, colors, labels, visible, bboxes)

            if best_result:
                print(f"    Warning: visible={visible_count} < min_visible={min_visible}, returning best result")
                return best_result

    return best_result


def _prepare_crop_fixed_visible(gdf, label_col, min_visible, max_visible, max_tries=100, style=None):
    if style is None:
        style = generate_random_style()

    result = _find_scale_for_visible_count(gdf, label_col, min_visible, max_visible, max_tries, style=style)

    if result is None:
        raise ValueError(f"Cannot find region with visible labels in [{min_visible}, {max_visible}] range")

    crop_scale, cropped, view_bounds, colors, labels, visible, bboxes = result
    visible_count = len(visible)
    total_features = len(cropped)

    return cropped, view_bounds, colors, labels, visible, bboxes, crop_scale, visible_count, total_features, style


def _draw_map(cropped, view_bounds, colors, labels, draw_indices, dpi, output_png, style):
    label_style = style["label_style"]

    text_style = dict(
        fontsize=label_style["fontsize"],
        fontweight=label_style["fontweight"],
        ha="center",
        va="center",
        color=label_style["color"],
        fontfamily=style["font_family"],
        path_effects=[pe.withStroke(
            linewidth=label_style["stroke_width"],
            foreground=label_style["stroke_color"]
        )],
    )

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_facecolor(style["ocean_color"])

    cropped.plot(
        ax=ax,
        edgecolor=style["border"]["color"],
        linewidth=style["border"]["linewidth"],
        color=colors
    )
    ax.set_xlim(view_bounds[0], view_bounds[2])
    ax.set_ylim(view_bounds[1], view_bounds[3])

    draw_set = set(draw_indices)
    for i in draw_set:
        lb = labels[i]
        displaced = (abs(lb["x"] - lb["orig_x"]) > 1e-9 or
                     abs(lb["y"] - lb["orig_y"]) > 1e-9)
        if displaced:
            ax.annotate(
                lb["name"],
                xy=(lb["orig_x"], lb["orig_y"]),
                xytext=(lb["x"], lb["y"]),
                arrowprops=dict(
                    arrowstyle="-",
                    color="gray",
                    lw=0.5,
                    shrinkA=0,
                    shrinkB=3
                ),
                **text_style,
            )
        else:
            ax.text(lb["x"], lb["y"], lb["name"], **text_style)

    ax.set_axis_off()
    plt.savefig(output_png, dpi=dpi, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def _pick_mask_indices(labels, visible, bboxes, num_mask):
    if len(visible) <= num_mask:
        return visible

    neighbor_radius = 2.0

    density = {}
    for i in visible:
        bi = bboxes[i]
        cx_i = (bi[0] + bi[2]) / 2
        cy_i = (bi[1] + bi[3]) / 2
        wi = bi[2] - bi[0]
        hi = bi[3] - bi[1]
        count = 0
        for j in visible:
            if j == i:
                continue
            bj = bboxes[j]
            cx_j = (bj[0] + bj[2]) / 2
            cy_j = (bj[1] + bj[3]) / 2
            dist_x = abs(cx_i - cx_j) / max(wi, 1e-12)
            dist_y = abs(cy_i - cy_j) / max(hi, 1e-12)
            if dist_x < neighbor_radius and dist_y < neighbor_radius:
                count += 1
        density[i] = count

    sorted_by_sparse = sorted(visible, key=lambda i: density[i])

    return sorted_by_sparse[:num_mask]


def batch_render_fixed_visible(
    input_dir,
    output_dir,
    label_col="NAME",
    num_crops=1,
    num_mask=1,
    min_visible=3,
    max_visible=6,
    max_tries=100,
    dpi=300,
):
    if num_mask >= min_visible:
        print(f"Warning: num_mask({num_mask}) >= min_visible({min_visible}), adjusting num_mask to {min_visible - 1}")
        num_mask = max(1, min_visible - 1)

    input_img_dir = os.path.join(output_dir, "input")
    gt_img_dir = os.path.join(output_dir, "gt")
    os.makedirs(input_img_dir, exist_ok=True)
    os.makedirs(gt_img_dir, exist_ok=True)

    files = sorted(glob_mod.glob(os.path.join(input_dir, "**", "*.geojson"), recursive=True))
    if not files:
        print(f"No .geojson files found in {input_dir}")
        return

    print(f"Found {len(files)} geojson files, rendering {num_crops} pairs (GT + input) per file")
    print(f"Visible labels range: {min_visible} - {max_visible}, num_mask: {num_mask}")

    meta_path = os.path.join(output_dir, "meta.json")

    all_meta = []
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                all_meta = json.load(f)
            print(f"Loaded {len(all_meta)} existing records")
        except:
            all_meta = []

    completed_stems = set()
    completed_indices = {}

    for meta in all_meta:
        stem = meta.get("year", "")
        gt_path_check = meta.get("gt", "")
        input_path_check = meta.get("input", "")

        match = re.search(r'_(\d+)_gt\.png$', gt_path_check)
        if match:
            idx = int(match.group(1))

            if os.path.exists(gt_path_check) and os.path.exists(input_path_check):
                if stem not in completed_indices:
                    completed_indices[stem] = set()
                completed_indices[stem].add(idx)

                if idx == num_crops - 1:
                    completed_stems.add(stem)

    if completed_stems:
        print(f"Completed {len(completed_stems)} geojson files, will skip")

    def append_meta(meta_item):
        all_meta.append(meta_item)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(all_meta, f, ensure_ascii=False, indent=2)

    for fi, fpath in enumerate(files, 1):
        stem = os.path.splitext(os.path.basename(fpath))[0]

        if stem in completed_stems:
            print(f"\n[{fi}/{len(files)}] {fpath}")
            print(f"  Skip: already completed ({stem}_{num_crops - 1}_gt.png exists)")
            continue

        print(f"\n[{fi}/{len(files)}] {fpath}")

        try:
            gdf = gpd.read_file(fpath)
            if gdf.empty:
                print("  Skip: file is empty")
                continue
            if label_col not in gdf.columns:
                print(f"  Skip: field {label_col} not found")
                continue
        except GEOSException as e:
            print(f"  Skip: invalid geometry - {e}")
            continue
        except Exception as e:
            print(f"  Skip: failed to read - {e}")
            continue

        for idx in range(num_crops):
            if stem in completed_indices and idx in completed_indices[stem]:
                print(f"  Image {idx}: already exists, skip")
                continue

            style = generate_random_style()

            try:
                cropped, view_bounds, colors, labels, visible, bboxes, actual_scale, visible_count, total_features, style = \
                    _prepare_crop_fixed_visible(gdf, label_col, min_visible, max_visible, max_tries, style=style)
                print(f"  Image {idx}: visible={visible_count}, total={total_features}, scale={actual_scale:.4f}, theme={style['theme']}")
            except GEOSException as e:
                print(f"  Skip image {idx}: invalid geometry - {e}")
                continue
            except ValueError as e:
                print(f"  Skip image {idx}: {e}")
                continue

            mask_indices = _pick_mask_indices(labels, visible, bboxes, num_mask)

            suffix = f"_{idx}" if num_crops > 1 else ""
            gt_path = os.path.join(gt_img_dir, f"{stem}{suffix}_gt.png")
            input_path = os.path.join(input_img_dir, f"{stem}{suffix}_input.png")

            _draw_map(cropped, view_bounds, colors, labels, visible, dpi, gt_path, style)
            print(f"    GT:    {gt_path}")

            input_visible = [i for i in visible if i not in mask_indices]
            _draw_map(cropped, view_bounds, colors, labels, input_visible, dpi, input_path, style)
            print(f"    input: {input_path}")

            masked_names = [labels[i]["name"] for i in mask_indices]

            append_meta({
                "gt": gt_path,
                "input": input_path,
                "masked_labels": masked_names,
                "source": fpath,
                "year": stem,
                "visible_count": visible_count,
                "total_features": total_features,
                "scale": actual_scale,
                "num_mask": len(mask_indices)
            })

    print(f"\nBatch rendering complete, total {len(all_meta)} pairs, metadata: {meta_path}")


# ======================== Configuration ========================
INPUT_DIR    = "/mnt/nas-new/home/yangxue/lmx/image/auto/history/map/historical-basemaps/geojson"
OUTPUT_DIR   = "geojson_output_v2"
LABEL_COL    = "NAME"
NUM_CROPS    = 50                  # Number of random render pairs per geojson
NUM_MASK     = 2                   # Number of labels to mask per pair
MIN_VISIBLE  = 5                   # Minimum visible labels
MAX_VISIBLE  = 8                   # Maximum visible labels
MAX_TRIES    = 100                 # Max attempts to find suitable scale
DPI          = 300                 # Output resolution
# ===============================================================

if __name__ == "__main__":
    batch_render_fixed_visible(
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        label_col=LABEL_COL,
        num_crops=NUM_CROPS,
        num_mask=NUM_MASK,
        min_visible=MIN_VISIBLE,
        max_visible=MAX_VISIBLE,
        max_tries=MAX_TRIES,
        dpi=DPI,
    )
