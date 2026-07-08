#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont, ImageOps


CATEGORY_ORDER = ["carb", "protein", "fruit_veg", "fat", "mixed"]
CATEGORY_LABELS = {
    "carb": "Carbohydrates",
    "protein": "Proteins",
    "fruit_veg": "Fruits & Vegetables",
    "fat": "Fats",
    "mixed": "Mixed",
}
CATEGORY_COLORS = {
    "carb": "#E7A93C",
    "protein": "#C95D47",
    "fruit_veg": "#5F9E5B",
    "fat": "#6B8FB5",
    "mixed": "#A08FAE",
}

GI_KEYWORDS = {
    "white bread": 75,
    "bagel": 72,
    "rice cake": 82,
    "corn flakes": 81,
    "instant oatmeal": 79,
    "potato": 78,
    "jasmine rice": 80,
    "white rice": 73,
    "banana": 62,
    "brown rice": 55,
    "sweet potato": 61,
    "whole wheat bread": 53,
    "oatmeal": 55,
    "rolled oats": 55,
    "yogurt": 35,
    "milk": 31,
    "apple": 36,
    "orange": 43,
    "lentil": 32,
    "lentils": 32,
    "chickpea": 28,
    "beans": 35,
    "pasta": 49,
    "spaghetti": 49,
}

PROTEIN_SOURCE_KEYWORDS = {
    "whey": "whey",
    "casein": "casein",
    "chicken": "meat",
    "beef": "meat",
    "pork": "meat",
    "turkey": "meat",
    "salmon": "meat",
    "tuna": "meat",
    "shrimp": "meat",
    "meat": "meat",
    "egg": "animal",
    "milk": "dairy",
    "yogurt": "dairy",
    "cheese": "dairy",
    "tofu": "plant",
    "soy": "plant",
    "bean": "plant",
    "lentil": "plant",
}

PRODUCE_KEYWORDS = {
    "apple",
    "banana",
    "orange",
    "broccoli",
    "spinach",
    "lettuce",
    "tomato",
    "carrot",
    "cucumber",
    "berries",
    "berry",
    "grape",
    "avocado",
    "mushroom",
    "pepper",
    "onion",
    "kale",
}


@dataclass
class FoodRecord:
    source_id: str
    food_name: str
    display_name: str = ""
    display_name_zh: str = ""
    fdc_id: str = ""
    data_type: str = ""
    source_dataset: str = ""
    food_category: str = ""
    energy_kcal: float = 0.0
    protein_g: float = 0.0
    carb_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float = 0.0
    sugar_g: float = 0.0
    primary_macro_category: str = "mixed"
    gi_value: float | None = None
    gi_level: str = "unknown"
    gi_source: str = ""
    protein_source: str = "unknown"
    image_url: str = ""
    image_page_url: str = ""
    image_title: str = ""
    image_license: str = ""
    image_attribution: str = ""
    image_source: str = ""
    local_image_path: str = ""
    cutout_image_path: str = ""
    cutout_source: str = ""
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def is_high_gi(self) -> bool:
        return self.gi_level == "high"

    @property
    def is_high_protein(self) -> bool:
        if self.protein_g >= 20:
            return True
        total_macro_cal = max(self.protein_g * 4 + self.carb_g * 4 + self.fat_g * 9, 1e-6)
        return (self.protein_g * 4) / total_macro_cal >= 0.35

    @property
    def has_local_image(self) -> bool:
        return bool(self.local_image_path and Path(self.local_image_path).exists())

    @property
    def has_cutout_image(self) -> bool:
        return bool(self.cutout_image_path and Path(self.cutout_image_path).exists())

    @property
    def preferred_image_path(self) -> str:
        if self.has_cutout_image:
            return self.cutout_image_path
        return self.local_image_path

    @property
    def title_text(self) -> str:
        if self.display_name_zh:
            return self.display_name_zh
        if self.display_name:
            return self.display_name
        parts = [part.capitalize() for part in self.food_name.replace("_", " ").split()]
        return " ".join(parts) if parts else self.food_name


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def gi_level_from_value(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 70:
        return "high"
    if value >= 56:
        return "medium"
    return "low"


def infer_gi_value(food_name: str) -> tuple[float | None, str]:
    normalized = normalize_text(food_name)
    for key, value in GI_KEYWORDS.items():
        if key in normalized:
            return float(value), "heuristic_keyword"
    return None, ""


def infer_protein_source(food_name: str, food_category: str = "") -> str:
    haystack = f"{food_name} {food_category}"
    normalized = normalize_text(haystack)
    for key, value in PROTEIN_SOURCE_KEYWORDS.items():
        if key in normalized:
            return value
    return "unknown"


def infer_primary_macro_category(food_name: str, food_category: str, protein_g: float, carb_g: float, fat_g: float, fiber_g: float) -> str:
    normalized = normalize_text(f"{food_name} {food_category}")
    if any(keyword in normalized for keyword in PRODUCE_KEYWORDS):
        return "fruit_veg"
    if "vegetable" in normalized or "fruit" in normalized:
        return "fruit_veg"
    macro_calories = {
        "protein": protein_g * 4,
        "carb": carb_g * 4,
        "fat": fat_g * 9,
    }
    category = max(macro_calories, key=macro_calories.get)
    if category == "protein" and protein_g >= 10:
        return "protein"
    if category == "carb" and carb_g >= 10:
        return "carb"
    if category == "fat" and fat_g >= 8:
        return "fat"
    if fiber_g >= 2 and carb_g >= 5:
        return "fruit_veg"
    return "mixed"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text[0] == "[":
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError(f"Expected a JSON array in {path}")
        return [item for item in payload if isinstance(item, dict)]

    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records



def build_stable_source_id(raw: dict[str, Any], fallback_index: int) -> str:
    existing = str(raw.get("source_id", "")).strip()
    if existing:
        return existing
    food_name = normalize_text(str(raw.get("food_name", "")))
    display_name = normalize_text(str(raw.get("display_name", "")))
    display_name_zh = str(raw.get("display_name_zh", "")).strip()
    fdc_id = str(raw.get("fdc_id", "")).strip()
    dataset = normalize_text(str(raw.get("source_dataset", "")))
    data_type = normalize_text(str(raw.get("data_type", "")))
    name_part = food_name or display_name or display_name_zh or "food"
    suffix = fdc_id or dataset or data_type or str(fallback_index)
    return f"{name_part}__{suffix}"

def load_food_records(path: Path) -> list[FoodRecord]:
    records: list[FoodRecord] = []
    for idx, raw in enumerate(load_jsonl(path), start=1):
        records.append(
            FoodRecord(
                source_id=build_stable_source_id(raw, idx),
                food_name=str(raw.get("food_name", "")),
                display_name=str(raw.get("display_name", "")),
                display_name_zh=str(raw.get("display_name_zh", "")),
                fdc_id=str(raw.get("fdc_id", "")),
                data_type=str(raw.get("data_type", "")),
                source_dataset=str(raw.get("source_dataset", "")),
                food_category=str(raw.get("food_category", "")),
                energy_kcal=safe_float(raw.get("energy_kcal")),
                protein_g=safe_float(raw.get("protein_g")),
                carb_g=safe_float(raw.get("carb_g")),
                fat_g=safe_float(raw.get("fat_g")),
                fiber_g=safe_float(raw.get("fiber_g")),
                sugar_g=safe_float(raw.get("sugar_g")),
                primary_macro_category=str(raw.get("primary_macro_category", "mixed")),
                gi_value=raw.get("gi_value"),
                gi_level=str(raw.get("gi_level", "unknown")),
                gi_source=str(raw.get("gi_source", "")),
                protein_source=str(raw.get("protein_source", "unknown")),
                image_url=str(raw.get("image_url", "")),
                image_page_url=str(raw.get("image_page_url", "")),
                image_title=str(raw.get("image_title", "")),
                image_license=str(raw.get("image_license", "")),
                image_attribution=str(raw.get("image_attribution", "")),
                image_source=str(raw.get("image_source", "")),
                local_image_path=str(raw.get("local_image_path", "")),
                cutout_image_path=str(raw.get("cutout_image_path", "")),
                cutout_source=str(raw.get("cutout_source", "")),
                tags=[str(x) for x in raw.get("tags", [])],
                meta=raw.get("meta", {}),
            )
        )
    return records


def choose_distinct(records: list[FoodRecord], count: int, rng: random.Random) -> list[FoodRecord]:
    seen: set[str] = set()
    shuffled = records[:]
    rng.shuffle(shuffled)
    picked: list[FoodRecord] = []
    for record in shuffled:
        key = normalize_text(record.food_name)
        if key in seen:
            continue
        picked.append(record)
        seen.add(key)
        if len(picked) >= count:
            break
    return picked


def category_color(category: str) -> str:
    return CATEGORY_COLORS.get(category, CATEGORY_COLORS["mixed"])


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, CATEGORY_LABELS["mixed"])


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in ["DejaVuSans.ttf", "arial.ttf", "Arial.ttf"]:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def hex_color(value: str) -> tuple[int, int, int]:
    return ImageColor.getrgb(value)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    fill: str = "#1C1F24",
    line_gap: int = 4,
    align: str = "left",
) -> tuple[int, int]:
    lines = wrap_text(draw, text, font, max_width)
    x, y = xy
    max_x = x
    current_y = y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        line_x = x
        if align == "center":
            line_x = x - width // 2
        elif align == "right":
            line_x = x - width
        draw.text((line_x, current_y), line, font=font, fill=fill)
        current_y += height + line_gap
        max_x = max(max_x, line_x + width)
    return max_x, current_y


def fit_cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image.convert("RGBA"), size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def load_image_for_box(path: str, size: tuple[int, int]) -> Image.Image | None:
    if not path:
        return None
    image_path = Path(path)
    if not image_path.exists():
        return None
    try:
        return fit_cover(Image.open(image_path), size)
    except Exception:
        return None


def _expand_bbox(bbox: tuple[int, int, int, int], image_size: tuple[int, int], pad: int = 6) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    width, height = image_size
    return (
        max(0, x0 - pad),
        max(0, y0 - pad),
        min(width, x1 + pad),
        min(height, y1 + pad),
    )


def _square_bbox(bbox: tuple[int, int, int, int], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    width, height = image_size
    box_w = x1 - x0
    box_h = y1 - y0
    side = max(box_w, box_h)
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    left = int(round(cx - side / 2.0))
    top = int(round(cy - side / 2.0))
    right = left + side
    bottom = top + side

    if left < 0:
        right -= left
        left = 0
    if top < 0:
        bottom -= top
        top = 0
    if right > width:
        left -= right - width
        right = width
    if bottom > height:
        top -= bottom - height
        bottom = height

    left = max(0, left)
    top = max(0, top)
    right = min(width, right)
    bottom = min(height, bottom)
    return (left, top, right, bottom)


def crop_to_foreground(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A") if "A" in rgba.getbands() else None
    if alpha is not None:
        alpha_bbox = alpha.getbbox()
        if alpha_bbox is not None and alpha_bbox != (0, 0, rgba.width, rgba.height):
            return rgba.crop(_square_bbox(_expand_bbox(alpha_bbox, rgba.size), rgba.size))

    rgb = rgba.convert("RGB")
    corners = [
        rgb.getpixel((0, 0)),
        rgb.getpixel((rgb.width - 1, 0)),
        rgb.getpixel((0, rgb.height - 1)),
        rgb.getpixel((rgb.width - 1, rgb.height - 1)),
    ]
    bg_color = max(set(corners), key=corners.count)
    background = Image.new("RGB", rgb.size, bg_color)
    diff = ImageChops.difference(rgb, background)
    r, g, b = diff.split()
    diff_mask = ImageChops.lighter(ImageChops.lighter(r, g), b)
    diff_mask = diff_mask.point(lambda p: 255 if p > 18 else 0)
    bbox = diff_mask.getbbox()
    if bbox is None:
        return rgba
    crop_bbox = _square_bbox(_expand_bbox(bbox, rgba.size), rgba.size)
    cropped = rgba.crop(crop_bbox)
    if cropped.width < max(24, rgba.width // 8) or cropped.height < max(24, rgba.height // 8):
        return rgba
    return cropped


def contain_center(image: Image.Image, size: tuple[int, int], fill_ratio: float = 0.88) -> Image.Image:
    target_w = max(1, int(size[0] * fill_ratio))
    target_h = max(1, int(size[1] * fill_ratio))
    contained = ImageOps.contain(image.convert("RGBA"), (target_w, target_h), method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    offset = ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2)
    mask = contained.getchannel("A") if "A" in contained.getbands() else None
    if mask is None:
        canvas.paste(contained, offset)
    else:
        canvas.paste(contained, offset, mask)
    return canvas


def load_object_image_for_box(path: str, size: tuple[int, int], fill_ratio: float = 0.88) -> Image.Image | None:
    if not path:
        return None
    image_path = Path(path)
    if not image_path.exists():
        return None
    try:
        image = Image.open(image_path).convert("RGBA")
        return contain_center(crop_to_foreground(image), size, fill_ratio=fill_ratio)
    except Exception:
        return None

def alpha_mask(image: Image.Image, radius: int | None = None) -> Image.Image:
    if "A" in image.getbands():
        mask = image.getchannel("A")
    else:
        mask = Image.new("L", image.size, 255)
    if radius is None:
        return mask
    return ImageChops.multiply(mask, rounded_mask(image.size, radius))


def draw_food_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    subtitle: str = "",
    fill: str = "#F6F2E7",
    outline: str = "#2A2F38",
    highlight: str | None = None,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=24, fill=fill, outline=outline, width=4)
    if highlight:
        inset = 8
        draw.rounded_rectangle((x0 + inset, y0 + inset, x1 - inset, y1 - inset), radius=20, outline=highlight, width=8)
    title_font = load_font(26)
    subtitle_font = load_font(18)
    pad = 18
    draw_wrapped_text(draw, (x0 + pad, y0 + pad), title, title_font, max(40, x1 - x0 - pad * 2), fill="#1C1F24")
    if subtitle:
        draw_wrapped_text(draw, (x0 + pad, y0 + 68), subtitle, subtitle_font, max(40, x1 - x0 - pad * 2), fill="#5B6472")


def draw_food_tile(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    record: FoodRecord,
    subtitle: str = "",
    fill: str = "#F6F2E7",
    outline: str = "#2A2F38",
    highlight: str | None = None,
    show_metadata: bool = True,
    show_title: bool = True,
) -> None:
    draw = ImageDraw.Draw(canvas)
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=24, fill=fill, outline=outline, width=4)
    if highlight:
        inset = 8
        draw.rounded_rectangle((x0 + inset, y0 + inset, x1 - inset, y1 - inset), radius=20, outline=highlight, width=8)

    image_height = int((y1 - y0) * (0.6 if not subtitle and not show_metadata else 0.56))
    image_box = (x0 + 12, y0 + 12, x1 - 12, y0 + 12 + image_height)
    loaded = load_image_for_box(record.preferred_image_path, (image_box[2] - image_box[0], image_box[3] - image_box[1]))
    if loaded is not None:
        mask = alpha_mask(loaded, radius=18)
        canvas.paste(loaded, (image_box[0], image_box[1]), mask)
        draw.rounded_rectangle(image_box, radius=18, outline="#FFFFFF", width=2)
    else:
        fallback_box = image_box
        draw.rounded_rectangle(fallback_box, radius=18, fill=lighten(category_color(record.primary_macro_category), 0.76), outline="#FFFFFF", width=2)
        initials = " ".join(word[:1].upper() for word in record.title_text.split()[:2]).strip() or "F"
        draw.text(((fallback_box[0] + fallback_box[2]) // 2, (fallback_box[1] + fallback_box[3]) // 2 - 12), initials, font=load_font(44), fill="#FFFFFF", anchor="mm")

    extra = subtitle
    if show_metadata and not subtitle:
        extra = category_label(record.primary_macro_category)

    if not show_title:
        return

    title = record.title_text
    title_width = max(40, x1 - x0 - 32)
    max_title_lines = 2 if extra else 3
    title_font = load_font(24)
    title_lines = wrap_text(draw, title, title_font, title_width)
    while (len(title_lines) > max_title_lines or any(draw.textbbox((0, 0), line, font=title_font)[2] - draw.textbbox((0, 0), line, font=title_font)[0] > title_width for line in title_lines)) and getattr(title_font, 'size', 24) > 15:
        title_font = load_font(getattr(title_font, 'size', 24) - 1)
        title_lines = wrap_text(draw, title, title_font, title_width)
    if len(title_lines) > max_title_lines:
        title_lines = title_lines[:max_title_lines]
        title_lines[-1] = title_lines[-1][: max(1, len(title_lines[-1]) - 1)].rstrip() + '…'

    text_top = image_box[3] + 14
    line_gap = 3
    current_y = text_top
    for line in title_lines:
        draw.text((x0 + 16, current_y), line, font=title_font, fill="#1C1F24")
        bbox = draw.textbbox((0, 0), line, font=title_font)
        current_y += (bbox[3] - bbox[1]) + line_gap

    if extra:
        subtitle_font = load_font(15)
        draw_wrapped_text(draw, (x0 + 16, current_y + 4), extra, subtitle_font, title_width, fill="#5B6472", line_gap=2)


def sample_by_category(records: list[FoodRecord], category: str, count: int, rng: random.Random) -> list[FoodRecord]:
    pool = [record for record in records if record.primary_macro_category == category]
    return choose_distinct(pool, count, rng)


def sample_by_predicate(records: list[FoodRecord], predicate, count: int, rng: random.Random) -> list[FoodRecord]:
    pool = [record for record in records if predicate(record)]
    return choose_distinct(pool, count, rng)


def lighten(color: str, factor: float) -> str:
    r, g, b = hex_color(color)
    out = (
        int(r + (255 - r) * factor),
        int(g + (255 - g) * factor),
        int(b + (255 - b) * factor),
    )
    return "#%02X%02X%02X" % out


def point_on_curve(x: float, baseline: float, peak_x: float, peak_y: float, tail_y: float, width: float) -> float:
    left = math.exp(-((x - peak_x) ** 2) / max(width, 1e-6))
    right = math.exp(-x * 1.2)
    return baseline + peak_y * left + tail_y * right


def strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(text or "")).strip()



