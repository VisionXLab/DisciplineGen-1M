# Dataset Construction Pipelines

This directory contains four open-source data-construction pipelines:

- `xiangqi`: board-game editing tasks for chess and Chinese chess
- `go`: Go crucial-move editing tasks
- `static`: static layout and tactics-board synthesis tasks
- `nutrition`: sports-nutrition visual editing tasks

The implementation keeps the historical source-code directories for compatibility:

- `xiangqi` -> [chess_xiangqi/README.md](./chess_xiangqi/README.md)
- `go` -> [go/README.md](./go/README.md)
- `static` -> [sports_tactics/README.md](./sports_tactics/README.md)
- `nutrition` -> [sports_nutrition/README.md](./sports_nutrition/README.md)

Each pipeline follows the same high-level stages:

1. Download or prepare raw data.
2. Parse the raw source into structured records.
3. Prepare visual assets when needed.
4. Configure optional engines or external tools.
5. Render paired `editing` and `gt` images.
6. Export unified annotations and metadata.

## Pipeline Summary

| Pipeline | Raw source | Main processing | Optional engine/tool | Builder |
| --- | --- | --- | --- | --- |
| `xiangqi` | Lichess PGN / XQBase HTML | move parsing, board rendering, legal-move generation | Stockfish / Pikafish | `scripts/chess_xiangqi/build_board_dataset.py` |
| `go` | KataGo SGF archives | SGF parsing, candidate sampling, strong relabeling | KataGo analysis | `scripts/go/build_go_dataset.py` |
| `static` | StatsBomb / Metrica records | canonical tactics records, formation/layout rendering | none | `scripts/sports_tactics/build_sports_tactics_dataset.py` |
| `nutrition` | USDA FoodData Central | food asset table, GI labels, food-image assets | none | `scripts/sports_nutrition/build_sports_nutrition_dataset.py` |

## Output Format

Each renderer writes:

- `output_root/<dataset_name>.json`
- `output_root/editing/*.png`
- `output_root/gt/*.png`

The sample JSON aligns each metadata record with the corresponding input and target images. Use `scripts/export_unified_annotations.py` to convert rendered datasets into the final annotation/meta format.
