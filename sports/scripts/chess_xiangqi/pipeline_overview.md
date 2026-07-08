# Chess / 象棋 数据构造管线

## 目录目标

这个目录统一收纳两类棋类数据构造代码：

- `Chess`
- `Chinese Chess / Xiangqi`

两者都覆盖 3 类图像编辑任务：

- 开局编辑 / Opening
- 合法落点高亮 / Legal Moves
- 最优下一手绘制 / Best Move

统一数据输出格式保持为：

- `xxx.json`
- `xxx/editing/*.png`
- `xxx/gt/*.png`

## Chess 管线

### 1. 数据来源

- 主要来源：Lichess 标准棋 PGN 月度库
- 原始格式：`PGN`
- 关键字段：
  - `Opening`
  - `ECO`
  - 主线走子序列

### 2. Opening 数据构造

思路：

- 从 PGN 中读取 `Opening`
- 按 opening 名称分组
- 对每组只看前 `N` 个 half-moves
- 取该 opening 在前 `N` 步内所有样本都共同经过的最长公共前缀
- `editing` 使用标准初始局面
- `gt` 使用这个公共前缀最后一步对应的 canonical opening 局面

指令模板：

- `Edit the chess diagram to show the Polish Opening.`

当前实现：

- [chess_backend.py](./chess_backend.py)

### 3. Legal Moves 数据构造

思路：

- 从 PGN 中间局面采样
- 随机选一个当前行动方的棋子
- 用规则引擎求该棋子的合法终点
- `editing` 为原局面
- `gt` 为在目标格点上做高亮后的局面

指令模板：

- `Highlight the squares the queen can move to.`

当前实现：

- [chess_backend.py](./chess_backend.py)

### 4. Best Move 数据构造

思路：

- 从 PGN 中盘采样局面
- 用 `Stockfish` 分析局面
- 采用 shallow / deep 双深度一致性过滤
- 再用 `top-1 vs top-2` 分差做稳定性筛选
- `editing` 为原局面
- `gt` 为标出最佳下一手箭头的局面

指令模板：

- `Draw White's best move for the next turn.`

当前实现：

- [chess_backend.py](./chess_backend.py)

## 象棋管线

### 1. 数据来源

- 主要来源：XQBase 棋谱页
- 原始格式：网页 HTML
- 中间结构化格式：`jsonl`
- 关键字段：
  - `source_id`
  - `opening`
  - `initial_fen`
  - `moves_ucci`

相关抓取和解析脚本：

- [extract_xqbase_game_urls.py](./extract_xqbase_game_urls.py)
- [download_xqbase_pages.sh](./download_xqbase_pages.sh)
- [parse_xqbase_game_pages.py](./parse_xqbase_game_pages.py)

### 2. Opening 数据构造

思路：

- 从结构化 `jsonl` 中读取 `opening`
- 按 opening 名称分组
- 对每组只看前 `N` 个 `moves_ucci`
- 取该 opening 在前 `N` 步内所有样本都共同经过的最长公共前缀
- `editing` 为初始局面
- `gt` 为这个公共前缀最后一步对应的 canonical opening 局面

指令模板：

- `Edit the Chinese chess diagram to show the C65. 五七炮对屏风马进７卒 红左直车对黑右直车右炮巡河.`

当前实现：

- [xiangqi_backend.py](./xiangqi_backend.py)

### 3. Legal Moves 数据构造

思路：

- 从 `jsonl` 局面序列中采样中盘局面
- 对当前行动方的棋子生成合法着法
- 覆盖所有棋子类型：车马相仕帅炮兵
- `editing` 为原局面
- `gt` 为对合法终点做高亮后的局面

指令模板：

- `Highlight the legal moves of the Red left rook.`

当前实现：

- [xiangqi_backend.py](./xiangqi_backend.py)
- 规则与渲染辅助：
  - [xiangqi_utils.py](./xiangqi_utils.py)

### 4. Best Move 数据构造

思路：

- 从 `jsonl` 中盘局面采样
- 用 `Pikafish` 输出 `bestmove`
- 做 shallow / deep 双深度一致性过滤
- 再用分差阈值过滤不稳定局面
- `editing` 为原局面
- `gt` 为带箭头的最佳下一手局面

这里的标签来源是引擎，而不是人类棋谱中的下一手。

指令模板：

- `Draw Red's best move for the next turn.`

当前实现：

- [xiangqi_backend.py](./xiangqi_backend.py)
- 规则与渲染辅助：
  - [xiangqi_utils.py](./xiangqi_utils.py)

## 渲染现状

### Chess

- 当前主要依赖 `python-chess`
- 可选 `svg` 渲染
- 也保留简单 fallback renderer

### 象棋

- 当前主要依赖 `xiangqi-setup` 生成底图
- 合法落点高亮和 bestmove 箭头由后处理叠加
- 当前推荐主题：
  - `playok_2014_remake`
  - `playok_2014_chinese_noshadow`

## 重构结论

`Chess` 和 `象棋` 已经可以统一抽象为同一个任务骨架：

- 数据读取
- 局面采样
- 任务标签生成
- `editing / gt / json` 导出

但它们在 3 个层面仍明显不同：

- 原始数据源不同：`PGN` vs `HTML -> JSONL`
- 规则与引擎不同：`python-chess + Stockfish` vs `xiangqi_utils + Pikafish`
- 渲染器不同：`python-chess SVG` vs `xiangqi-setup`

因此当前最合理的组织方式是：

- 抽成按游戏划分的 backend 模块
- 增加统一入口脚本

当前统一入口：

- [build_board_dataset.py](./build_board_dataset.py)

它已经支持两个 mode：

- `--game chess`
- `--game xiangqi`

以及三种任务：

- `--task opening`
- `--task legal_moves`
- `--task bestmove`

