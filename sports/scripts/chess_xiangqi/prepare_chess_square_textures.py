#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Crop and normalize chess square textures.')
    parser.add_argument('--light-input', required=True)
    parser.add_argument('--dark-input', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--crop', type=int, default=8, help='Pixels to crop from each border before resizing.')
    parser.add_argument('--size', type=int, default=256)
    return parser.parse_args()


def process_one(src: Path, dst: Path, crop: int, size: int) -> None:
    image = Image.open(src).convert('RGB')
    w, h = image.size
    left = min(crop, w // 8)
    top = min(crop, h // 8)
    right = max(left + 1, w - left)
    bottom = max(top + 1, h - top)
    image = image.crop((left, top, right, bottom))
    image = ImageOps.fit(image, (size, size), method=Image.Resampling.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    image.save(dst)


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    process_one(Path(args.light_input), output_dir / 'light_square.png', args.crop, args.size)
    process_one(Path(args.dark_input), output_dir / 'dark_square.png', args.crop, args.size)
    print(f'Wrote textures to {output_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
