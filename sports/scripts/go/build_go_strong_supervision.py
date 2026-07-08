#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
from collections import Counter, deque
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='使用 KataGo analysis 对 Go 候选局面做强监督重标注。')
    parser.add_argument('--input-jsonl', required=True, help='parse_katago_sgf.py 生成的候选 JSONL。')
    parser.add_argument('--output-jsonl', required=True)
    parser.add_argument('--engine', required=True, help='KataGo 可执行文件路径。')
    parser.add_argument('--model', required=True, help='KataGo 模型文件路径，通常为 .bin.gz。')
    parser.add_argument('--config', required=True, help='KataGo analysis 配置文件路径，例如 analysis_example.cfg。')
    parser.add_argument('--max-samples', type=int, default=0, help='最多处理多少条候选样本，0 表示不限。')
    parser.add_argument('--max-visits', type=int, default=256)
    parser.add_argument('--analysis-pv-len', type=int, default=12)
    parser.add_argument('--min-top-visits', type=int, default=32)
    parser.add_argument('--min-score-gap', type=float, default=1.5, help='top1 和 top2 的最小 scoreLead 差值。')
    parser.add_argument('--min-winrate-gap', type=float, default=0.03, help='top1 和 top2 的最小 winrate 差值。')
    parser.add_argument('--max-abs-score-lead', type=float, default=15.0, help='过滤已经明显一边倒的局面。<=0 表示关闭。')
    parser.add_argument('--default-rules', default='chinese')
    parser.add_argument('--default-komi', type=float, default=7.5)
    parser.add_argument('--allow-pass', action='store_true')
    parser.add_argument('--engine-log', default='', help='可选。把 KataGo stderr 同步写入这个日志文件。')
    parser.add_argument('--disable-appimage-extract-and-run', action='store_true', help='默认会为 Linux AppImage 版 KataGo 设置 APPIMAGE_EXTRACT_AND_RUN=1；传此参数可关闭。')
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open('r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            record.setdefault('meta', {})
            record['_line_no'] = line_no
            records.append(record)
    return records


def normalize_color(color: str | None) -> str:
    token = (color or '').strip().upper()
    if token in {'B', 'BLACK'}:
        return 'B'
    if token in {'W', 'WHITE'}:
        return 'W'
    raise ValueError(f'Unsupported color token: {color!r}')


def normalize_rules(value: str | None, default_rules: str) -> str:
    token = (value or '').strip().lower()
    if not token:
        return default_rules
    if 'chinese' in token:
        return 'chinese'
    if 'japanese' in token:
        return 'japanese'
    if token == 'aga' or 'american go association' in token:
        return 'aga'
    if 'korean' in token:
        return 'korean'
    if 'new zealand' in token:
        return 'new-zealand'
    if 'tromp' in token or 'taylor' in token:
        return 'tromp-taylor'
    return default_rules


def parse_komi(value: Any, default_komi: float) -> float:
    if value in (None, ''):
        return default_komi
    return float(value)


class KataGoAnalysisEngine:
    def __init__(self, engine_path: str, model_path: str, config_path: str, engine_log: str = '', use_appimage_extract_and_run: bool = True):
        self.command = [engine_path, 'analysis', '-model', model_path, '-config', config_path]
        self.stderr_tail: deque[str] = deque(maxlen=200)
        self.stderr_lock = threading.Lock()
        self.log_fp = open(engine_log, 'a', encoding='utf-8') if engine_log else None
        env = os.environ.copy()
        if use_appimage_extract_and_run:
            env.setdefault('APPIMAGE_EXTRACT_AND_RUN', '1')
        self.proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
            env=env,
        )
        self.counter = 0
        self.stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self.stderr_thread.start()
        time.sleep(0.2)
        if self.proc.poll() is not None:
            raise RuntimeError(self._format_engine_failure('KataGo analysis 启动失败'))

    def _drain_stderr(self) -> None:
        if self.proc.stderr is None:
            return
        for line in self.proc.stderr:
            with self.stderr_lock:
                self.stderr_tail.append(line.rstrip('\n'))
            if self.log_fp is not None:
                self.log_fp.write(line)
                self.log_fp.flush()

    def _stderr_excerpt(self) -> str:
        with self.stderr_lock:
            lines = list(self.stderr_tail)
        if not lines:
            return '(stderr 为空，可能是动态库/驱动层直接失败，或没有输出任何错误信息)'
        return '\n'.join(lines[-20:])

    def _format_engine_failure(self, prefix: str) -> str:
        return f"{prefix}\ncommand: {' '.join(self.command)}\nstderr:\n{self._stderr_excerpt()}"

    def query(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError('KataGo process pipes are not available.')
        if self.proc.poll() is not None:
            raise RuntimeError(self._format_engine_failure('KataGo analysis 在发送 query 前已退出'))
        self.counter += 1
        query_id = f'q_{self.counter}'
        payload = dict(payload)
        payload['id'] = query_id
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + '\n')
        self.proc.stdin.flush()

        while True:
            line = self.proc.stdout.readline()
            if line == '':
                raise RuntimeError(self._format_engine_failure('KataGo analysis engine terminated unexpectedly'))
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get('id') != query_id:
                continue
            if message.get('isDuringSearch'):
                continue
            return message

    def close(self) -> None:
        if self.proc.stdin is not None and not self.proc.stdin.closed:
            self.proc.stdin.close()
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        if self.log_fp is not None:
            self.log_fp.close()


def build_query(record: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    meta = record.get('meta', {})
    size = int(record.get('size', 19))
    to_play = normalize_color(record.get('to_play'))
    rules = normalize_rules(meta.get('rules'), args.default_rules)
    komi = parse_komi(meta.get('komi'), args.default_komi)

    moves_history = []
    for item in meta.get('moves_gtp_history', []):
        if not isinstance(item, list) or len(item) != 2:
            continue
        color = normalize_color(item[0])
        move = str(item[1]).strip()
        moves_history.append([color, 'pass' if move.lower() == 'pass' else move.upper()])

    initial_stones: list[list[str]] = []
    initial_black = meta.get('initial_black_stones') or []
    initial_white = meta.get('initial_white_stones') or []

    # If we have real move history, do not also seed the current board as initial stones,
    # otherwise KataGo will see duplicated moves and reject the query as illegal.
    if initial_black or initial_white:
        initial_stones.extend([['B', str(coord).upper()] for coord in initial_black])
        initial_stones.extend([['W', str(coord).upper()] for coord in initial_white])
    elif not moves_history:
        initial_stones.extend([['B', str(coord).upper()] for coord in record.get('black_stones', [])])
        initial_stones.extend([['W', str(coord).upper()] for coord in record.get('white_stones', [])])

    if moves_history:
        initial_player = moves_history[0][0]
    else:
        initial_player = to_play

    return {
        'rules': rules,
        'komi': komi,
        'boardXSize': size,
        'boardYSize': size,
        'maxVisits': args.max_visits,
        'analysisPVLen': args.analysis_pv_len,
        'includeOwnership': False,
        'initialPlayer': initial_player,
        'initialStones': initial_stones,
        'moves': moves_history,
    }


def compact_move_info(info: dict[str, Any]) -> dict[str, Any]:
    return {
        'move': info.get('move'),
        'order': info.get('order'),
        'visits': info.get('visits'),
        'winrate': info.get('winrate'),
        'scoreLead': info.get('scoreLead'),
        'pv': info.get('pv', []),
    }


def passes_thresholds(best: dict[str, Any], second: dict[str, Any], args: argparse.Namespace) -> tuple[bool, str, float, float]:
    best_visits = int(best.get('visits', 0) or 0)
    if best_visits < args.min_top_visits:
        return False, 'top_visits_too_low', 0.0, 0.0

    best_score = float(best.get('scoreLead', 0.0) or 0.0)
    second_score = float(second.get('scoreLead', 0.0) or 0.0)
    best_winrate = float(best.get('winrate', 0.0) or 0.0)
    second_winrate = float(second.get('winrate', 0.0) or 0.0)

    score_gap = abs(best_score - second_score)
    winrate_gap = abs(best_winrate - second_winrate)

    if args.min_score_gap > 0 and score_gap < args.min_score_gap:
        return False, 'score_gap_too_small', score_gap, winrate_gap
    if args.min_winrate_gap > 0 and winrate_gap < args.min_winrate_gap:
        return False, 'winrate_gap_too_small', score_gap, winrate_gap
    if args.max_abs_score_lead > 0 and abs(best_score) > args.max_abs_score_lead:
        return False, 'position_too_one_sided', score_gap, winrate_gap
    return True, 'ok', score_gap, winrate_gap


def relabel_record(record: dict[str, Any], query: dict[str, Any], response: dict[str, Any], args: argparse.Namespace) -> tuple[dict[str, Any] | None, str]:
    if 'error' in response:
        field = response.get('field')
        detail = response['error'] if field is None else f"{response['error']} (field={field})"
        raise RuntimeError(f"KataGo response error: {detail}")
    if 'warning' in response:
        field = response.get('field')
        detail = response['warning'] if field is None else f"{response['warning']} (field={field})"
        print(f"[warn] {record.get('source_id', '')}: KataGo response warning: {detail}")
    move_infos = sorted(response.get('moveInfos', []), key=lambda item: item.get('order', 10**9))
    if len(move_infos) < 2:
        return None, 'too_few_move_infos'

    best = move_infos[0]
    second = move_infos[1]
    best_move = str(best.get('move', '')).strip()
    if not best_move:
        return None, 'empty_best_move'
    if best_move.lower() == 'pass' and not args.allow_pass:
        return None, 'best_move_is_pass'

    keep, reason, score_gap, winrate_gap = passes_thresholds(best, second, args)
    if not keep:
        return None, reason

    updated = dict(record)
    updated['answer'] = 'pass' if best_move.lower() == 'pass' else best_move.upper()

    meta = dict(record.get('meta', {}))
    meta.update(
        {
            'weak_answer': record.get('answer'),
            'engine_name': 'KataGo',
            'engine_best_move': updated['answer'],
            'engine_rules': query.get('rules'),
            'engine_komi': query.get('komi'),
            'engine_max_visits': query.get('maxVisits'),
            'engine_score_lead': best.get('scoreLead'),
            'engine_winrate': best.get('winrate'),
            'engine_score_gap': score_gap,
            'engine_winrate_gap': winrate_gap,
            'engine_top2': [compact_move_info(best), compact_move_info(second)],
        }
    )
    updated['meta'] = meta
    updated.pop('_line_no', None)
    return updated, 'ok'


def main() -> int:
    args = parse_args()
    records = load_jsonl(Path(args.input_jsonl))
    if args.max_samples > 0:
        records = records[: args.max_samples]
    if not records:
        raise SystemExit('No candidate records found.')

    output_path = Path(args.output_jsonl)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    kept = 0
    skipped = 0
    reject_reasons: Counter[str] = Counter()
    engine = KataGoAnalysisEngine(
        args.engine,
        args.model,
        args.config,
        engine_log=args.engine_log,
        use_appimage_extract_and_run=not args.disable_appimage_extract_and_run,
    )
    try:
        with output_path.open('w', encoding='utf-8') as f:
            for index, record in enumerate(records, start=1):
                try:
                    query = build_query(record, args)
                    response = engine.query(query)
                    updated, reason = relabel_record(record, query, response, args)
                except Exception as exc:
                    skipped += 1
                    reject_reasons['engine_or_query_error'] += 1
                    print(f'[skip] {record.get("source_id", index)}: {exc}')
                    continue

                if updated is None:
                    skipped += 1
                    reject_reasons[reason] += 1
                    continue

                f.write(json.dumps(updated, ensure_ascii=False) + '\n')
                kept += 1

    finally:
        engine.close()

    if kept == 0:
        if reject_reasons:
            summary = ', '.join(f'{key}={value}' for key, value in reject_reasons.most_common())
            raise SystemExit(f'No strong-supervision records passed the filters. Reasons: {summary}')
        raise SystemExit('No strong-supervision records passed the filters.')

    summary = ', '.join(f'{key}={value}' for key, value in reject_reasons.most_common()) if reject_reasons else 'none'
    print(f'Wrote {kept} strong-supervision Go records to {output_path}. Skipped {skipped}. Reject reasons: {summary}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
