#!/usr/bin/env python3
from __future__ import annotations

import argparse

import chess_backend
import xiangqi_backend


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Unified board-game dataset builder for chess and xiangqi.')
    parser.add_argument('--game', required=True, choices=['chess', 'xiangqi'])
    parser.add_argument('--task', required=True, choices=['opening', 'legal_moves', 'bestmove'])
    parser.add_argument('--input', required=True, help='PGN path for chess, JSONL path for xiangqi')
    parser.add_argument('--output-root', required=True)
    parser.add_argument('--max-samples', type=int, default=100, help='Number of samples to export. Use 0 for all available positions.')
    parser.add_argument('--image-size', type=int, default=1100)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--plies', type=int, default=4)
    parser.add_argument('--min-plies', type=int, default=4)
    parser.add_argument('--openings', nargs='*', default=[])
    parser.add_argument('--min-ply', type=int, default=6)
    parser.add_argument('--max-ply', type=int, default=40)
    parser.add_argument('--min-targets', type=int, default=2)
    parser.add_argument('--max-targets', type=int, default=12)
    parser.add_argument('--engine', help='Stockfish for chess bestmove, Pikafish for xiangqi bestmove')
    parser.add_argument('--engine-net', help='Optional NNUE network path for xiangqi engines such as Pikafish')
    parser.add_argument('--engine-threads', type=int, default=0, help='Optional engine Threads setting for xiangqi bestmove. 0 keeps engine default.')
    parser.add_argument('--engine-hash', type=int, default=0, help='Optional engine Hash setting in MB for xiangqi bestmove. 0 keeps engine default.')
    parser.add_argument('--depth', type=int, default=12)
    parser.add_argument('--verify-depth', type=int, default=16)
    parser.add_argument('--min-score-gap-cp', type=int, default=100)
    parser.add_argument('--max-abs-score-cp', type=int, default=600)
    parser.add_argument('--renderer', choices=['auto', 'svg', 'simple'], default='auto')
    parser.add_argument('--chess-light-square-image', default='')
    parser.add_argument('--chess-dark-square-image', default='')
    parser.add_argument('--xiangqi-setup-bin', default='xiangqi-setup')
    parser.add_argument('--svg-converter', default='auto', choices=['auto', 'cairosvg', 'rsvg-convert', 'magick', 'inkscape'])
    parser.add_argument('--board-theme', default='playok_2014_remake')
    parser.add_argument('--pieces-theme', default='playok_2014_chinese_noshadow')
    parser.add_argument('--annotations-theme', default='colors_alpha')
    parser.add_argument('--xiangqi-board-image', default='')
    parser.add_argument('--xiangqi-piece-assets', default='')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.game == 'chess':
        if args.task == 'opening':
            return chess_backend.build_opening_dataset(args)
        if args.task == 'legal_moves':
            return chess_backend.build_legal_moves_dataset(args)
        return chess_backend.build_bestmove_dataset(args)
    if args.task == 'opening':
        return xiangqi_backend.build_opening_dataset(args)
    if args.task == 'legal_moves':
        return xiangqi_backend.build_legal_moves_dataset(args)
    return xiangqi_backend.build_bestmove_dataset(args)


if __name__ == '__main__':
    raise SystemExit(main())

