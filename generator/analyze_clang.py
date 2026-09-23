#!/usr/bin/env python3
"""Build the generator's declaration inventory from Clang's JSON AST.

This is an explicit fallback for headers the installed Clava reader cannot
load. It records source declarations only; implicit template specializations
are checked against their template definition and omitted.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator, TextIO


CPP_QUALIFIED = re.compile(r"^(?:::)?[A-Za-z_][A-Za-z_0-9]*(?:::[A-Za-z_][A-Za-z_0-9]*)*$")


class AnalyzerError(Exception):
    """Clang could not produce a complete, unambiguous declaration model."""


def _actual_location(location: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(location, dict):
        return {}
    # Expansion locations identify where macro-generated declarations occur
    # in the analyzed header. Spelling locations point back to the macro body.
    for key in ("expansionLoc", "spellingLoc"):
        nested = location.get(key)
        if isinstance(nested, dict):
            return nested
    return location


def _declaration_location(
    raw_location: dict[str, Any] | None,
    declaration_name: str,
    inherited_file: str,
    offset_files: dict[int, set[str]],
    source_cache: dict[Path, tuple[bytes, list[int]]],
) -> dict[str, Any]:
    if not isinstance(raw_location, dict):
        return {}
    spelling = raw_location.get("spellingLoc")
    if isinstance(spelling, dict):
        offset = spelling.get("offset")
        if isinstance(offset, int) and declaration_name:
            candidates = set(offset_files.get(offset, set()))
            if spelling.get("file"):
                candidates.add(str(Path(spelling["file"]).resolve()))
            if inherited_file:
                candidates.add(str(Path(inherited_file).resolve()))
            matches = [candidate for candidate in candidates if _source_has_token(candidate, offset, declaration_name, source_cache)]
            if not matches:
                known_files = {source_file for files in offset_files.values() for source_file in files}
                matches = [candidate for candidate in known_files if _source_has_token(candidate, offset, declaration_name, source_cache)]
            if len(matches) == 1:
                return {**spelling, "file": matches[0]}
            if len(matches) > 1:
                raise AnalyzerError(f"Clang spelling location for {declaration_name} is ambiguous: {sorted(matches)}")
    return _actual_location(raw_location)


def _read_json_sequence(stream: TextIO, chunk_size: int = 1024 * 1024) -> Iterator[dict[str, Any]]:
    """Read Clang's filtered AST output, which is a sequence of JSON objects."""
    decoder = json.JSONDecoder()
    buffer = ""
    offset = 0
    eof = False
    while True:
        while offset < len(buffer) and buffer[offset].isspace():
            offset += 1
        if offset == len(buffer):
            if eof:
                return
            buffer = ""
            offset = 0
            chunk = stream.read(chunk_size)
            if not chunk:
                eof = True
                continue
            buffer = chunk
            continue

        try:
            value, next_offset = decoder.raw_decode(buffer, offset)
        except json.JSONDecodeError as error:
            if eof:
                raise AnalyzerError(f"Clang emitted invalid or incomplete JSON AST: {error}") from error
            # A filtered AST can contain one large namespace subtree. Keep
            # that subtree in memory, but do not retain prior roots.
            if offset:
                buffer = buffer[offset:]
                offset = 0
            chunk = stream.read(chunk_size)
            if not chunk:
                eof = True
            else:
                buffer += chunk
            continue

        if not isinstance(value, dict):
            raise AnalyzerError("Clang AST output root must be a JSON object")
        yield value
        offset = next_offset


def _file_for(location: dict[str, Any], inherited_file: str) -> str:
    return str(location.get("file") or inherited_file)


def _resolve_node_file(
    location: dict[str, Any],
    inherited_file: str,
    offset_files: dict[int, set[str]],
    source_cache: dict[Path, tuple[bytes, list[int]]],
    *,
    description: str,
    strict: bool,
    expected_token: str | None = None,
) -> str:
    explicit_file = location.get("file")
    if isinstance(explicit_file, str) and explicit_file:
        return str(Path(explicit_file).resolve())
    offset = location.get("offset")
    if isinstance(offset, int) and not isinstance(offset, bool):
        candidates = offset_files.get(offset, set())
        if len(candidates) == 1:
            candidate = next(iter(candidates))
            if not expected_token or _source_has_token(candidate, offset, expected_token, source_cache):
                return candidate
            if inherited_file and _source_has_token(inherited_file, offset, expected_token, source_cache):
                return str(Path(inherited_file).resolve())
            if strict:
                raise AnalyzerError(f"Clang location for {description} does not match its declared name at byte {offset}")
            return str(Path(inherited_file).resolve()) if inherited_file else ""
        if len(candidates) > 1:
            if expected_token:
                matches = [candidate for candidate in candidates if _source_has_token(candidate, offset, expected_token, source_cache)]
                if len(matches) == 1:
                    return matches[0]
            if strict:
                raise AnalyzerError(f"Clang source file is ambiguous for {description} at byte {offset}: {sorted(candidates)}")
            return str(Path(inherited_file).resolve()) if inherited_file else ""
    if inherited_file:
        line = location.get("line")
        column = location.get("col")
        if isinstance(offset, int) and isinstance(line, int) and isinstance(column, int):
            inherited = Path(inherited_file).resolve()
            cached = source_cache.get(inherited)
            if cached is None:
                try:
                    contents = inherited.read_bytes()
                except OSError as error:
                    raise AnalyzerError(f"Cannot read source file for {description}: {inherited}: {error}") from error
                starts = [0]
                starts.extend(index + 1 for index, byte in enumerate(contents) if byte == 10)
                cached = contents, starts
                source_cache[inherited] = cached
            _contents, starts = cached
            if 0 <= offset <= len(_contents):
                index = bisect.bisect_right(starts, offset) - 1
                if index + 1 == line and offset - starts[index] + 1 == column:
                    return str(inherited)
        elif isinstance(offset, int) and expected_token and _source_has_token(str(Path(inherited_file).resolve()), offset, expected_token, source_cache):
            return str(Path(inherited_file).resolve())
        elif not strict:
            return str(Path(inherited_file).resolve())
    if strict:
        point = location.get("line", "unknown line")
        raise AnalyzerError(f"Clang omitted source file for {description} at line {point}; provenance is unresolved")
    return str(Path(inherited_file).resolve()) if inherited_file else ""


def _source_has_token(
    source_file: str,
    offset: int,
    token: str,
    source_cache: dict[Path, tuple[bytes, list[int]]],
) -> bool:
    path = Path(source_file).resolve()
    cached = source_cache.get(path)
    if cached is None:
        try:
            contents = path.read_bytes()
        except OSError:
            return False
        starts = [0]
        starts.extend(index + 1 for index, byte in enumerate(contents) if byte == 10)
        cached = contents, starts
        source_cache[path] = cached
    contents = cached[0]
    return contents[offset : offset + len(token)] == token.encode("utf-8")


def _source_point(
    raw_location: dict[str, Any] | None,
    inherited_file: str,
    header_root: Path,
    offset_files: dict[int, set[str]],
    source_cache: dict[Path, tuple[bytes, list[int]]],
    *,
    description: str,
) -> tuple[int, int, int, Path]:
    location = _actual_location(raw_location)
    source_file = str(location.get("file") or inherited_file or "")
    offset = location.get("offset")
    if not source_file and isinstance(offset, int):
        candidates = offset_files.get(offset, set())
        if len(candidates) == 1:
            source_file = next(iter(candidates))
        elif len(candidates) > 1:
            inherited = str(Path(inherited_file).resolve()) if inherited_file else ""
            if inherited in candidates:
                source_file = inherited
            else:
                raise AnalyzerError(f"Clang source file is ambiguous for {description} at byte {offset}: {sorted(candidates)}")
    source_file = source_file or inherited_file
    if not source_file:
        raise AnalyzerError(f"Clang did not identify the source file for {description}")
    try:
        resolved_file = Path(source_file).resolve()
    except OSError as error:
        raise AnalyzerError(f"Invalid source file for {description}: {source_file}") from error
    try:
        resolved_file.relative_to(header_root)
    except ValueError as error:
        raise AnalyzerError(f"{description} is outside --header-root {header_root}: {resolved_file}") from error

    line = location.get("line")
    column = location.get("col")
    if isinstance(line, bool) or not isinstance(line, int) or line < 1 or isinstance(column, bool) or not isinstance(column, int) or column < 1:
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise AnalyzerError(f"Clang did not provide a usable source offset for {description}")
        source_data = source_cache.get(resolved_file)
        if source_data is None:
            try:
                contents = resolved_file.read_bytes()
            except OSError as error:
                raise AnalyzerError(f"Cannot read source file for {description}: {resolved_file}: {error}") from error
            line_starts = [0]
            line_starts.extend(index + 1 for index, byte in enumerate(contents) if byte == 10)
            source_data = (contents, line_starts)
            source_cache[resolved_file] = source_data
        _contents, line_starts = source_data
        if offset > len(_contents):
            raise AnalyzerError(f"Clang source offset is past end of file for {description}")
        line_index = bisect.bisect_right(line_starts, offset) - 1
        line = line_index + 1
        column = offset - line_starts[line_index] + 1

    token_length = location.get("tokLen", 1)
    if isinstance(token_length, bool) or not isinstance(token_length, int) or token_length < 1:
        raise AnalyzerError(f"Clang provided an invalid token length for {description}")
    return line, column, token_length, resolved_file


def _source_location(
    node: dict[str, Any],
    inherited_file: str,
    header_root: Path,
    offset_files: dict[int, set[str]],
    source_cache: dict[Path, tuple[bytes, list[int]]],
    *,
    description: str,
) -> dict[str, Any]:
    source_range = node.get("range") or {}
    begin = source_range.get("begin") or node.get("loc")
    end = source_range.get("end") or begin
    line, column, _begin_length, start_file = _source_point(
        begin, inherited_file, header_root, offset_files, source_cache, description=description
    )
    end_line, end_column, end_length, end_file = _source_point(
        end, inherited_file, header_root, offset_files, source_cache, description=description
    )
    if start_file != end_file:
        # Macro-generated declarations can span an argument in an included
        # file and a macro body in this header. The identifier location is a
        # precise single-file location even when that range is not.
        if not node.get("loc"):
            raise AnalyzerError(f"Clang source range for {description} crosses files and has no identifier location")
        line, column, token_length, identifier_file = _source_point(
            node["loc"], inherited_file, header_root, offset_files, source_cache,
            description=f"identifier of {description}",
        )
        return {
            "file": identifier_file.relative_to(header_root).as_posix(),
            "line": line,
            "column": column,
            "end_line": line,
            "end_column": column + token_length - 1,
        }
    return {
        "file": start_file.relative_to(header_root).as_posix(),
        "line": line,
        "column": column,
        "end_line": end_line,
        "end_column": end_column + end_length - 1,
    }


def _source_snippet(
    node: dict[str, Any],
    inherited_file: str,
    header_root: Path,
    offset_files: dict[int, set[str]],
    source_cache: dict[Path, tuple[bytes, list[int]]],
) -> str:
    source_range = node.get("range") or {}
    begin = _actual_location(source_range.get("begin"))
    end = _actual_location(source_range.get("end"))
    start_offset = begin.get("offset")
    end_offset = end.get("offset")
    end_length = end.get("tokLen", 1)
    begin_point = _source_point(begin, inherited_file, header_root, offset_files, source_cache, description="enumerator source")
    end_point = _source_point(end, inherited_file, header_root, offset_files, source_cache, description="enumerator source")
    if (
        begin_point[3] == end_point[3]
        and isinstance(start_offset, int)
        and isinstance(end_offset, int)
        and isinstance(end_length, int)
    ):
        if begin_point[3] not in source_cache:
            contents = begin_point[3].read_bytes()
            starts = [0]
            starts.extend(index + 1 for index, byte in enumerate(contents) if byte == 10)
            source_cache[begin_point[3]] = (contents, starts)
        source_data = source_cache[begin_point[3]][0]
        if 0 <= start_offset <= end_offset < len(source_data):
            return source_data[start_offset : end_offset + end_length].decode("utf-8", errors="replace").strip()
    return str(node.get("name") or "")


def _offset_file_index(root: dict[str, Any]) -> dict[int, set[str]]:
    offset_files: dict[int, set[str]] = defaultdict(set)

    def add_location(raw: Any) -> None:
        location = _actual_location(raw)
        file_name = location.get("file")
        offset = location.get("offset")
        if isinstance(file_name, str) and file_name and isinstance(offset, int) and not isinstance(offset, bool):
            offset_files[offset].add(str(Path(file_name).resolve()))

    def visit(node: dict[str, Any]) -> None:
        add_location(node.get("loc"))
        source_range = node.get("range") or {}
        add_location(source_range.get("begin"))
        add_location(source_range.get("end"))
        for child in node.get("inner", []):
            if isinstance(child, dict):
                visit(child)

    visit(root)
    return offset_files


def build_inventory(
    roots: Iterator[dict[str, Any]],
    *,
    header: Path,
    header_root: Path,
    source: bytes,
    ast_filter: str | None = None,
    qualified_prefix: str | None = None,
) -> dict[str, Any]:
    header = header.resolve()
    header_root = header_root.resolve()
    try:
        relative_header = header.relative_to(header_root).as_posix()
    except ValueError as error:
        raise AnalyzerError(f"Header {header} must be beneath --header-root {header_root}") from error

    if ast_filter and not qualified_prefix:
        raise AnalyzerError("--qualified-prefix is required with --ast-filter because Clang omits parent scopes")
    if qualified_prefix and not CPP_QUALIFIED.fullmatch(qualified_prefix):
        raise AnalyzerError(f"Invalid qualified prefix: {qualified_prefix}")

    source_cache: dict[Path, tuple[bytes, list[int]]] = {}
    source_cache[header] = (source, [0] + [index + 1 for index, byte in enumerate(source) if byte == 10])
    base_scope = tuple(qualified_prefix.split("::")) if qualified_prefix else ()
    declarations: list[dict[str, Any]] = []
    template_records: dict[str, list[tuple[int | None, int]]] = {}
    specializations: list[tuple[str, dict[str, Any], str]] = []

    def walk(
        node: dict[str, Any],
        scopes: tuple[str, ...],
        inherited_file: str,
        offset_files: dict[int, set[str]],
        selected_header_root: bool,
    ) -> None:
        kind = str(node.get("kind") or "")
        name = node.get("name")
        if not isinstance(name, str):
            name = ""
        location = _declaration_location(node.get("loc"), name, inherited_file, offset_files, source_cache)
        source_file = _resolve_node_file(
            location,
            inherited_file,
            offset_files,
            source_cache,
            description=f"{kind or 'AST node'} {name or '<anonymous>'}",
            strict=False,
        )
        try:
            is_target = bool(source_file) and Path(source_file).resolve() == header
        except OSError:
            is_target = False
        include_declaration = selected_header_root or is_target

        if include_declaration and kind == "ClassTemplateSpecializationDecl" and node.get("completeDefinition"):
            if not name:
                raise AnalyzerError("Clang reported a class template specialization without a name")
            qualified_name = "::".join((*scopes, name))
            exact_file = _resolve_node_file(
                location,
                source_file,
                offset_files,
                source_cache,
                description=f"template specialization {qualified_name}",
                strict=True,
                expected_token=name,
            )
            specializations.append((qualified_name, node, exact_file))

        if include_declaration and kind in {"CXXRecordDecl", "RecordDecl"} and node.get("completeDefinition") and not node.get("isImplicit"):
            if not name:
                raise AnalyzerError(f"Unnamed record declaration in {relative_header}")
            qualified_name = "::".join((*scopes, name))
            exact_file = _resolve_node_file(
                location,
                source_file,
                offset_files,
                source_cache,
                description=f"record {qualified_name}",
                strict=True,
                expected_token=name,
            )
            members: list[dict[str, Any]] = []
            seen_members: set[str] = set()
            for field in node.get("inner", []):
                if field.get("kind") != "FieldDecl":
                    continue
                field_name = field.get("name")
                field_type = (field.get("type") or {}).get("qualType")
                if not isinstance(field_name, str) or not field_name:
                    raise AnalyzerError(f"Field without a name in {qualified_name}")
                if not isinstance(field_type, str) or not field_type.strip():
                    raise AnalyzerError(f"Field {qualified_name}.{field_name} has no Clang type")
                if field_name in seen_members:
                    raise AnalyzerError(f"Duplicate field {field_name} in {qualified_name}")
                seen_members.add(field_name)
                field_location = _declaration_location(field.get("loc"), field_name, exact_file, offset_files, source_cache)
                field_file = _resolve_node_file(
                    field_location,
                    exact_file,
                    offset_files,
                    source_cache,
                    description=f"field {qualified_name}.{field_name}",
                    strict=True,
                    expected_token=field_name,
                )
                members.append({
                    "name": field_name,
                    "type": " ".join(field_type.split()),
                    "location": _source_location(
                        field,
                        field_file,
                        header_root,
                        offset_files,
                        source_cache,
                        description=f"field {qualified_name}.{field_name}",
                    ),
                })
            declaration = {
                "kind": "record",
                "qualified_name": qualified_name,
                "location": _source_location(
                    node,
                    exact_file,
                    header_root,
                    offset_files,
                    source_cache,
                    description=f"record {qualified_name}",
                ),
                "members": members,
            }
            declarations.append(declaration)
            record_offset = location.get("offset")
            if not isinstance(record_offset, int):
                record_offset = None
            template_records.setdefault(qualified_name, []).append((record_offset, len(declarations) - 1))

        if include_declaration and kind == "EnumDecl":
            enumerators = [entry for entry in node.get("inner", []) if entry.get("kind") == "EnumConstantDecl"]
            if enumerators:
                if not name:
                    raise AnalyzerError(f"Unnamed enum declaration in {relative_header}")
                qualified_name = "::".join((*scopes, name))
                exact_file = _resolve_node_file(
                    location,
                    source_file,
                    offset_files,
                    source_cache,
                    description=f"enum {qualified_name}",
                    strict=True,
                    expected_token=name,
                )
                constants: list[dict[str, Any]] = []
                seen_constants: set[str] = set()
                for enumerator in enumerators:
                    constant_name = enumerator.get("name")
                    if not isinstance(constant_name, str) or not constant_name:
                        raise AnalyzerError(f"Enumerator without a name in {qualified_name}")
                    if constant_name in seen_constants:
                        raise AnalyzerError(f"Duplicate enumerator {constant_name} in {qualified_name}")
                    seen_constants.add(constant_name)
                    enumerator_location = _declaration_location(enumerator.get("loc"), constant_name, exact_file, offset_files, source_cache)
                    constants.append({
                        "name": constant_name,
                        "source": _source_snippet(enumerator, exact_file, header_root, offset_files, source_cache) or constant_name,
                        "location": _source_location(
                            {**enumerator, "loc": enumerator_location},
                            exact_file,
                            header_root,
                            offset_files,
                            source_cache,
                            description=f"enumerator {qualified_name}::{constant_name}",
                        ),
                    })
                declarations.append({
                    "kind": "enum",
                    "qualified_name": qualified_name,
                    "location": _source_location(
                        node,
                        exact_file,
                        header_root,
                        offset_files,
                        source_cache,
                        description=f"enum {qualified_name}",
                    ),
                    "constants": constants,
                })

        if kind in {"NamespaceDecl", "CXXRecordDecl", "RecordDecl"} and name:
            if kind == "NamespaceDecl" or (node.get("completeDefinition") and not node.get("isImplicit")):
                child_scopes = (*scopes, name)
            else:
                child_scopes = scopes
        else:
            child_scopes = scopes

        for child in node.get("inner", []):
            if isinstance(child, dict):
                walk(child, child_scopes, source_file or inherited_file, offset_files, selected_header_root)

    for root in roots:
        offset_files = _offset_file_index(root)
        root_location = _actual_location(root.get("loc"))
        root_file = _resolve_node_file(
            root_location,
            "",
            offset_files,
            source_cache,
            description=f"AST root {root.get('kind', '<unknown>')}",
            strict=False,
        )
        root_is_header = bool(root_file) and Path(root_file).resolve() == header
        if ast_filter and not root_is_header:
            continue
        start_scope = base_scope if root_is_header else ()
        walk(root, start_scope, root_file, offset_files, bool(ast_filter and root_is_header))

    if not declarations:
        raise AnalyzerError(f"Clang JSON AST contained no declarations from {header}")

    primary_offsets = {
        qualified_name: {offset for offset, _index in entries if offset is not None}
        for qualified_name, entries in template_records.items()
    }
    for qualified_name, specialization, _inherited_file in specializations:
        specialization_location = _declaration_location(
            specialization.get("loc"),
            str(specialization.get("name") or ""),
            _inherited_file,
            {},
            source_cache,
        )
        specialization_offset = specialization_location.get("offset")
        if not isinstance(specialization_offset, int) or specialization_offset not in primary_offsets.get(qualified_name, set()):
            point = specialization_location.get("line", "unknown line")
            raise AnalyzerError(
                f"Explicit or ambiguous class template specialization {qualified_name} at line {point} is unsupported"
            )

    by_name: dict[str, dict[str, Any]] = {}
    for declaration in declarations:
        name = str(declaration["qualified_name"])
        if not CPP_QUALIFIED.fullmatch(name):
            raise AnalyzerError(f"Clang produced an unsupported qualified name: {name!r}")
        if name in by_name:
            raise AnalyzerError(f"Ambiguous duplicate declaration: {name}")
        by_name[name] = declaration

    declarations.sort(key=lambda item: item["qualified_name"])
    referenced_files: set[str] = set()
    for declaration in declarations:
        referenced_files.add(declaration["location"]["file"])
        for member in declaration.get("members", []):
            referenced_files.add(member["location"]["file"])
        for constant in declaration.get("constants", []):
            referenced_files.add(constant["location"]["file"])
    source_files = []
    for relative_file in sorted(referenced_files):
        source_path = (header_root / relative_file).resolve()
        try:
            source_path.relative_to(header_root)
        except ValueError as error:
            raise AnalyzerError(f"Declaration source file escapes --header-root: {relative_file}") from error
        try:
            file_bytes = source_path.read_bytes()
        except OSError as error:
            raise AnalyzerError(f"Cannot read declaration source file {relative_file}: {error}") from error
        source_files.append({
            "file": relative_file,
            "sha256": hashlib.sha256(file_bytes).hexdigest(),
        })
    return {
        "format": "clava-declaration-inventory/v1",
        "source_header": {
            "file": relative_header,
            "sha256": hashlib.sha256(source).hexdigest(),
        },
        "source_files": source_files,
        "declarations": declarations,
    }


def analyze(
    *,
    header: Path,
    header_root: Path,
    output: Path,
    compiler: str,
    include_dirs: list[Path],
    compiler_args: list[str] | None = None,
    ast_filter: str | None = None,
    qualified_prefix: str | None = None,
) -> dict[str, Any]:
    header = header.resolve()
    header_root = header_root.resolve()
    if not header.is_file():
        raise AnalyzerError(f"Header does not exist: {header}")
    try:
        header.relative_to(header_root)
    except ValueError as error:
        raise AnalyzerError(f"Header {header} must be beneath --header-root {header_root}") from error
    for include_dir in include_dirs:
        if not include_dir.is_dir():
            raise AnalyzerError(f"Include directory does not exist: {include_dir}")

    try:
        source = header.read_bytes()
    except OSError as error:
        raise AnalyzerError(f"Cannot read header {header}: {error}") from error

    command = shlex.split(compiler)
    if not command:
        raise AnalyzerError("--clang-command must name an executable")
    invocation = command + ["-std=c++20", "-fsyntax-only", "-x", "c++"]
    for include_dir in include_dirs:
        invocation.extend(["-isystem", str(include_dir.resolve())])
    invocation.extend(compiler_args or [])
    invocation.extend(["-Xclang", "-ast-dump=json"])
    if ast_filter:
        invocation.extend(["-Xclang", "-ast-dump-filter", "-Xclang", ast_filter])
    invocation.append(str(header))

    with tempfile.TemporaryDirectory(prefix="flang-clang-json-") as temporary_directory:
        ast_path = Path(temporary_directory) / "clang-ast.json-seq"
        try:
            with ast_path.open("w", encoding="utf-8") as ast_stream:
                result = subprocess.run(
                    invocation,
                    stdout=ast_stream,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
        except OSError as error:
            raise AnalyzerError(f"Could not run Clang command {command[0]!r}: {error}") from error
        if result.returncode != 0:
            detail = result.stderr.rstrip()
            raise AnalyzerError(
                f"Clang failed with exit code {result.returncode}"
                + (f":\n{detail}" if detail else "")
            )
        try:
            with ast_path.open("r", encoding="utf-8") as ast_stream:
                inventory = build_inventory(
                    _read_json_sequence(ast_stream),
                    header=header,
                    header_root=header_root,
                    source=source,
                    ast_filter=ast_filter,
                    qualified_prefix=qualified_prefix,
                )
        except UnicodeDecodeError as error:
            raise AnalyzerError(f"Clang emitted non-UTF-8 JSON AST: {error}") from error

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--header-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clang-command", default=os.environ.get("FLANG_GENERATOR_CLANG_COMMAND", "clang++"))
    parser.add_argument("--include-dir", type=Path, action="append", default=[])
    parser.add_argument("--clang-arg", action="append", default=[], help="extra argument passed directly to Clang; repeat as needed")
    parser.add_argument("--ast-filter", help="Clang AST substring filter for large headers")
    parser.add_argument("--qualified-prefix", help="parent scope omitted by --ast-filter, for example Fortran")
    args = parser.parse_args(argv)
    include_dirs = args.include_dir or [args.header_root]

    try:
        inventory = analyze(
            header=args.header,
            header_root=args.header_root,
            output=args.output,
            compiler=args.clang_command,
            include_dirs=include_dirs,
            compiler_args=args.clang_arg,
            ast_filter=args.ast_filter,
            qualified_prefix=args.qualified_prefix,
        )
    except AnalyzerError as error:
        print(f"Clang analyzer error: {error}", file=sys.stderr)
        return 2
    print(f"Wrote {len(inventory['declarations'])} declarations to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
