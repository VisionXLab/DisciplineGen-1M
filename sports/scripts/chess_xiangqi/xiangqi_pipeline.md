# Xiangqi Full Pipeline

## Scope

This document records the runnable pipeline for Xiangqi data collection and dataset construction in this repo.

Current tasks:

- `opening`
- `legal_moves`
- `bestmove`

Unified builder:

- [build_board_dataset.py](./build_board_dataset.py)

Core backend:

- [xiangqi_backend.py](./xiangqi_backend.py)

## Prerequisites

Required inputs:

- downloaded XQBase game pages under `raw_data/xiangqi/games`
- parsed JSONL at `raw_data/xiangqi/xqbase_games.jsonl`
- blank board image
- prepared Xiangqi piece assets

Required tools:

- Python 3
- `Pillow`
- `Pikafish` plus `pikafish.nnue` for `bestmove`

Install basic Python dependency:

```bash
python3 -m pip install pillow
```

## Step 1. Download XQBase Pages

If you already scanned the valid range and know it ends at `gameid=12141`, the full-page download is:

```bash
bash scripts/chess_xiangqi/download_xqbase_pages.sh raw_data/xiangqi/xqbase_game_urls.txt raw_data/xiangqi/games
```

If you want to regenerate the sequential URL list first:

```bash
python3 scripts/chess_xiangqi/scan_xqbase_gameids.py --start-gameid 1 --end-gameid 12141 --output-urls raw_data/xiangqi/xqbase_game_urls.txt
```

The source format is:

- `https://www.xqbase.com/xqbase/?gameid=xxx`

## Step 2. Parse Downloaded Pages

Convert downloaded HTML pages into normalized JSONL:

```bash
python3 scripts/chess_xiangqi/parse_xqbase_game_pages.py --input-dir raw_data/xiangqi/games --output-jsonl raw_data/xiangqi/xqbase_games.jsonl
```

Each JSONL record contains at least:

- `source_id`
- `opening`
- `initial_fen`
- `moves_ucci`

Optional but recommended field:

- `opening_en`

If `opening_en` exists, the `opening` task will use it to build English instruction text. Otherwise it falls back to `opening`.

If you already generated:

- `raw_data/xiangqi/xqbase_games_with_opening_en.jsonl`

then prefer using that file as the `--input` for the `opening` task.

## Step 3. Prepare Xiangqi Piece Assets

Raw piece images should be normalized before rendering.

This preprocessing does:

- keep only the central circular piece region
- remove the rest of the background
- save to transparent background
- normalize to a fixed square canvas

Run:

```bash
python3 scripts/chess_xiangqi/prepare_xiangqi_piece_assets.py --input-dir raw_data/xiangqi/assets --output-dir raw_data/xiangqi/assets_prepared --canvas-size 512 --scale-ratio 0.9
```

Renderer inputs:

- board image: `raw_data/xiangqi/asset/blank_board.png`
- prepared pieces: `raw_data/xiangqi/assets_prepared`

## Task Logic

### Opening

Logic:

- group all games by `opening`
- take the first `--plies` moves from each game in the same opening
- count identical prefixes inside that window
- choose the most frequent prefix as the canonical opening template
- keep one canonical opening template per opening

This task is not per-position exhaustive. It is one canonical sample per opening.

### Legal Moves

Logic:

- iterate every game
- iterate every position whose ply is within `--min-ply` and `--max-ply`
- for the side to move, iterate every piece on that board
- if that piece has a legal-move count inside `--min-targets` and `--max-targets`, export one sample

This is now exhaustive over eligible positions and eligible current-side pieces.

### Best Move

Logic:

- iterate every game
- iterate every position whose ply is within `--min-ply` and `--max-ply`
- run Pikafish at `--depth`
- run Pikafish again at `--verify-depth`
- keep the sample only if both searches agree and pass the score-gap filters

This is now exhaustive over eligible positions in deterministic order, but still filtered by engine stability.

## Run Each Task

### Opening

```bash
python3 scripts/chess_xiangqi/build_board_dataset.py --game xiangqi --task opening --input raw_data/xiangqi/xqbase_games_with_opening_en.jsonl --output-root outputs/xiangqi_opening_full --max-samples 0 --plies 4 --min-plies 4 --renderer simple --xiangqi-board-image raw_data/xiangqi/asset/blank_board.png --xiangqi-piece-assets raw_data/xiangqi/assets_prepared
```

### Legal Moves

```bash
python3 scripts/chess_xiangqi/build_board_dataset.py --game xiangqi --task legal_moves --input raw_data/xiangqi/xqbase_games.jsonl --output-root outputs/xiangqi_legal_moves_full --max-samples 0 --min-ply 6 --max-ply 40 --min-targets 2 --max-targets 12 --renderer simple --xiangqi-board-image raw_data/xiangqi/asset/blank_board.png --xiangqi-piece-assets raw_data/xiangqi/assets_prepared
```

### Best Move

```bash
python3 scripts/chess_xiangqi/build_board_dataset.py --game xiangqi --task bestmove --input raw_data/xiangqi/xqbase_games.jsonl --output-root outputs/xiangqi_bestmove_full --max-samples 0 --min-ply 8 --max-ply 30 --engine "$PIKAFISH_ENGINE" --engine-net "$PIKAFISH_NET" --depth 12 --verify-depth 16 --min-score-gap-cp 100 --max-abs-score-cp 600 --renderer simple --xiangqi-board-image raw_data/xiangqi/asset/blank_board.png --xiangqi-piece-assets raw_data/xiangqi/assets_prepared
```

## Output Notes

Each task writes:

- `output_root/<dataset_name>.json`
- `output_root/editing/*.png`
- `output_root/gt/*.png`

Useful metadata now includes:

- `source_id`
- `fen`
- `ply`
- task-specific fields such as `targets` or `best_move_ucci`
