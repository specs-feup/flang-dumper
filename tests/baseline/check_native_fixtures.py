#!/usr/bin/env python3
"""Check native Flang JSON graph fixtures against their frozen snapshots."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from compare_graphs import JsonObject, compare_graphs


HERE = Path(__file__).resolve().parent
FIXTURES = (
    "loop_trailing_comment",
    "optional_if_else",
    "array_constructor_implied_do",
)


def _load_json(text: str, source: str) -> JsonObject:
    try:
        value = json.loads(text, object_pairs_hook=JsonObject)
    except json.JSONDecodeError as error:
        raise ValueError(f"{source}: invalid JSON: {error}") from error
    if not isinstance(value, JsonObject):
        raise ValueError(f"{source}: graph root must be a JSON object")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flang", required=True, type=Path, help="Flang 22 executable")
    parser.add_argument("--plugin", required=True, type=Path, help="DumpASTPlugin shared library")
    args = parser.parse_args(argv)

    failed = False
    for name in FIXTURES:
        fixture = HERE / "fixtures" / f"{name}.f90"
        snapshot = HERE / "snapshots" / f"{name}.json"
        command = [
            str(args.flang),
            "-fc1",
            "-fopenmp",
            "-load",
            str(args.plugin),
            "-plugin",
            "dump-ast",
            str(fixture),
        ]
        try:
            expected = _load_json(snapshot.read_text(encoding="utf-8"), str(snapshot))
        except (OSError, UnicodeError, ValueError) as error:
            print(f"{name}: {error}", file=sys.stderr)
            failed = True
            continue

        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(f"{name}: Flang exited with status {result.returncode}", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
            failed = True
            continue

        if result.stderr:
            print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")

        try:
            actual = _load_json(result.stdout, f"Flang output for {name}")
            expected_counts = _graph_counts(expected)
            actual_counts = _graph_counts(actual)
            matches = compare_graphs(expected, actual)
        except ValueError as error:
            print(f"{name}: {error}", file=sys.stderr)
            failed = True
            continue

        if not matches:
            print(f"{name}: graph differs from {snapshot}", file=sys.stderr)
            print(
                f"  expected nodes/comments/enums: {expected_counts[0]}/{expected_counts[1]}/{expected_counts[2]}",
                file=sys.stderr,
            )
            print(
                f"  actual   nodes/comments/enums: {actual_counts[0]}/{actual_counts[1]}/{actual_counts[2]}",
                file=sys.stderr,
            )
            failed = True
            continue

        print(
            f"{name}: nodes={actual_counts[0]} comments={actual_counts[1]} enums={actual_counts[2]}"
        )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
