# Sports Nutrition Dataset Construction

本目录用于构造 `Sports Nutrition` 图像编辑数据。统一按下面 6 个阶段推进：

1. 原始数据下载
2. 环境配置
3. 资产处理
4. 引擎说明
5. 数据生成
6. 快速校验

最终主资产表默认写到：

- `raw_data/sports_nutrition/food_assets.json`

最终数据集统一导出为：

- `output_root/<dataset_name>.json`
- `output_root/editing/*.png`
- `output_root/gt/*.png`

## 1. 原始数据下载

推荐目录：

```bash
mkdir -p raw_data/sports_nutrition/usda
mkdir -p raw_data/sports_nutrition/images
mkdir -p raw_data/sports_nutrition/cutouts
```

下载并解压 USDA FoodData Central：

```bash
python scripts/sports_nutrition/download_fooddata_central.py \
  --output-dir raw_data/sports_nutrition/usda \
  --dataset foundation survey
```

下载完成后，后续默认使用：

- `raw_data/sports_nutrition/usda/foundation/extracted`
- `raw_data/sports_nutrition/usda/survey/extracted`

## 2. 环境配置

建议 Python 3.10+。

最小 Python 依赖：

```bash
python -m pip install -U pillow
```

如果你要用脚本内置下载逻辑抓 USDA 压缩包，环境里最好有：

- `wget`

但没有 `wget` 也可以回落到 Python 自带的 HTTP 下载。

## 3. 资产处理

### 3.1 准备食物清单

默认食物清单文件：

- `scripts/sports_nutrition/sports_nutrition_food_list.txt`

格式：

```text
white rice	白米饭
yogurt	酸奶
carrot	胡萝卜
```

可选辅助文件：

- `raw_data/sports_nutrition/usda_selection.json`
  - 手工固定 `food_name -> fdc_id`
- `raw_data/sports_nutrition/gi_reference.csv`
  - 手工维护 GI 标注

### 3.2 从 USDA 构建基础资产

```bash
python scripts/sports_nutrition/build_food_assets.py \
  --input raw_data/sports_nutrition/usda/foundation/extracted raw_data/sports_nutrition/usda/survey/extracted \
  --food-list scripts/sports_nutrition/sports_nutrition_food_list.txt \
  --selection-json raw_data/sports_nutrition/usda_selection.json \
  --output-json raw_data/sports_nutrition/food_assets.json \
  --output-unmatched raw_data/sports_nutrition/food_unmatched.json
```

说明：

- `selection-json` 优先级最高，用于强绑定到指定 `fdc_id`
- `food_unmatched.json` 用于后续补匹配

### 3.3 排查未匹配食品

```bash
python scripts/sports_nutrition/inspect_usda_candidates.py \
  --input raw_data/sports_nutrition/usda/foundation/extracted raw_data/sports_nutrition/usda/survey/extracted \
  --unmatched-json raw_data/sports_nutrition/food_unmatched.json \
  --top-k 10 \
  --output-json raw_data/sports_nutrition/usda_candidates_unmatched.json
```

挑选合适的 `fdc_id` 回填到 `usda_selection.json` 后，重新运行上一步。

### 3.4 合并 GI 标注

推荐 GI 表头：

```csv
food_name,zh_name,gi_value,source,source_note
white rice,白米饭,83,gluok.com,
banana,香蕉,52,gluok.com,
```

合并命令：

```bash
python scripts/sports_nutrition/apply_gi_reference.py \
  --assets-json raw_data/sports_nutrition/food_assets.json \
  --gi-csv raw_data/sports_nutrition/gi_reference.csv \
  --default-source gluok.com
```

### 3.5 合并本地真实食物图片

图片目录建议按中文名命名文件，例如：

- `raw_data/sports_nutrition/images/核桃.png`
- `raw_data/sports_nutrition/images/酸奶.jpg`

执行：

```bash
python scripts/sports_nutrition/apply_food_images.py \
  --assets-json raw_data/sports_nutrition/food_assets.json \
  --images-dir raw_data/sports_nutrition/images \
  --output-json raw_data/sports_nutrition/food_assets.json \
  --missing-json raw_data/sports_nutrition/food_images_missing.json \
  --default-image-source local_manual
```

### 3.6 合并本地 cutout 透明图

如果你有抠图资产，建议单独放到：

- `raw_data/sports_nutrition/cutouts`

执行：

```bash
python scripts/sports_nutrition/apply_food_cutouts.py \
  --assets-json raw_data/sports_nutrition/food_assets.json \
  --cutouts-dir raw_data/sports_nutrition/cutouts \
  --output-json raw_data/sports_nutrition/food_assets.json \
  --missing-json raw_data/sports_nutrition/food_cutouts_missing.json \
  --default-cutout-source local_cutout
```

### 3.7 清理冗余字段

```bash
python scripts/sports_nutrition/prune_food_assets.py \
  --assets-json raw_data/sports_nutrition/food_assets.json
```

如果希望保留清理前版本，可写到新文件：

```bash
python scripts/sports_nutrition/prune_food_assets.py \
  --assets-json raw_data/sports_nutrition/food_assets.json \
  --output-json raw_data/sports_nutrition/food_assets.pruned.json
```

## 4. 引擎说明

营养数据管线不依赖棋类或搜索引擎。

这一阶段统一记为：

- 不需要额外引擎下载

## 5. 数据生成

在 `food_assets.json` 准备好后，直接渲染目标任务：

```bash
python scripts/sports_nutrition/build_sports_nutrition_dataset.py \
  --input-jsonl raw_data/sports_nutrition/food_assets.json \
  --task classify_grouping \
  --output-root outputs/sports_nutrition_grouping \
  --max-samples 20
```

如果想先只枚举计划，不立刻渲染：

```bash
python scripts/sports_nutrition/build_sports_nutrition_dataset.py \
  --input-jsonl raw_data/sports_nutrition/food_assets.json \
  --task all \
  --plan-jsonl raw_data/sports_nutrition/render_plan.jsonl \
  --max-samples 200
```

再根据现有计划渲染：

```bash
python scripts/sports_nutrition/build_sports_nutrition_dataset.py \
  --input-jsonl raw_data/sports_nutrition/food_assets.json \
  --render-plan-jsonl raw_data/sports_nutrition/render_plan.jsonl \
  --output-root outputs/sports_nutrition_rendered \
  --max-samples 200
```

可用任务：

- `classify_grouping`
- `pie_chart_integration`
- `nutrition_pyramid`
- `highlight_high_gi`
- `highlight_high_protein`
- `glucose_curve_low_gi`
- `curve_label_gi`
- `low_intensity_distribution`
- `protein_curve_label`
- `fat_curve_draw`
- `all`

## 6. 快速校验

检查资产覆盖情况：

```bash
python - <<'PY'
import json
from pathlib import Path
items = json.loads(Path("raw_data/sports_nutrition/food_assets.json").read_text(encoding="utf-8"))
print("assets_count =", len(items))
print("gi_filled =", sum(1 for x in items if x.get("gi_value") is not None))
print("local_image_filled =", sum(1 for x in items if x.get("local_image_path")))
print("cutout_image_filled =", sum(1 for x in items if x.get("cutout_image_path")))
PY
```

检查样本导出目录：

- `outputs/sports_nutrition_grouping/<dataset_name>.json`
- `outputs/sports_nutrition_grouping/editing`
- `outputs/sports_nutrition_grouping/gt`
