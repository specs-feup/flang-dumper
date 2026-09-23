#!/usr/bin/env python3
"""Compare two flang-dumper JSON graphs after normalizing pointer IDs.

Only pointer IDs declared by a node's ``id`` field are rewritten. Every object
is represented as an ordered sequence of key/value pairs so attribute names,
presence, duplicate attributes, and field order remain significant.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any


class JsonObject:
    """JSON object that retains key order and duplicate keys."""

    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        self.pairs = pairs

    def get(self, name: str) -> Any:
        for key, value in self.pairs:
            if key == name:
                return value
        raise KeyError(name)


def _retain_object_order(value: Any) -> Any:
    """Convert ordinary in-memory mappings to the ordered JSON representation."""
    if isinstance(value, JsonObject):
        return JsonObject([(key, _retain_object_order(child)) for key, child in value.pairs])
    if isinstance(value, dict):
        return JsonObject([(key, _retain_object_order(child)) for key, child in value.items()])
    if isinstance(value, list):
        return [_retain_object_order(child) for child in value]
    return value


POINTER_ID = re.compile(r"0x[0-9a-fA-F]+-.+")


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return json.load(source, object_pairs_hook=JsonObject)


def _pointer_map(graph: Any) -> dict[str, str]:
    if not isinstance(graph, JsonObject):
        raise ValueError("graph root must be a JSON object")
    try:
        nodes = graph.get("nodes")
    except KeyError as error:
        raise ValueError("graph root is missing the 'nodes' array") from error
    if not isinstance(nodes, list):
        raise ValueError("graph 'nodes' field must be an array")

    mapping: dict[str, str] = {}
    for node_index, node in enumerate(nodes):
        if not isinstance(node, JsonObject):
            raise ValueError(f"nodes[{node_index}] must be an object")
        try:
            node_id = node.get("id")
        except KeyError as error:
            raise ValueError(f"nodes[{node_index}] is missing its 'id' field") from error
        if not isinstance(node_id, str):
            raise ValueError(f"nodes[{node_index}].id must be a string")
        if not POINTER_ID.fullmatch(node_id):
            raise ValueError(f"nodes[{node_index}].id is not a pointer-derived ID: {node_id!r}")
        if node_id in mapping:
            raise ValueError(f"nodes[{node_index}] repeats node ID {node_id!r}")
        mapping[node_id] = f"@node{len(mapping)}"
    return mapping


def normalize_graph(graph: Any) -> tuple[Any, dict[str, str]]:
    """Return an order-preserving canonical form and the original ID mapping."""
    graph = _retain_object_order(graph)
    mapping = _pointer_map(graph)

    def normalize(value: Any) -> Any:
        if isinstance(value, JsonObject):
            return ("object", tuple((key, normalize(child)) for key, child in value.pairs))
        if isinstance(value, list):
            return ("array", tuple(normalize(child) for child in value))
        if isinstance(value, str):
            return ("string", mapping.get(value, value))
        if value is None:
            return ("null",)
        if isinstance(value, bool):
            return ("boolean", value)
        if isinstance(value, (int, float)):
            return ("number", value)
        raise ValueError(f"unsupported JSON value: {type(value).__name__}")

    return normalize(graph), mapping


def compare_graphs(left: Any, right: Any) -> bool:
    """Compare JSON graph objects, ignoring only process-specific pointer IDs."""
    left_normalized, _ = normalize_graph(left)
    right_normalized, _ = normalize_graph(right)
    return left_normalized == right_normalized


def _display_normalized(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expected", type=Path)
    parser.add_argument("actual", type=Path)
    args = parser.parse_args(argv)
    try:
        expected, expected_map = normalize_graph(_load(args.expected))
        actual, actual_map = normalize_graph(_load(args.actual))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"graph comparison error: {error}", file=sys.stderr)
        return 2

    if expected == actual:
        print("graphs match after pointer ID normalization")
        return 0

    print("graphs differ after pointer ID normalization", file=sys.stderr)
    diff = difflib.unified_diff(
        _display_normalized(expected).splitlines(),
        _display_normalized(actual).splitlines(),
        fromfile=str(args.expected),
        tofile=str(args.actual),
        lineterm="",
    )
    for line in list(diff)[:80]:
        print(line, file=sys.stderr)
    if len(expected_map) != len(actual_map):
        print(
            f"normalized node counts: expected={len(expected_map)}, actual={len(actual_map)}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
