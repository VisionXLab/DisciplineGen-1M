# Go Dataset Pipeline

This directory builds Go image-editing data for the `crucial_move` task.

The input image is the current board position. The target image adds the key next move and labels it with `1`.

## Entry Points

- [build_go_dataset.py](./build_go_dataset.py): render final Go editing samples.
- [parse_katago_sgf.py](./parse_katago_sgf.py): parse KataGo SGF archives into candidate positions.
- [build_go_strong_supervision.py](./build_go_strong_supervision.py): relabel candidate positions with KataGo analysis.
- [go_utils.py](./go_utils.py): shared parsing and rendering utilities.
- [download_katago_archive.sh](./download_katago_archive.sh): download archive links from KataGo Archive.

## Output Format

Each rendered dataset writes:

- `output_root/<dataset_name>.json`
- `output_root/editing/*.png`
- `output_root/gt/*.png`

The JSON records align metadata with the corresponding input and target images.

## Data Source

The pipeline uses SGF records from KataGo Archive:

- `https://katagoarchive.org/kata1`

The archive contains multiple subsets, including `traininggames` and `ratinggames`. This pipeline uses SGF game records. It does not directly consume NPZ training tensors.

## Installation

Use Python 3.10+ and install the common project dependencies:

```bash
python -m pip install -r requirements.txt
```

For strong supervision, prepare:

- a `katago` executable
- a compatible `kata1-*.bin.gz` model
- an analysis config such as `analysis_example.cfg`

Example local layout:

```text
go_engine/katago_runtime/
├── katago
├── analysis_example.cfg
└── kata1-xxx.bin.gz
```

## Step 1: Download KataGo SGF Archives

```bash
bash scripts/go/download_katago_archive.sh traininggames raw_data/go/katago
```

This creates a subset directory similar to:

```text
raw_data/go/katago/traininggames/
├── index.html
├── download_links.txt
├── *.tar.bz2
└── ...
```

To download all supported subsets:

```bash
bash scripts/go/download_katago_archive.sh all raw_data/go/katago
```

## Step 2: Extract Archives

```bash
cd raw_data/go/katago/traininggames
for f in *.tar.bz2; do
  tar -xjf "$f"
done
```

If your archive is a ZIP file, use `unzip` instead.

## Step 3: Parse SGF Candidates

```bash
python scripts/go/parse_katago_sgf.py \
  --input raw_data/go/katago/traininggames \
  --output-jsonl raw_data/go/katago_candidates.jsonl \
  --min-ply 20 \
  --max-ply 120 \
  --sample-every 10 \
  --max-samples 5000
```

This step samples board positions from SGF main lines. The initial weak label is the next SGF move.

Useful debug flags:

```bash
--skip-count
--max-files 100
--no-progress
```

## Step 4: Relabel with KataGo Analysis

```bash
python scripts/go/build_go_strong_supervision.py \
  --input-jsonl raw_data/go/katago_candidates.jsonl \
  --output-jsonl raw_data/go/katago_strong.jsonl \
  --engine "$KATAGO_ENGINE" \
  --model "$KATAGO_MODEL" \
  --config "$KATAGO_CONFIG" \
  --max-visits 256 \
  --analysis-pv-len 12 \
  --min-top-visits 32 \
  --min-score-gap 1.5 \
  --min-winrate-gap 0.03 \
  --max-abs-score-lead 15
```

The output keeps only positions where the engine-selected top move is sufficiently reliable. Metadata preserves both the weak SGF answer and the engine result.

Optional engine log:

```bash
--engine-log raw_data/go/katago_engine.log
```

## Step 5: Render Final Images

```bash
python scripts/go/build_go_dataset.py \
  --input raw_data/go/katago_strong.jsonl \
  --input-format jsonl \
  --output-root outputs/go_crucial_move \
  --max-samples 1000 \
  --image-size 1024
```

Expected output:

```text
outputs/go_crucial_move/
├── go_crucial_move.json
├── editing/
└── gt/
```

## Troubleshooting

If `KataGo analysis` fails to start, first check the executable, model, and config paths. GPU builds also require compatible CUDA/cuDNN drivers.

If the Linux binary is an AppImage and FUSE is unavailable, the strong-supervision script sets `APPIMAGE_EXTRACT_AND_RUN=1` by default. To test manually:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 "$KATAGO_ENGINE" analysis \
  -model "$KATAGO_MODEL" \
  -config "$KATAGO_CONFIG"
```

If no samples pass the filters, relax the thresholds for debugging:

```bash
--min-top-visits 8 \
--min-score-gap 0.5 \
--min-winrate-gap 0.01 \
--max-abs-score-lead 30
```

For large SGF directories, use `--skip-count` to avoid the startup cost of counting files.
