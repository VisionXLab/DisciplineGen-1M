#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from go_utils import infer_category, row_col_to_gtp, sgf_coord_to_row_col


@dataclass
class SgfNode:
    props: dict[str, list[str]] = field(default_factory=dict)
    children: list["SgfNode"] = field(default_factory=list)

    def move(self) -> tuple[str, str] | None:
        for color in ("B", "W"):
            values = self.props.get(color, [])
            if values and values[0]:
                return color, values[0]
        return None


class SgfParser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def parse_collection(self) -> list[SgfNode]:
        trees: list[SgfNode] = []
        self._skip_ws()
        while self.pos < len(self.text):
            if self.text[self.pos] == "(":
                tree = self._parse_tree()
                if tree is not None:
                    trees.append(tree)
            else:
                self.pos += 1
            self._skip_ws()
        return trees

    def _skip_ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def _parse_tree(self) -> SgfNode | None:
        self._expect("(")
        nodes: list[SgfNode] = []
        self._skip_ws()
        while self.pos < len(self.text) and self.text[self.pos] == ";":
            nodes.append(self._parse_node())
            self._skip_ws()

        if not nodes:
            while self.pos < len(self.text) and self.text[self.pos] != ")":
                self.pos += 1
            self._expect(")")
            return None

        for idx in range(len(nodes) - 1):
            nodes[idx].children.append(nodes[idx + 1])

        last = nodes[-1]
        self._skip_ws()
        while self.pos < len(self.text) and self.text[self.pos] == "(":
            child = self._parse_tree()
            if child is not None:
                last.children.append(child)
            self._skip_ws()

        self._expect(")")
        return nodes[0]

    def _parse_node(self) -> SgfNode:
        self._expect(";")
        props: dict[str, list[str]] = {}
        self._skip_ws()
        while self.pos < len(self.text):
            if self.text[self.pos] in ";()":
                break
            if not self.text[self.pos].isalpha():
                self.pos += 1
                continue
            ident = self._parse_ident()
            values = self._parse_values()
            props[ident] = values
            self._skip_ws()
        return SgfNode(props=props)

    def _parse_ident(self) -> str:
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos].isalpha():
            self.pos += 1
        return self.text[start:self.pos]

    def _parse_values(self) -> list[str]:
        values: list[str] = []
        self._skip_ws()
        while self.pos < len(self.text) and self.text[self.pos] == "[":
            self.pos += 1
            buf: list[str] = []
            while self.pos < len(self.text):
                ch = self.text[self.pos]
                if ch == "\\" and self.pos + 1 < len(self.text):
                    buf.append(self.text[self.pos + 1])
                    self.pos += 2
                    continue
                if ch == "]":
                    self.pos += 1
                    break
                buf.append(ch)
                self.pos += 1
            values.append("".join(buf))
            self._skip_ws()
        return values

    def _expect(self, token: str) -> None:
        if self.pos >= len(self.text) or self.text[self.pos] != token:
            raise ValueError(f"Expected '{token}' at position {self.pos}")
        self.pos += 1


def comment_text(node: SgfNode) -> str:
    return " ".join(node.props.get("C", []))


def has_right_marker(node: SgfNode) -> bool:
    return "RIGHT" in comment_text(node).upper()


def root_setup(node: SgfNode, size: int) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    black = [sgf_coord_to_row_col(v, size) for v in node.props.get("AB", []) if v]
    white = [sgf_coord_to_row_col(v, size) for v in node.props.get("AW", []) if v]
    return black, white


def find_right_path(node: SgfNode, path: list[tuple[str, str]] | None = None) -> list[tuple[str, str]] | None:
    path = list(path or [])
    move = node.move()
    if move is not None:
        path.append(move)

    if has_right_marker(node):
        return path

    for child in node.children:
        result = find_right_path(child, path)
        if result:
            return result
    return None


def infer_problem_category(root: SgfNode, source_path: Path) -> str:
    texts = [
        source_path.as_posix(),
        " ".join(root.props.get("GN", [])),
        " ".join(root.props.get("EV", [])),
        " ".join(root.props.get("C", [])),
    ]
    return infer_category(*texts)


def build_text(category: str, to_play: str) -> str:
    side = "Black" if to_play == "black" else "White"
    if category == "Tesuji":
        prefix = "A Tesuji Problem"
    elif category == "Life and Death":
        prefix = "A Life and Death Problem"
    elif category == "Opening Problem":
        prefix = "An Opening Problem"
    else:
        prefix = "A Go Problem"
    return f'{prefix}: {side} to play. Please find the crucial first move and mark it with "1" on the board.'


def parse_problem(tree: SgfNode, source_path: Path, source_id: str) -> dict | None:
    size = int(tree.props.get("SZ", ["19"])[0])
    right_path = find_right_path(tree)
    if not right_path:
        return None

    first_color, first_move = right_path[0]
    answer_row, answer_col = sgf_coord_to_row_col(first_move, size)
    black_stones, white_stones = root_setup(tree, size)
    category = infer_problem_category(tree, source_path)
    to_play = "black" if first_color == "B" else "white"

    meta = {
        "raw_category": category,
        "source_path": source_path.as_posix(),
        "right_path_length": len(right_path),
        "root_comment": comment_text(tree),
    }
    if "PL" in tree.props and tree.props["PL"]:
        meta["root_pl"] = tree.props["PL"][0]

    return {
        "source_id": source_id,
        "size": size,
        "category": category,
        "to_play": to_play,
        "answer": row_col_to_gtp(answer_row, answer_col, size),
        "black_stones": [row_col_to_gtp(r, c, size) for r, c in black_stones],
        "white_stones": [row_col_to_gtp(r, c, size) for r, c in white_stones],
        "text": build_text(category, to_play),
        "meta": meta,
    }


def load_trees(path: Path) -> list[tuple[Path, SgfNode]]:
    if path.is_dir():
        targets = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in {".sgf", ".sgfs"})
    else:
        targets = [path]

    trees: list[tuple[Path, SgfNode]] = []
    for target in targets:
        text = target.read_text(encoding="utf-8", errors="replace")
        parser = SgfParser(text)
        for tree in parser.parse_collection():
            trees.append((target, tree))
    return trees


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse GoProblems-style SGF into JSONL for Go dataset building.")
    parser.add_argument("--input", required=True, help="SGF file or directory.")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--max-samples", type=int, default=0, help="0 means no limit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    records: list[dict] = []
    parsed = 0
    skipped = 0

    for idx, (source_path, tree) in enumerate(load_trees(input_path), start=1):
        source_id = f"{source_path.stem}_{idx}"
        record = parse_problem(tree, source_path, source_id)
        if record is None:
            skipped += 1
            continue
        records.append(record)
        parsed += 1
        if args.max_samples and len(records) >= args.max_samples:
            break

    if not records:
        raise SystemExit("No valid GoProblems SGF records were parsed.")

    output_path = Path(args.output_jsonl)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Parsed {parsed} GoProblems records to {output_path} (skipped {skipped})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
