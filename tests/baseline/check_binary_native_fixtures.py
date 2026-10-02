#!/usr/bin/env python3
"""Check native Flang binary graphs against the frozen JSON snapshots."""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from check_native_fixtures import FIXTURES
from compare_graphs import JsonObject, compare_graphs, normalize_graph
from decode_ast_stream import _load_record_class, decode_stream


HERE = Path(__file__).resolve().parent


def _load_json(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=JsonObject)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: could not load snapshot: {error}") from error
    if not isinstance(value, JsonObject):
        raise ValueError(f"{path}: graph root must be a JSON object")
    return value


def _graph_counts(graph: JsonObject) -> tuple[int, int, int]:
    try:
        nodes = graph.get("nodes")
        comments = graph.get("comments")
        enums = graph.get("enums")
    except KeyError as error:
        raise ValueError(f"graph is missing {error.args[0]!r}") from error
    if not isinstance(nodes, list):
        raise ValueError("graph 'nodes' field must be an array")
    if not isinstance(comments, list):
        raise ValueError("graph 'comments' field must be an array")
    if not isinstance(enums, JsonObject):
        raise ValueError("graph 'enums' field must be an object")
    return len(nodes), len(comments), len(enums.pairs)


def _normalized_text(graph: Any) -> str:
    normalized, _ = normalize_graph(graph)
    return json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"


def _report_difference(name: str, snapshot: Path, expected: Any, actual: Any) -> None:
    print(f"{name}: graph differs from {snapshot}", file=sys.stderr)
    diff = list(
        difflib.unified_diff(
            _normalized_text(expected).splitlines(),
            _normalized_text(actual).splitlines(),
            fromfile=str(snapshot),
            tofile=f"decoded binary graph for {name}",
            lineterm="",
        )
    )
    for line in diff[:80]:
        print(line, file=sys.stderr)
    if len(diff) > 80:
        print("... diff truncated after 80 lines", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flang", required=True, type=Path, help="Flang 22 executable")
    parser.add_argument("--plugin", required=True, type=Path, help="DumpASTPlugin shared library")
    parser.add_argument("--protoc", required=True, type=Path, help="protoc executable")
    args = parser.parse_args(argv)

    try:
        record_class = _load_record_class(str(args.protoc))
    except Exception as error:
        print(f"could not initialize AST stream decoder: {error}", file=sys.stderr)
        return 1

    failed = False
    for name in FIXTURES:
        fixture = HERE / "fixtures" / f"{name}.f90"
        snapshot = HERE / "snapshots" / f"{name}.json"
        try:
            expected = _load_json(snapshot)
        except ValueError as error:
            print(f"{name}: {error}", file=sys.stderr)
            failed = True
            continue

        command = [
            str(args.flang),
            "-fc1",
            "-fopenmp",
            "-load",
            str(args.plugin),
            "-plugin",
            "dump-ast-protobuf",
            str(fixture),
        ]
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, check=False)
        except OSError as error:
            print(f"{name}: could not run Flang: {error}", file=sys.stderr)
            failed = True
            continue

        if result.returncode != 0:
            print(f"{name}: Flang exited with status {result.returncode}", file=sys.stderr)
            failed = True
            continue

        try:
            actual = decode_stream(result.stdout, record_class)
            actual_counts = _graph_counts(actual)
        except Exception as error:
            print(f"{name}: AST stream decode failed: {error}", file=sys.stderr)
            failed = True
            continue

        print(
            f"{name}: nodes={actual_counts[0]} comments={actual_counts[1]} enums={actual_counts[2]}"
        )

        try:
            expected_counts = _graph_counts(expected)
            matches = compare_graphs(expected, actual)
        except ValueError as error:
            print(f"{name}: graph comparison failed: {error}", file=sys.stderr)
            failed = True
            continue

        if not matches:
            print(
                f"{name}: expected nodes/comments/enums: "
                f"{expected_counts[0]}/{expected_counts[1]}/{expected_counts[2]}",
                file=sys.stderr,
            )
            print(
                f"{name}: actual   nodes/comments/enums: "
                f"{actual_counts[0]}/{actual_counts[1]}/{actual_counts[2]}",
                file=sys.stderr,
            )
            try:
                _report_difference(name, snapshot, expected, actual)
            except ValueError as error:
                print(f"{name}: could not format graph difference: {error}", file=sys.stderr)
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
