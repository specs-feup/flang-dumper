#!/usr/bin/env python3
"""Build or check the pinned Flang 22 declaration inventory."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence


GENERATOR_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = GENERATOR_DIR / "flang22-declarations.json"
HEADER_FILTERS = (
    ("flang/Parser/parse-tree.h", "Fortran::parser"),
    ("flang/Support/Fortran.h", "Fortran::common"),
    ("flang/Parser/format-specification.h", "Fortran::format"),
)


def _load_sibling_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load generator module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ANALYZER = _load_sibling_module("flang22_analyze_clang", GENERATOR_DIR / "analyze_clang.py")
MERGER = _load_sibling_module("flang22_merge_inventories", GENERATOR_DIR / "merge_inventories.py")


def build_model(*, header_root: Path, include_dir: Path, clang_command: str) -> dict[str, Any]:
    """Analyze the pinned headers in merge-priority order and combine them."""
    inventories: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="flang22-declarations-") as temporary:
        temporary_dir = Path(temporary)
        for index, (relative_header, ast_filter) in enumerate(HEADER_FILTERS):
            inventories.append(
                ANALYZER.analyze(
                    header=include_dir / relative_header,
                    header_root=header_root,
                    output=temporary_dir / f"inventory-{index}.json",
                    compiler=clang_command,
                    include_dirs=[include_dir],
                    ast_filter=ast_filter,
                    qualified_prefix="Fortran",
                )
            )
    return MERGER.merge_inventories(inventories)


def serialize_model(model: dict[str, Any]) -> str:
    return json.dumps(model, ensure_ascii=False, indent=2) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--header-root", type=Path, required=True)
    parser.add_argument("--include-dir", type=Path, required=True)
    parser.add_argument("--clang-command", default="clang++-21")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="fail if output differs from the generated model")
    args = parser.parse_args(argv)

    try:
        model = build_model(
            header_root=args.header_root,
            include_dir=args.include_dir,
            clang_command=args.clang_command,
        )
        serialized = serialize_model(model)
        if args.check:
            try:
                existing = args.output.read_text(encoding="utf-8")
            except OSError as error:
                print(f"Flang 22 model check failed: cannot read {args.output}: {error}", file=sys.stderr)
                return 1
            if existing != serialized:
                print(f"Flang 22 declaration model is out of date: {args.output}", file=sys.stderr)
                return 1
            print(f"Flang 22 declaration model is current ({len(model['declarations'])} declarations)")
            return 0

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8", newline="\n")
        print(f"Wrote {len(model['declarations'])} declarations to {args.output.resolve()}")
        return 0
    except (ANALYZER.AnalyzerError, MERGER.MergeError, OSError, RuntimeError) as error:
        print(f"Flang 22 model error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
