#!/usr/bin/env python3
"""Compare live Flang JSON and protobuf AST graphs across a source corpus."""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path

from compare_graphs import JsonObject, compare_graphs, normalize_graph
from decode_ast_stream import _load_record_class, decode_stream


def _discover_sources(inputs: list[Path]) -> list[Path]:
    sources: set[Path] = set()
    for item in inputs:
        if not item.exists():
            raise ValueError(f"input does not exist: {item}")
        if item.is_file():
            candidates = [item]
        elif item.is_dir():
            candidates = item.rglob("*.f90")
        else:
            raise ValueError(f"input is not a file or directory: {item}")

        for candidate in candidates:
            if candidate.name.endswith(".expected.f90"):
                continue
            if candidate.suffix != ".f90":
                if item.is_file():
                    raise ValueError(f"source file must have a .f90 suffix: {item}")
                continue
            sources.add(candidate.resolve())
    return sorted(sources, key=lambda path: path.as_posix())


def _label(source: Path) -> str:
    try:
        return source.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return str(source)


def _run(command: list[str]) -> subprocess.CompletedProcess[bytes] | OSError:
    try:
        return subprocess.run(command, capture_output=True, check=False)
    except OSError as error:
        return error


def _load_json_graph(data: bytes, source: str) -> JsonObject:
    try:
        text = data.decode("utf-8")
        graph = json.loads(text, object_pairs_hook=JsonObject)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{source}: invalid JSON output: {error}") from error
    if not isinstance(graph, JsonObject):
        raise ValueError(f"{source}: graph root must be a JSON object")
    try:
        nodes = graph.get("nodes")
        comments = graph.get("comments")
        enums = graph.get("enums")
    except KeyError as error:
        raise ValueError(f"{source}: graph is missing {error.args[0]!r}") from error
    if not isinstance(nodes, list):
        raise ValueError(f"{source}: graph 'nodes' field must be an array")
    if not isinstance(comments, list):
        raise ValueError(f"{source}: graph 'comments' field must be an array")
    if not isinstance(enums, JsonObject):
        raise ValueError(f"{source}: graph 'enums' field must be an object")
    try:
        normalize_graph(graph)
    except ValueError as error:
        raise ValueError(f"{source}: invalid graph: {error}") from error
    return graph


def _print_stderr(label: str, side: str, data: bytes) -> None:
    if not data:
        return
    text = data.decode("utf-8", errors="replace")
    print(f"{label}: {side} stderr:", file=sys.stderr)
    print(text, file=sys.stderr, end="" if text.endswith("\n") else "\n")


def _command(flang: Path, plugin: Path, action: str, source: Path) -> list[str]:
    return [
        str(flang),
        "-fc1",
        "-fopenmp",
        "-load",
        str(plugin),
        "-plugin",
        action,
        str(source),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flang", required=True, type=Path, help="Flang executable")
    parser.add_argument("--json-plugin", required=True, type=Path, help="JSON plugin library")
    parser.add_argument("--binary-plugin", required=True, type=Path, help="protobuf plugin library")
    parser.add_argument("--protoc", required=True, type=Path, help="protoc executable")
    parser.add_argument("sources", nargs="+", type=Path, help="source files or directories")
    args = parser.parse_args(argv)

    try:
        sources = _discover_sources(args.sources)
    except ValueError as error:
        parser.error(str(error))

    total = len(sources)
    baseline_clean = 0
    matched = 0
    baseline_failed = 0
    binary_failed = 0
    mismatched = 0
    record_class = None
    decoder_error = None
    if sources:
        try:
            record_class = _load_record_class(str(args.protoc))
        except Exception as error:
            decoder_error = str(error)

    for source in sources:
        label = _label(source)
        json_result = _run(_command(args.flang, args.json_plugin, "dump-ast", source))
        if isinstance(json_result, OSError):
            baseline_failed += 1
            print(f"BASELINE_FAIL {label}: could not run Flang JSON plugin: {json_result}")
            continue
        if json_result.returncode != 0:
            baseline_failed += 1
            print(f"BASELINE_FAIL {label}: JSON Flang exited with status {json_result.returncode}")
            _print_stderr(label, "JSON", json_result.stderr)
            continue

        try:
            baseline = _load_json_graph(json_result.stdout, label)
        except ValueError as error:
            baseline_failed += 1
            print(f"BASELINE_FAIL {label}: {error}")
            _print_stderr(label, "JSON", json_result.stderr)
            continue

        baseline_clean += 1
        if decoder_error is not None:
            binary_failed += 1
            print(f"BINARY_FAIL {label}: could not initialize protobuf decoder: {decoder_error}")
            continue

        binary_result = _run(
            _command(args.flang, args.binary_plugin, "dump-ast-protobuf", source)
        )
        if isinstance(binary_result, OSError):
            binary_failed += 1
            print(f"BINARY_FAIL {label}: could not run Flang protobuf plugin: {binary_result}")
            continue
        if binary_result.returncode != 0:
            binary_failed += 1
            print(
                f"BINARY_FAIL {label}: protobuf Flang exited with status "
                f"{binary_result.returncode}"
            )
            _print_stderr(label, "protobuf", binary_result.stderr)
            continue

        try:
            binary_graph = decode_stream(binary_result.stdout, record_class)
            equal = compare_graphs(baseline, binary_graph)
        except Exception as error:
            binary_failed += 1
            print(f"BINARY_FAIL {label}: protobuf graph decode or validation failed: {error}")
            _print_stderr(label, "JSON", json_result.stderr)
            _print_stderr(label, "protobuf", binary_result.stderr)
            continue

        if equal:
            matched += 1
            print(f"MATCH {label}")
        else:
            mismatched += 1
            print(f"MISMATCH {label}")
            expected, _ = normalize_graph(baseline)
            actual, _ = normalize_graph(binary_graph)
            differences = difflib.unified_diff(
                json.dumps(expected, ensure_ascii=False, indent=2).splitlines(),
                json.dumps(actual, ensure_ascii=False, indent=2).splitlines(),
                fromfile="JSON", tofile="protobuf", lineterm="",
            )
            for index, line in enumerate(differences):
                if index == 80:
                    print("... diff truncated", file=sys.stderr)
                    break
                print(line, file=sys.stderr)
            _print_stderr(label, "JSON", json_result.stderr)
            _print_stderr(label, "protobuf", binary_result.stderr)

    print(
        "summary: "
        f"total={total} baseline_clean={baseline_clean} matched={matched} "
        f"baseline_failed={baseline_failed} binary_failed={binary_failed} "
        f"mismatched={mismatched}"
    )
    return 1 if baseline_clean == 0 or binary_failed or mismatched else 0


if __name__ == "__main__":
    raise SystemExit(main())
