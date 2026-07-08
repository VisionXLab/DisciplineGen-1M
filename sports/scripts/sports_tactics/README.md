# Sports Tactics Dataset Construction

本目录用于构造 `Sports Tactic` 足球战术板图像编辑数据。统一按下面 6 个阶段推进：

1. 原始数据下载
2. 环境配置
3. 资产处理
4. 引擎说明
5. 数据生成
6. 快速校验

当前已经接通渲染的足球任务：

- `soccer_formation_dots`
- `soccer_formation_jerseys`
- `soccer_ball_handler_highlight`

最终数据集统一导出为：

- `output_root/<dataset_name>.json`
- `output_root/editing/*.png`
- `output_root/gt/*.png`

## 1. 原始数据下载

### 1.1 主线数据源：StatsBomb Open Data

```bash
python scripts/sports_tactics/download_statsbomb_open.py \
  --output-dir raw_data/sports_tactics/statsbomb
```

下载并解压后，解析根目录为：

- `raw_data/sports_tactics/statsbomb/extracted/data`

### 1.2 可选补充源：Metrica Sample Data

```bash
python scripts/sports_tactics/download_metrica_sample.py \
  --output-dir raw_data/sports_tactics/metrica
```

说明：

- `Metrica` 目前只接到 canonical JSONL 解析阶段
- 当前 `build_sports_tactics_dataset.py` 还没有直接渲染 `soccer_next_frame` 样本

## 2. 环境配置

建议 Python 3.10+。

最小 Python 依赖：

```bash
python -m pip install -U pillow
```

如果希望优先使用命令行下载器，环境里最好有：

- `wget`

## 3. 资产处理

足球战术板没有单独的图片资产库，这一阶段的“资产处理”等价于：

- 把公开数据解析成统一 canonical JSONL
- 对 formation 样本做去重
- 为后续战术板渲染准备稳定输入

### 3.1 解析 StatsBomb 到 canonical JSONL

如果只要 formation：

```bash
python scripts/sports_tactics/parse_statsbomb_open.py \
  --statsbomb-root raw_data/sports_tactics/statsbomb/extracted/data \
  --output-jsonl raw_data/sports_tactics/statsbomb_formations_full.jsonl
```

For a quick smoke test, limit the scan:

```bash
python scripts/sports_tactics/parse_statsbomb_open.py \
  --statsbomb-root raw_data/sports_tactics/statsbomb/extracted/data \
  --output-jsonl raw_data/sports_tactics/statsbomb_formations_quickstart.jsonl \
  --max-matches 5
```

这个文件可以直接作为 formation-only 流程的 prune 输入。

如果还要球权持有者高亮：

```bash
python scripts/sports_tactics/parse_statsbomb_open.py \
  --statsbomb-root raw_data/sports_tactics/statsbomb/extracted/data \
  --output-jsonl raw_data/sports_tactics/statsbomb_tactics_full.jsonl \
  --include-ball-handler \
  --highlight-stride 18 \
  --max-highlight-per-match 12
```

### 3.2 对 formation 样本去重

`prune_statsbomb_tactics_jsonl.py` 默认只保留 `soccer_formation` 记录，因此不要覆盖带高亮任务的全量文件。

推荐单独产出一个去重后的 formation 文件：

```bash
python scripts/sports_tactics/prune_statsbomb_tactics_jsonl.py \
  --input-jsonl raw_data/sports_tactics/statsbomb_tactics_full.jsonl \
  --output-jsonl raw_data/sports_tactics/statsbomb_formations_pruned.jsonl
```

### 3.3 可选：解析 Metrica tracking 样本

```bash
python scripts/sports_tactics/parse_metrica_sample.py \
  --metrica-root raw_data/sports_tactics/metrica/extracted/data \
  --output-jsonl raw_data/sports_tactics/metrica_next_frame.jsonl
```

说明：

- 这一步会输出 `soccer_next_frame` 记录
- 当前仓库还没有把它接到战术板渲染器里

## 4. 引擎说明

足球战术板数据管线不依赖搜索引擎或棋类引擎。

这一阶段统一记为：

- 不需要额外引擎下载

## 5. 数据生成

### 5.1 Formation dots

```bash
python scripts/sports_tactics/build_sports_tactics_dataset.py \
  --input-jsonl raw_data/sports_tactics/statsbomb_formations_pruned.jsonl \
  --task soccer_formation_dots \
  --output-root outputs/soccer_formation_dots \
  --max-samples 200
```

### 5.2 Formation jerseys

```bash
python scripts/sports_tactics/build_sports_tactics_dataset.py \
  --input-jsonl raw_data/sports_tactics/statsbomb_formations_pruned.jsonl \
  --task soccer_formation_jerseys \
  --output-root outputs/soccer_formation_jerseys \
  --max-samples 200
```

### 5.3 Ball-handler highlight

球权高亮必须使用未被 prune 掉高亮记录的全量文件：

```bash
python scripts/sports_tactics/build_sports_tactics_dataset.py \
  --input-jsonl raw_data/sports_tactics/statsbomb_tactics_full.jsonl \
  --task soccer_ball_handler_highlight \
  --output-root outputs/soccer_ball_handler \
  --max-samples 200
```

当前渲染逻辑：

- `soccer_formation_dots`
  - `before`: 空白战术板
  - `after`: 蓝点落在阵型槽位
- `soccer_formation_jerseys`
  - `before`: 空白战术板
  - `after`: 白色球衣落在阵型槽位
- `soccer_ball_handler_highlight`
  - `before`: 双方球员已在板上
  - `after`: 持球队员外侧增加橙色圆环

## 6. 快速校验

建议至少检查下面两个文件是否同时存在：

- `raw_data/sports_tactics/statsbomb_tactics_full.jsonl`
- `raw_data/sports_tactics/statsbomb_formations_pruned.jsonl`

并确认输出目录包含：

- `outputs/soccer_formation_dots/<dataset_name>.json`
- `outputs/soccer_formation_dots/editing`
- `outputs/soccer_formation_dots/gt`
