#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from xiangqi_utils import PIECE_PNG_NAME, normalize_piece_asset_image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Normalize Xiangqi piece PNG assets into transparent, fixed-size canvases.')
    parser.add_argument('--input-dir', required=True, help='Directory containing the raw piece PNGs.')
    parser.add_argument('--output-dir', required=True, help='Directory to store normalized piece PNGs.')
    parser.add_argument('--canvas-size', type=int, default=512, help='Square canvas size for normalized assets.')
    parser.add_argument('--scale-ratio', type=float, default=0.9, help='Relative occupied size inside the square canvas.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    missing = []
    names = sorted(set(PIECE_PNG_NAME.values()))
    for name in names:
        src = input_dir / name
        if not src.is_file():
            missing.append(name)
            continue
        image = Image.open(src).convert('RGBA')
        normalized = normalize_piece_asset_image(image, canvas_size=args.canvas_size, scale_ratio=args.scale_ratio)
        normalized.save(output_dir / name)
        print(f'[ok] {name}')

    if missing:
        print('[missing] ' + ', '.join(missing))
        return 1

    print(f'Prepared {len(names)} Xiangqi piece assets into {output_dir}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
