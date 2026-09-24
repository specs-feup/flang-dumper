#!/usr/bin/env python3
"""Extract explicit dump-handler bodies for migration review.

This produces a review artifact from existing DUMP_NODE and
DUMP_NODE_MANUAL registrations. It is not consumed by the runtime generator.
"""

from __future__ import annotations

import argparse
import bisect
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Iterator


FORMAT = "flang-handler-bodies/v1"
NODE_MACROS = {"DUMP_NODE", "DUMP_NODE_MANUAL"}


def _load_inventory_parser():
    parser_path = Path(__file__).resolve().parents[1] / "scripts" / "inventory_dump_handlers.py"
    spec = importlib.util.spec_from_file_location("inventory_dump_handlers", parser_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load registration parser at {parser_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PARSER = _load_inventory_parser()


class ExtractionError(ValueError):
    """An invalid source or registration inventory."""


def _line_number(line_starts: list[int], offset: int) -> int:
    return bisect.bisect_right(line_starts, offset)


def _macro_invocations(source: str) -> Iterator[dict[str, Any]]:
    """Yield node registrations and their raw CONTENTS argument."""
    cursor = 0
    line_starts = [0]
    line_starts.extend(index + 1 for index, char in enumerate(source) if char == "\n")

    while cursor < len(source):
        skipped = _PARSER._skip_quoted_or_comment(source, cursor)
        if skipped is not None:
            cursor = skipped
            continue

        if cursor > 0 and source[cursor - 1] in _PARSER.IDENTIFIER_CHARS:
            cursor += 1
            continue
        macro = next(
            (
                candidate
                for candidate in ("DUMP_NODE_MANUAL", "DUMP_NODE", "DUMP_ENUM")
                if source.startswith(candidate, cursor)
                and cursor + len(candidate) < len(source)
                and source[cursor + len(candidate)] not in _PARSER.IDENTIFIER_CHARS
            ),
            None,
        )
        if macro is None:
            cursor += 1
            continue

        after_name = cursor + len(macro)
        opening = _PARSER._skip_trivia(source, after_name)
        if opening >= len(source) or source[opening] != "(":
            cursor = after_name
            continue
        closing = _PARSER._matching_parenthesis(source, opening)
        args = _PARSER._split_arguments(source, opening + 1, closing)
        if len(args) != 2:
            line = _line_number(line_starts, cursor)
            raise ExtractionError(
                f"{macro} at line {line} has {len(args)} arguments; expected 2"
            )

        if macro in NODE_MACROS:
            yield {
                "fully_qualified_type": _PARSER._normalize_type_name(args[0]),
                "registration": macro,
                "source_line": _line_number(line_starts, cursor),
                # _split_arguments strips surrounding whitespace; retain every
                # character inside the CONTENTS argument for the review artifact.
                "contents_argument": args[1],
                "has_explicit_content": _PARSER._has_explicit_content(args[1]),
            }
        cursor = closing + 1


def _inventory_candidates(document: Any) -> dict[tuple[str, str, int], dict[str, Any]]:
    if not isinstance(document, dict) or set(document) != {"schema_version", "registrations"}:
        raise ExtractionError("registration inventory must contain schema_version and registrations")
    version = document.get("schema_version")
    if isinstance(version, bool) or version != 1:
        raise ExtractionError("registration inventory schema_version must be 1")
    registrations = document.get("registrations")
    if not isinstance(registrations, list):
        raise ExtractionError("registration inventory registrations must be an array")

    candidates: dict[tuple[str, str, int], dict[str, Any]] = {}
    names: set[str] = set()
    for index, item in enumerate(registrations):
        if not isinstance(item, dict):
            raise ExtractionError(f"registrations[{index}] must be an object")
        macro = item.get("registration")
        if macro not in NODE_MACROS or item.get("has_explicit_content") is not True:
            continue
        name = item.get("fully_qualified_type")
        line = item.get("source_line")
        if not isinstance(name, str) or not name.strip():
            raise ExtractionError(f"registrations[{index}].fully_qualified_type must be a nonempty string")
        if isinstance(line, bool) or not isinstance(line, int) or line < 1:
            raise ExtractionError(f"registrations[{index}].source_line must be a positive integer")
        if name in names:
            raise ExtractionError(f"duplicate explicit-content registration for {name}")
        names.add(name)
        key = (name, macro, line)
        if key in candidates:
            raise ExtractionError(f"duplicate explicit-content registration for {name} at line {line}")
        candidates[key] = item
    return candidates


def extract_handler_bodies(source: str, inventory: Any) -> dict[str, Any]:
    """Build sorted explicit-content entries after validating the inventory."""
    expected = _inventory_candidates(inventory)
    found: dict[tuple[str, str, int], dict[str, Any]] = {}
    for invocation in _macro_invocations(source):
        if not invocation["has_explicit_content"]:
            continue
        name = invocation["fully_qualified_type"]
        key = (name, invocation["registration"], invocation["source_line"])
        if name in {candidate[0] for candidate in found}:
            raise ExtractionError(f"duplicate explicit-content registration for {name}")
        found[key] = invocation

    if len(found) != len(expected) or set(found) != set(expected):
        missing = sorted(set(expected) - set(found))
        unexpected = sorted(set(found) - set(expected))
        details = []
        if missing:
            details.append("missing from source: " + ", ".join(f"{name} ({macro}, line {line})" for name, macro, line in missing))
        if unexpected:
            details.append("missing from inventory: " + ", ".join(f"{name} ({macro}, line {line})" for name, macro, line in unexpected))
        raise ExtractionError(
            f"explicit-content registration count mismatch: source has {len(found)}, inventory has {len(expected)}"
            + ("; " + "; ".join(details) if details else "")
        )

    handlers = []
    for key in sorted(found, key=lambda value: value[0]):
        invocation = found[key]
        contents = invocation["contents_argument"]
        if not (contents.startswith("{") and contents.endswith("}")):
            name, macro, line = key
            raise ExtractionError(
                f"{macro} for {name} at line {line} has explicit content without a braced CONTENTS block"
            )
        handlers.append(
            {
                "fully_qualified_type": invocation["fully_qualified_type"],
                "registration": invocation["registration"],
                "source_line": invocation["source_line"],
                "body": contents[1:-1].strip(),
            }
        )
    return {"format": FORMAT, "handlers": handlers}


def _read_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ExtractionError(f"could not read {description} {path}: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="plugin.cpp containing dump registrations")
    parser.add_argument("inventory", type=Path, help="registration inventory JSON")
    parser.add_argument("-o", "--output", required=True, type=Path, help="handler bodies JSON path")
    parser.add_argument("--check", action="store_true", help="check that output is current without writing it")
    args = parser.parse_args(argv)

    try:
        source = args.source.read_text(encoding="utf-8")
        inventory = _read_json(args.inventory, "registration inventory")
        result = extract_handler_bodies(source, inventory)
        rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            try:
                actual = args.output.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                raise ExtractionError(f"could not read output {args.output}: {error}") from error
            if actual != rendered:
                raise ExtractionError(f"{args.output} is stale; regenerate it without --check")
        else:
            args.output.write_text(rendered, encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as error:
        print(f"handler body extraction error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
