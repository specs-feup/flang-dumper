#!/usr/bin/env python3
"""Extract DUMP_NODE, DUMP_NODE_MANUAL, and DUMP_ENUM registrations.

The scanner is deliberately small: it handles C/C++ comments and literals, and
balances delimiters before reading macro arguments. It does not try to parse
arbitrary C++ expressions.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


MACROS = ("DUMP_NODE_MANUAL", "DUMP_NODE", "DUMP_ENUM")
IDENTIFIER_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def _raw_string_end(source: str, index: int) -> int | None:
    """Return the end offset of a raw string beginning at *index*, if any."""
    match = re.match(r'(?:u8|u|U|L)?R"([^ ()\\\t\r\n]{0,16})\(', source[index:])
    if not match:
        return None
    delimiter = match.group(1)
    content_start = index + match.end()
    closing = ")" + delimiter + '"'
    close_at = source.find(closing, content_start)
    if close_at < 0:
        raise ValueError(f"unterminated raw string literal at offset {index}")
    return close_at + len(closing)


def _skip_quoted_or_comment(source: str, index: int) -> int | None:
    """Skip one literal/comment at *index*, or return None if none starts."""
    raw_end = _raw_string_end(source, index)
    if raw_end is not None:
        return raw_end

    if source.startswith("//", index):
        newline = source.find("\n", index + 2)
        return len(source) if newline < 0 else newline + 1
    if source.startswith("/*", index):
        close_at = source.find("*/", index + 2)
        if close_at < 0:
            raise ValueError(f"unterminated block comment at offset {index}")
        return close_at + 2
    if source[index] not in "\"'":
        return None

    quote = source[index]
    cursor = index + 1
    while cursor < len(source):
        if source[cursor] == "\\":
            cursor += 2
        elif source[cursor] == quote:
            return cursor + 1
        else:
            cursor += 1
    raise ValueError(f"unterminated quoted literal at offset {index}")


def _skip_trivia(source: str, index: int) -> int:
    while index < len(source):
        if source[index].isspace():
            index += 1
            continue
        skipped = _skip_quoted_or_comment(source, index)
        if skipped is not None and source.startswith(("//", "/*"), index):
            index = skipped
            continue
        return index
    return index


def _matching_parenthesis(source: str, opening: int) -> int:
    """Return the offset of the matching ')' for source[opening] == '('."""
    depth = 1
    cursor = opening + 1
    while cursor < len(source):
        skipped = _skip_quoted_or_comment(source, cursor)
        if skipped is not None:
            cursor = skipped
            continue
        char = source[cursor]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return cursor
        cursor += 1
    raise ValueError(f"unclosed macro invocation at offset {opening - 1}")


def _split_arguments(source: str, start: int, end: int) -> list[str]:
    """Split a macro argument list, respecting nested C++ delimiters."""
    args: list[str] = []
    cursor = start
    arg_start = start
    stack: list[str] = []
    pairs = {")": "(", "}": "{", "]": "["}
    while cursor < end:
        skipped = _skip_quoted_or_comment(source, cursor)
        if skipped is not None:
            cursor = skipped
            continue
        char = source[cursor]
        if char in "({[":
            stack.append(char)
        elif char in ")}]":
            if stack and stack[-1] == pairs[char]:
                stack.pop()
        elif char == "," and not stack:
            args.append(source[arg_start:cursor].strip())
            arg_start = cursor + 1
        cursor += 1
    args.append(source[arg_start:end].strip())
    return args


def _without_comments(text: str) -> str:
    """Remove comments while leaving quoted text intact."""
    pieces: list[str] = []
    cursor = 0
    while cursor < len(text):
        skipped = _skip_quoted_or_comment(text, cursor)
        if skipped is None:
            pieces.append(text[cursor])
            cursor += 1
            continue
        if text.startswith(("//", "/*"), cursor):
            pieces.append(" ")
        else:
            pieces.append(text[cursor:skipped])
        cursor = skipped
    return "".join(pieces)


def _has_explicit_content(argument: str) -> bool:
    contents = _without_comments(argument).strip()
    if contents.startswith("{") and contents.endswith("}"):
        contents = contents[1:-1]
    return bool(contents.strip())


def _normalize_type_name(type_name: str) -> str:
    type_name = re.sub(r"\s*::\s*", "::", type_name.strip())
    type_name = re.sub(r"\s*([<>,*&])\s*", r"\1", type_name)
    return re.sub(r"\s+", " ", type_name)


def parse_registrations(source: str) -> list[dict[str, object]]:
    """Return registrations in source order, with 1-based source lines."""
    registrations: list[dict[str, object]] = []
    cursor = 0
    while cursor < len(source):
        skipped = _skip_quoted_or_comment(source, cursor)
        if skipped is not None:
            cursor = skipped
            continue

        if cursor > 0 and source[cursor - 1] in IDENTIFIER_CHARS:
            cursor += 1
            continue
        macro = next(
            (
                candidate
                for candidate in MACROS
                if source.startswith(candidate, cursor)
                and cursor + len(candidate) < len(source)
                and source[cursor + len(candidate)] not in IDENTIFIER_CHARS
            ),
            None,
        )
        if macro is None:
            cursor += 1
            continue

        after_name = cursor + len(macro)
        opening = _skip_trivia(source, after_name)
        if opening >= len(source) or source[opening] != "(":
            cursor = after_name
            continue
        closing = _matching_parenthesis(source, opening)
        args = _split_arguments(source, opening + 1, closing)
        if len(args) != 2:
            line = source.count("\n", 0, cursor) + 1
            raise ValueError(
                f"{macro} at line {line} has {len(args)} arguments; expected 2"
            )

        if macro == "DUMP_ENUM":
            type_name = _normalize_type_name(f"{args[0]}::{args[1]}")
            handler_kind = "enum"
            manual = False
            explicit_content = False
        else:
            type_name = _normalize_type_name(args[0])
            handler_kind = "manual_node" if macro == "DUMP_NODE_MANUAL" else "node"
            manual = macro == "DUMP_NODE_MANUAL"
            explicit_content = _has_explicit_content(args[1])

        registrations.append(
            {
                "fully_qualified_type": type_name,
                "registration": macro,
                "handler_kind": handler_kind,
                "source_line": source.count("\n", 0, cursor) + 1,
                "manual": manual,
                "has_explicit_content": explicit_content,
            }
        )
        cursor = closing + 1
    return registrations


def inventory(path: Path) -> dict[str, object]:
    return {"schema_version": 1, "registrations": parse_registrations(path.read_text(encoding="utf-8"))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=Path("src/generated_visitor_registrations.inc"),
        help="source file to scan (default: src/generated_visitor_registrations.inc)",
    )
    parser.add_argument("-o", "--output", type=Path, help="write JSON to this file instead of stdout")
    args = parser.parse_args(argv)
    try:
        rendered = json.dumps(inventory(args.source), indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as error:
        print(f"inventory error: {error}", file=sys.stderr)
        return 2
    if not args.output:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
