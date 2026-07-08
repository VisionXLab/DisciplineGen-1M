# Chess / Xiangqi Dataset Construction

本目录用于构造两类棋类图像编辑数据：

- `Chess`
- `Chinese Chess / Xiangqi`

统一入口脚本：

- `scripts/chess_xiangqi/build_board_dataset.py`

统一按下面 6 个阶段推进：

1. 原始数据下载
2. 环境配置
3. 资产处理
4. 引擎下载
5. 数据生成
6. 快速校验

最终数据集统一导出为：

- `output_root/<dataset_name>.json`
- `output_root/editing/*.png`
- `output_root/gt/*.png`

支持任务：

- `opening`
- `legal_moves`
- `bestmove`

## 1. 原始数据下载

推荐目录：

```bash
mkdir -p raw_data/chess
mkdir -p raw_data/xiangqi
```

### 1.1 Chess：下载 Lichess 标准棋 PGN

下载单个月：

```bash
wget -O raw_data/chess/lichess_db_standard_rated_2026-03.pgn.zst \
  https://database.lichess.org/standard/lichess_db_standard_rated_2026-03.pgn.zst
```

按年份批量下载：

```bash
bash scripts/chess_xiangqi/download_lichess_standard.sh raw_data/chess 2023 2025
```

从 `.pgn.zst` 中直接抽样，不需要整包解压：

```bash
python scripts/chess_xiangqi/extract_lichess_pgn_sample.py \
  --input-zst raw_data/chess/lichess_db_standard_rated_2026-03.pgn.zst \
  --output raw_data/chess/opening_sample.pgn \
  --max-games 5000
```

### 1.2 Xiangqi：下载 XQBase 棋谱页

全量顺扫并下载页面：

```bash
bash scripts/chess_xiangqi/download_xqbase_full.sh raw_data/xiangqi
```

如果只想先生成 URL 列表：

```bash
python scripts/chess_xiangqi/scan_xqbase_gameids.py \
  --start-gameid 1 \
  --stop-empty-run 5000 \
  --output-urls raw_data/xiangqi/xqbase_game_urls.txt \
  --output-log raw_data/xiangqi/xqbase_scan_log.tsv
```

再单独下载页面：

```bash
bash scripts/chess_xiangqi/download_xqbase_pages.sh \
  raw_data/xiangqi/xqbase_game_urls.txt \
  raw_data/xiangqi/games
```

解析为结构化 JSONL：

```bash
python scripts/chess_xiangqi/parse_xqbase_game_pages.py \
  --input-dir raw_data/xiangqi/games \
  --output-jsonl raw_data/xiangqi/xqbase_games.jsonl
```

## 2. 环境配置

建议 Python 3.10+。

通用依赖：

```bash
python -m pip install -U pillow
```

### 2.1 Chess 额外依赖

```bash
python -m pip install -U python-chess
```

如果想使用 `svg` 渲染：

```bash
python -m pip install -U cairosvg
```

还需要系统工具：

- `zstd`
  - `extract_lichess_pgn_sample.py` 直接依赖 `zstd -dc`
- `wget`
  - `download_lichess_standard.sh` 依赖

### 2.2 Xiangqi 额外依赖

如果你打算使用 `svg` 或 `auto` 渲染器，安装：

```bash
python -m pip install -U xiangqi-setup
```

可选的 SVG 转 PNG 转换器：

- `rsvg-convert`
- `cairosvg`
- `magick`
- `inkscape`

如果只使用仓库内置底板和 PNG 棋子资产，可以直接走 `--renderer simple`，不强依赖 `xiangqi-setup`。

## 3. 资产处理

### 3.1 Chess

Chess 不需要单独的图片资产处理，直接从 PGN 渲染棋盘即可。

### 3.2 Xiangqi

当前仓库已经自带一套可直接用于 `simple` 渲染器的资产：

- `scripts/chess_xiangqi/assets/blank_board.png`
- `scripts/chess_xiangqi/assets/*.png`

如果你要替换成自己的原始棋子图，可以先做归一化：

```bash
python scripts/chess_xiangqi/prepare_xiangqi_piece_assets.py \
  --input-dir raw_data/xiangqi/assets_raw \
  --output-dir raw_data/xiangqi/assets_prepared \
  --canvas-size 512 \
  --scale-ratio 0.9
```

之后把 `--xiangqi-piece-assets` 指向新的 `assets_prepared` 目录即可。

## 4. 引擎下载

### 4.1 Chess Best Move：Stockfish

`bestmove` 任务需要 `Stockfish`。安装方式可以是：

- 系统包管理器安装
- 手动下载二进制，然后把完整路径传给 `--engine`

Linux 常见示例：

```bash
sudo apt install -y stockfish
```

### 4.2 Xiangqi Best Move：Pikafish

`bestmove` 任务需要：

- `Pikafish` 可执行文件
- 与该二进制匹配的 `pikafish.nnue`

推荐使用同一 release 包中的二进制和网络文件，并在运行时显式传：

- `--engine "$PIKAFISH_ENGINE"`
- `--engine-net "$PIKAFISH_NET"`

## 5. 数据生成

### 5.1 Chess Opening

```bash
python scripts/chess_xiangqi/build_board_dataset.py \
  --game chess \
  --task opening \
  --input raw_data/chess/opening_sample.pgn \
  --output-root outputs/chess_opening \
  --max-samples 100 \
  --plies 4 \
  --renderer svg
```

### 5.2 Chess Legal Moves

```bash
python scripts/chess_xiangqi/build_board_dataset.py \
  --game chess \
  --task legal_moves \
  --input raw_data/chess/opening_sample.pgn \
  --output-root outputs/chess_legal_moves \
  --max-samples 120 \
  --min-ply 6 \
  --max-ply 40 \
  --min-targets 2 \
  --max-targets 12 \
  --renderer svg
```

### 5.3 Chess Best Move

```bash
python scripts/chess_xiangqi/build_board_dataset.py \
  --game chess \
  --task bestmove \
  --input raw_data/chess/opening_sample.pgn \
  --output-root outputs/chess_bestmove \
  --engine "$STOCKFISH_ENGINE" \
  --max-samples 60 \
  --min-ply 8 \
  --max-ply 30 \
  --depth 12 \
  --verify-depth 16 \
  --min-score-gap-cp 100 \
  --max-abs-score-cp 600 \
  --renderer svg
```

### 5.4 Xiangqi Opening

下面示例直接使用仓库内置底板和棋子资产：

```bash
python scripts/chess_xiangqi/build_board_dataset.py \
  --game xiangqi \
  --task opening \
  --input raw_data/xiangqi/xqbase_games.jsonl \
  --output-root outputs/xiangqi_opening \
  --max-samples 100 \
  --plies 4 \
  --renderer simple \
  --xiangqi-board-image scripts/chess_xiangqi/assets/blank_board.png \
  --xiangqi-piece-assets scripts/chess_xiangqi/assets
```

### 5.5 Xiangqi Legal Moves

```bash
python scripts/chess_xiangqi/build_board_dataset.py \
  --game xiangqi \
  --task legal_moves \
  --input raw_data/xiangqi/xqbase_games.jsonl \
  --output-root outputs/xiangqi_legal_moves \
  --max-samples 140 \
  --min-ply 6 \
  --max-ply 40 \
  --min-targets 2 \
  --max-targets 12 \
  --renderer simple \
  --xiangqi-board-image scripts/chess_xiangqi/assets/blank_board.png \
  --xiangqi-piece-assets scripts/chess_xiangqi/assets
```

### 5.6 Xiangqi Best Move

```bash
python scripts/chess_xiangqi/build_board_dataset.py \
  --game xiangqi \
  --task bestmove \
  --input raw_data/xiangqi/xqbase_games.jsonl \
  --output-root outputs/xiangqi_bestmove \
  --engine "$PIKAFISH_ENGINE" \
  --engine-net "$PIKAFISH_NET" \
  --max-samples 60 \
  --min-ply 8 \
  --max-ply 30 \
  --depth 12 \
  --verify-depth 16 \
  --min-score-gap-cp 100 \
  --max-abs-score-cp 600 \
  --renderer simple \
  --xiangqi-board-image scripts/chess_xiangqi/assets/blank_board.png \
  --xiangqi-piece-assets scripts/chess_xiangqi/assets
```

## 6. 快速校验

建议至少检查下面文件是否已经准备好：

- Chess
  - `raw_data/chess/opening_sample.pgn`
- Xiangqi
  - `raw_data/xiangqi/xqbase_games.jsonl`

如果运行 `bestmove`，再检查：

- Chess
  - `--engine` 指向真实 `stockfish` 二进制
- Xiangqi
  - `--engine` 指向真实 `pikafish` 二进制
  - `--engine-net` 指向真实 `pikafish.nnue`

输出目录应包含：

- `outputs/chess_opening/<dataset_name>.json`
- `outputs/chess_opening/editing`
- `outputs/chess_opening/gt`
