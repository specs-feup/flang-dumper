#!/usr/bin/env python3
"""Merge Clang declaration inventories without discarding conflicting data.

The first input is the primary model: its ``source_header`` is retained in the
result. All source file hashes are reconciled by relative path, and declarations
are unioned by fully qualified name. Repeated declarations are accepted only
when their complete JSON values agree.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


MODEL_FORMAT = "clava-declaration-inventory/v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
QUALIFIED_NAME = re.compile(r"^(?:::)?[A-Za-z_][A-Za-z_0-9]*(?:::[A-Za-z_][A-Za-z_0-9]*)*$")


class MergeError(ValueError):
    """An input inventory is malformed or conflicts with another inventory."""


def _object(value: Any, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MergeError(f"{description} must be a JSON object")
    return value


def _array(value: Any, description: str) -> list[Any]:
    if not isinstance(value, list):
        raise MergeError(f"{description} must be a JSON array")
    return value


def _source_path(value: Any, description: str) -> str:
    if not isinstance(value, str) or not value:
        raise MergeError(f"{description} must be a non-empty relative POSIX path")
    if "\\" in value or "\x00" in value:
        raise MergeError(f"{description} is not a canonical relative POSIX path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise MergeError(f"{description} is not a canonical relative POSIX path: {value!r}")
    if path.as_posix() != value:
        raise MergeError(f"{description} is not a canonical relative POSIX path: {value!r}")
    return value


def _digest(value: Any, description: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise MergeError(f"{description} must be a lowercase SHA-256 digest")
    return value


def _location(value: Any, description: str) -> dict[str, Any]:
    location = _object(value, description)
    expected = {"file", "line", "column", "end_line", "end_column"}
    if set(location) != expected:
        raise MergeError(f"{description} must contain exactly {sorted(expected)}")
    _source_path(location["file"], f"{description}.file")
    for key in ("line", "column", "end_line", "end_column"):
        number = location[key]
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise MergeError(f"{description}.{key} must be a positive integer")
    return location


def _validate_declaration(value: Any, description: str) -> tuple[str, dict[str, Any]]:
    declaration = _object(value, description)
    name = declaration.get("qualified_name")
    if not isinstance(name, str) or not QUALIFIED_NAME.fullmatch(name):
        raise MergeError(f"{description}.qualified_name must be a supported C++ qualified name")
    kind = declaration.get("kind")
    if kind == "record":
        expected_keys = {"kind", "qualified_name", "location", "members"}
        if set(declaration) != expected_keys:
            raise MergeError(f"{description} record must contain exactly {sorted(expected_keys)}")
        _location(declaration["location"], f"{description}.location")
        members = _array(declaration["members"], f"{description}.members")
        for index, raw_member in enumerate(members):
            member_description = f"{description}.members[{index}]"
            member = _object(raw_member, member_description)
            if set(member) != {"name", "type", "location"}:
                raise MergeError(
                    f"{member_description} must contain exactly ['location', 'name', 'type']"
                )
            for key in ("name", "type"):
                if not isinstance(member[key], str) or not member[key]:
                    raise MergeError(f"{member_description}.{key} must be a non-empty string")
            _location(member["location"], f"{member_description}.location")
    elif kind == "enum":
        expected_keys = {"kind", "qualified_name", "location", "constants"}
        if set(declaration) != expected_keys:
            raise MergeError(f"{description} enum must contain exactly {sorted(expected_keys)}")
        _location(declaration["location"], f"{description}.location")
        constants = _array(declaration["constants"], f"{description}.constants")
        for index, raw_constant in enumerate(constants):
            constant_description = f"{description}.constants[{index}]"
            constant = _object(raw_constant, constant_description)
            if set(constant) != {"name", "source", "location"}:
                raise MergeError(
                    f"{constant_description} must contain exactly ['location', 'name', 'source']"
                )
            for key in ("name", "source"):
                if not isinstance(constant[key], str) or not constant[key]:
                    raise MergeError(f"{constant_description}.{key} must be a non-empty string")
            _location(constant["location"], f"{constant_description}.location")
    else:
        raise MergeError(f"{description}.kind must be 'record' or 'enum'")
    return name.removeprefix("::"), declaration


def _validate_model(value: Any, index: int) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    description = f"input[{index}]"
    model = _object(value, description)
    expected_root_keys = {"format", "source_header", "source_files", "declarations"}
    if set(model) != expected_root_keys:
        raise MergeError(f"{description} must contain exactly {sorted(expected_root_keys)}")
    if model["format"] != MODEL_FORMAT:
        raise MergeError(f"{description}.format must be {MODEL_FORMAT!r}")

    source_header = _object(model["source_header"], f"{description}.source_header")
    unexpected_header_keys = set(source_header) - {"file", "sha256"}
    if unexpected_header_keys:
        raise MergeError(
            f"{description}.source_header contains unsupported keys: "
            + ", ".join(sorted(unexpected_header_keys))
        )
    _source_path(source_header.get("file"), f"{description}.source_header.file")
    _digest(source_header.get("sha256"), f"{description}.source_header.sha256")

    source_files: list[dict[str, Any]] = []
    seen_paths: dict[str, str] = {}
    for file_index, raw_file in enumerate(_array(model["source_files"], f"{description}.source_files")):
        file_description = f"{description}.source_files[{file_index}]"
        source_file = _object(raw_file, file_description)
        unexpected_file_keys = set(source_file) - {"file", "sha256"}
        if unexpected_file_keys:
            raise MergeError(
                f"{file_description} contains unsupported keys: "
                + ", ".join(sorted(unexpected_file_keys))
            )
        path = _source_path(source_file.get("file"), f"{file_description}.file")
        digest = _digest(source_file.get("sha256"), f"{file_description}.sha256")
        if path in seen_paths:
            raise MergeError(f"{description} has a source path collision for {path!r}")
        seen_paths[path] = digest
        source_files.append({"file": path, "sha256": digest})

    declarations: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    source_paths = set(seen_paths)
    for declaration_index, raw_declaration in enumerate(
        _array(model["declarations"], f"{description}.declarations")
    ):
        declaration_description = f"{description}.declarations[{declaration_index}]"
        name, declaration = _validate_declaration(raw_declaration, declaration_description)
        if name in seen_names:
            raise MergeError(f"{description} has a duplicate declaration {name}")
        seen_names.add(name)
        _require_known_location_files(declaration, source_paths, declaration_description)
        declarations.append(declaration)
    return source_header, source_files, declarations


def _require_known_location_files(
    declaration: dict[str, Any], source_paths: set[str], description: str
) -> None:
    locations = [declaration["location"]]
    locations.extend(
        item["location"]
        for item in declaration.get("members", declaration.get("constants", []))
    )
    for location in locations:
        source_path = location["file"]
        if source_path not in source_paths:
            raise MergeError(
                f"{description} refers to {source_path!r}, which is absent from source_files"
            )


def merge_inventories(models: Sequence[Any]) -> dict[str, Any]:
    """Merge one or more inventories, retaining the first input's header."""
    if not models:
        raise MergeError("at least one declaration inventory is required")

    validated = [_validate_model(model, index) for index, model in enumerate(models)]
    primary_header = validated[0][0]
    all_digests: dict[str, str] = {}
    all_path_spellings: dict[str, str] = {}
    merged_source_files: dict[str, str] = {}
    merged_declarations: dict[str, dict[str, Any]] = {}

    for source_header, source_files, declarations in validated:
        tracked = [(source_header["file"], source_header["sha256"])]
        tracked.extend((item["file"], item["sha256"]) for item in source_files)
        for path, digest in tracked:
            # Paths are required to be canonical above. This key also catches
            # case-only collisions, which would overwrite on common Windows
            # and macOS filesystems even when analyzed on Linux.
            collision_key = path.casefold()
            previous_spelling = all_path_spellings.get(collision_key)
            if previous_spelling is not None and previous_spelling != path:
                raise MergeError(
                    f"source path collision: {previous_spelling!r} and {path!r}"
                )
            all_path_spellings[collision_key] = path
            previous_digest = all_digests.get(path)
            if previous_digest is not None and previous_digest != digest:
                raise MergeError(
                    f"source digest conflict for {path!r}: {previous_digest} != {digest}"
                )
            all_digests[path] = digest
            if path in merged_source_files and merged_source_files[path] != digest:
                raise MergeError(f"source digest conflict for {path!r}")
        for source_file in source_files:
            path = source_file["file"]
            digest = source_file["sha256"]
            previous_digest = merged_source_files.get(path)
            if previous_digest is not None and previous_digest != digest:
                raise MergeError(f"source digest conflict for {path!r}")
            merged_source_files[path] = digest

        for declaration in declarations:
            name = declaration["qualified_name"].removeprefix("::")
            previous = merged_declarations.get(name)
            if previous is not None and previous != declaration:
                raise MergeError(f"conflicting duplicate declaration {name}")
            if previous is None:
                merged_declarations[name] = declaration

    return {
        "format": MODEL_FORMAT,
        "source_header": primary_header,
        "source_files": [
            {"file": path, "sha256": merged_source_files[path]}
            for path in sorted(merged_source_files)
        ],
        "declarations": [merged_declarations[name] for name in sorted(merged_declarations)],
    }


def _read_model(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise MergeError(f"cannot read input {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise MergeError(f"invalid JSON in {path}: {error}") from error


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="inventories in merge priority order")
    parser.add_argument("-o", "--output", type=Path, help="write the merged inventory to this file")
    args = parser.parse_args(argv)

    try:
        if args.output is not None:
            output_path = args.output.resolve()
            input_paths = {path.resolve() for path in args.inputs}
            if output_path in input_paths:
                raise MergeError("output path must not overwrite an input inventory")
        result = merge_inventories([_read_model(path) for path in args.inputs])
        serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output is None:
            sys.stdout.write(serialized)
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized, encoding="utf-8", newline="\n")
            print(f"Wrote {len(result['declarations'])} declarations to {args.output.resolve()}")
    except MergeError as error:
        print(f"inventory merge error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"inventory merge error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
