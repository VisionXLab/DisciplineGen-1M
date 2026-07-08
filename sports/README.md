# GRADE Sports Dataset Pipelines

This repository contains data-construction pipelines for multimodal image-editing datasets in sports-related domains. The current pipelines cover:

- `xiangqi`: board-game state editing, including chess/xiangqi opening, legal-move, and best-move tasks
- `go`: Go crucial-move editing with optional KataGo-based strong supervision
- `static`: static tactical-board and layout synthesis tasks
- `nutrition`: sports-nutrition visual editing tasks

Each builder exports paired input and target images plus structured metadata. The exported datasets can then be converted into a unified annotation format for image-generation training.

## Repository Layout

- `scripts/chess_xiangqi/`: source code for the `xiangqi` pipeline. It includes both chess and Chinese-chess board rendering tasks.
- `scripts/go/`: source code for the `go` pipeline.
- `scripts/sports_tactics/`: source code for the `static` pipeline, currently focused on soccer tactics-board layouts.
- `scripts/sports_nutrition/`: source code for the `nutrition` pipeline.
- `scripts/export_unified_annotations.py`: converts rendered datasets into unified JSONL annotations.
- `scripts/expand_annotation_prompts.py`: creates prompt-diversified annotation variants.

## Installation

```bash
python -m pip install -r requirements.txt
```

Some optional steps use external binaries:

- `zstd` for reading Lichess `.pgn.zst` archives
- `wget` for resumable downloads
- `stockfish` for chess best-move labels
- `pikafish` plus `pikafish.nnue` for xiangqi best-move labels
- `katago` plus a compatible model/config for Go strong supervision

## Quickstart

The following smoke tests render one tiny sample for each pipeline and export unified annotations. They do not require downloading large public archives or configuring external engines.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
mkdir -p raw_data/go raw_data/xiangqi raw_data/static outputs
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Xiangqi

Create one synthetic XQBase-like JSONL record:

```bash
python - <<'PY'
import json
from pathlib import Path

Path("raw_data/xiangqi").mkdir(parents=True, exist_ok=True)
record = {
    "source_id": "quickstart_xiangqi_1",
    "opening": "Quickstart Opening",
    "opening_en": "Quickstart Opening",
    "initial_fen": "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w",
    "moves_ucci": ["h2e2", "h9e7", "b0c2", "b9c7"],
}
Path("raw_data/xiangqi/quickstart.jsonl").write_text(
    json.dumps(record, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
PY
```

Render and export:

```bash
python scripts/chess_xiangqi/build_board_dataset.py \
  --game xiangqi \
  --task opening \
  --input raw_data/xiangqi/quickstart.jsonl \
  --output-root outputs/xiangqi_quickstart \
  --max-samples 1 \
  --image-size 512 \
  --plies 4 \
  --min-plies 4 \
  --renderer simple \
  --xiangqi-board-image scripts/chess_xiangqi/assets/blank_board.png \
  --xiangqi-piece-assets scripts/chess_xiangqi/assets

python scripts/export_unified_annotations.py \
  --dataset-root outputs/xiangqi_quickstart \
  --output-root outputs/unified_xiangqi_quickstart
```

### Go

Create one Go crucial-move JSONL record:

```bash
python - <<'PY'
import json
from pathlib import Path
Path("raw_data/go").mkdir(parents=True, exist_ok=True)
record = {
    "size": 19,
    "black_stones": ["D4", "Q16"],
    "white_stones": ["D16", "Q4"],
    "to_play": "black",
    "answer": "K10",
    "category": "Go Problem",
    "source_id": "quickstart_1"
}
Path("raw_data/go/quickstart.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
PY
```

Render and export:

```bash
python scripts/go/build_go_dataset.py \
  --input raw_data/go/quickstart.jsonl \
  --input-format jsonl \
  --output-root outputs/go_quickstart \
  --max-samples 1 \
  --image-size 512

python scripts/export_unified_annotations.py \
  --dataset-root outputs/go_quickstart \
  --output-root outputs/unified_go_quickstart
```

### Static Tactics

Download StatsBomb Open Data, parse a small canonical subset, render, and export:

```bash
python scripts/sports_tactics/download_statsbomb_open.py \
  --output-dir raw_data/static/statsbomb

python scripts/sports_tactics/parse_statsbomb_open.py \
  --statsbomb-root raw_data/static/statsbomb/extracted/data \
  --output-jsonl raw_data/static/statsbomb_formations_full.jsonl \
  --max-matches 5

python scripts/sports_tactics/prune_statsbomb_tactics_jsonl.py \
  --input-jsonl raw_data/static/statsbomb_formations_full.jsonl \
  --output-jsonl raw_data/static/statsbomb_formations_pruned.jsonl

python scripts/sports_tactics/build_sports_tactics_dataset.py \
  --input-jsonl raw_data/static/statsbomb_formations_pruned.jsonl \
  --task soccer_formation_dots \
  --output-root outputs/static_quickstart \
  --max-samples 1 \
  --image-size 512

python scripts/export_unified_annotations.py \
  --dataset-root outputs/static_quickstart \
  --output-root outputs/unified_static_quickstart
```

### Nutrition

Render one static glucose-curve editing sample and export it:

```bash
python scripts/sports_nutrition/build_sports_nutrition_dataset.py \
  --task glucose_curve_low_gi \
  --output-root outputs/nutrition_quickstart \
  --max-samples 1 \
  --image-size 512

python scripts/export_unified_annotations.py \
  --dataset-root outputs/nutrition_quickstart \
  --output-root outputs/unified_nutrition_quickstart
```

## Data Sources

The pipelines download from public sources and do not require committed API keys:

- Lichess Database: `https://database.lichess.org/standard/`
- XQBase: `https://www.xqbase.com/xqbase/`
- KataGo Archive: `https://katagoarchive.org/kata1`
- USDA FoodData Central: `https://fdc.nal.usda.gov/`
- Wikimedia Commons: `https://commons.wikimedia.org/`
- StatsBomb Open Data: `https://github.com/statsbomb/open-data`
- Metrica sample data: `https://github.com/metrica-sports/sample-data`

## Minimal Workflow

1. Download or prepare raw data under an ignored directory such as `raw_data/`.
2. Run one of the domain builders under `scripts/`.
3. Write generated images and dataset JSON files under `outputs/`.
4. Convert rendered datasets with `scripts/export_unified_annotations.py`.
5. Optionally diversify prompts with `scripts/expand_annotation_prompts.py`.

See the pipeline-specific README files for full commands:

- `scripts/chess_xiangqi/README.md`
- `scripts/go/README.md`
- `scripts/sports_tactics/README.md`
- `scripts/sports_nutrition/README.md`

## Unified Annotation Format

Rendered datasets can be converted into annotation records containing:

- `id`
- `image`
- `conversations`
- `width`
- `height`
- `generation_flags`
- `original`

The first image is the conditioning image and the second image is the generation target. Dataset-level metadata is written to `meta.json`.
