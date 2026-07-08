# XQBase Xiangqi Pipeline

This file is superseded by:

- [xiangqi_pipeline.md](./xiangqi_pipeline.md)

Use the new document for:

- XQBase download
- page parsing
- piece-asset preprocessing
- `opening`
- `legal_moves`
- `bestmove`

The new document reflects the current full-coverage behavior:

- `legal_moves` exports every eligible current-side piece from every eligible position
- `bestmove` scans every eligible position in deterministic order and keeps those that pass engine-stability filters
