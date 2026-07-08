# Lichess -> Chess Image Editing Dataset

## 1. First check the format without full decompression

Lichess standard database is plain-text `PGN` inside a `.zst` file.

You do not need to fully decompress it first.

View the first few lines:

```bash
zstd -dc raw_data/chess/lichess_db_standard_rated_2026-03.pgn.zst | head -n 40
```

View the first 3 complete games:

```bash
zstd -dc raw_data/chess/lichess_db_standard_rated_2026-03.pgn.zst | awk '
BEGIN { RS=""; ORS="\n\n"; n=0 }
{
  print $0
  n++
  if (n>=3) exit
}'
```

Typical PGN structure:

```text
[Event "Rated Blitz game"]
[Site "https://lichess.org/xxxx"]
[Date "2026.03.01"]
[White "player1"]
[Black "player2"]
[Result "1-0"]
[ECO "D06"]
[Opening "Queen's Gambit"]

1. d4 d5 2. c4 ...
```

What is directly useful for your dataset:

- `Opening`
- `ECO`
- move sequence
- side to move
- resulting board state at any ply

## 2. Extract a small usable sample first

Extract 10,000 complete games without full decompression:

```bash
python scripts/extract_lichess_pgn_sample.py \
  --input-zst raw_data/chess/lichess_db_standard_rated_2026-03.pgn.zst \
  --output raw_data/chess/samples/sample_10000_games.pgn \
  --max-games 10000
```

Extract only target openings:

```bash
python scripts/extract_lichess_pgn_sample.py \
  --input-zst raw_data/chess/lichess_db_standard_rated_2026-03.pgn.zst \
  --output raw_data/chess/samples/opening_sample.pgn \
  --max-games 2000 \
  --opening "Polish Opening" \
  --opening "Queen's Gambit"
```

This is the best starting point because:

- no full decompression is required
- output is small enough to inspect
- it already matches your `opening` task family

## 3. Map PGN to your current chess task types

Your current chess tasks are:

- opening-state editing
- legal-move highlight
- best-move drawing

These can all be constructed from PGN/FEN plus a board renderer.

### 3.1 Opening-state editing

Current pattern:

- instruction: `Edit the chess diagram to show the Polish Opening.`
- `editing`: plain board or earlier board state
- `gt`: board after the opening moves are applied

Automatic construction:

1. read a PGN with `Opening = X`
2. take the move prefix that defines the opening
3. render:
   - `editing`: initial board
   - `gt`: board after the opening sequence
4. instruction template:
   - `Edit the chess diagram to show the {Opening}.`

Examples:

- `Polish Opening`
- `Queen's Gambit`

This is the cleanest and easiest scale-up mode.

### 3.2 Legal-move highlight

Current pattern:

- instruction: `Highlight the squares the queen can move to.`
- `editing`: current board
- `gt`: same board with legal destination squares highlighted

Automatic construction:

1. sample a board position from a PGN
2. choose one piece that has a non-trivial number of legal moves
3. compute legal destinations
4. render:
   - `editing`: plain board
   - `gt`: board with target squares highlighted
5. instruction template:
   - `Highlight the squares the {piece_name} can move to.`

Good piece types:

- queen
- knight
- rook
- bishop

This is also easy because the label is fully rule-based.

### 3.3 Best-move drawing

Current pattern:

- instruction: `Draw Black's best move for the next turn.`
- `editing`: current board
- `gt`: same board with best move drawn

Automatic construction:

1. sample a board position from a PGN
2. run an engine such as Stockfish
3. keep positions where the engine best move is stable and clear
4. render:
   - `editing`: plain board
   - `gt`: board with arrow or move marker
5. instruction template:
   - `Draw {side}'s best move for the next turn.`

This is slightly harder than the first two because it needs engine analysis.

## 4. Recommended directory layout

To match your current project style:

```text
chess_lichess/
  chess_lichess.json
  chess_lichess/
    editing/
      1_before.png
      2_before.png
      ...
    gt/
      1_after.png
      2_after.png
      ...
```

JSON schema:

```json
[
  {
    "text": "Edit the chess diagram to show the Polish Opening.",
    "task_id": "task_1",
    "image_path": "chess_lichess/editing/1_before.png",
    "gt": "chess_lichess/gt/1_after.png",
    "sub_task": "Chess"
  }
]
```

## 5. What renderer is needed

At minimum you need one `chessboard renderer` with:

- fixed board style
- fixed piece sprites
- optional square highlight layer
- optional arrow layer
- output size control

From your current examples:

- opening-edit images are `720 x 720`
- legal-move highlight examples are `1328 x 1328`

The easiest path is to standardize one resolution first, for example:

- `720 x 720` for opening-state editing
- `1328 x 1328` for highlight tasks

## 6. Minimal practical pipeline

### Phase A: opening-state editing first

This should be first because it is the lowest-risk mode.

Pipeline:

1. extract PGNs for target openings
2. parse move list
3. render initial board as `editing`
4. render board after opening sequence as `gt`
5. generate instruction from opening name
6. write JSON rows

### Phase B: legal-move highlight

Pipeline:

1. sample positions
2. pick a target piece
3. compute legal moves
4. render board without highlight as `editing`
5. render board with highlighted destination squares as `gt`
6. generate instruction from piece type

### Phase C: best-move drawing

Pipeline:

1. sample positions
2. run engine
3. filter to unambiguous positions
4. render plain board as `editing`
5. render best-move arrow or marker as `gt`
6. generate instruction from side to move

## 7. Bottom line

Yes, the Lichess `.pgn.zst` file can be directly turned into your image-editing data.

The most practical order is:

1. inspect compressed PGN directly
2. extract a small PGN sample without full decompression
3. build `opening-state editing` first
4. then add `legal-move highlight`
5. then add `best-move drawing`

If you want to start immediately, the fastest next command is:

```bash
python scripts/extract_lichess_pgn_sample.py \
  --input-zst raw_data/chess/lichess_db_standard_rated_2026-03.pgn.zst \
  --output raw_data/chess/samples/opening_sample.pgn \
  --max-games 2000 \
  --opening "Polish Opening" \
  --opening "Queen's Gambit"
```
