#!/usr/bin/env python3
"""Generate the small Clava declaration-analysis probe artifacts.

This deliberately emits a schema/codegen probe, not the Flang dumper's final
wire protocol. Production node identity, record framing, and visitor coverage
remain outside this first slice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_HEADER = ROOT / "fixtures" / "parse_tree_fixture.hpp"
DEFAULT_METADATA = ROOT / "metadata.json"
ANALYZER = ROOT / "analyze.js"
SCHEMA_FILENAME = "flang_ast.proto"
PRODUCER_FILENAME = "producer.fragment.cpp"
MODEL_FILENAME = "declarations.json"

PROTO_SCALARS = {
    "bool": {"bool"},
    "int32": {"int", "signed int", "short", "short int", "signed short", "signed short int", "signed char"},
    "uint32": {"unsigned", "unsigned int", "unsigned short", "unsigned short int", "unsigned char"},
    "int64": {"long", "long int", "signed long", "signed long int", "long long", "long long int", "signed long long", "signed long long int"},
    "uint64": {"unsigned long", "unsigned long int", "unsigned long long", "unsigned long long int"},
    "float": {"float"},
    "double": {"double"},
    "string": {"std::string"},
    "bytes": {"std::string"},
}
IDENT = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")
PACKAGE = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*$")
CPP_QUALIFIED = re.compile(r"^(?:::)?[A-Za-z_][A-Za-z_0-9]*(?:::[A-Za-z_][A-Za-z_0-9]*)*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class GenerationError(Exception):
    """An input declaration or manifest entry cannot be generated safely."""


def fail(message: str) -> None:
    raise GenerationError(message)


def require_object(value: Any, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{description} must be a JSON object")
    return value


def require_list(value: Any, description: str) -> list[Any]:
    if not isinstance(value, list):
        fail(f"{description} must be a JSON array")
    return value


def required_string(value: Any, description: str) -> str:
    if not isinstance(value, str) or not value:
        fail(f"{description} must be a non-empty string")
    return value


def positive_int(value: Any, description: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        fail(f"{description} must be an integer")
    minimum = 0 if allow_zero else 1
    if value < minimum or value > 536_870_911 or 19_000 <= value <= 19_999:
        fail(f"{description} is outside the protobuf field/enum number range: {value}")
    return value


def normalized_cpp_type(value: str) -> str:
    value = re.sub(r"\b(?:struct|class|enum)\s+", "", value.strip())
    value = re.sub(r"\s+", " ", value)
    return value.removeprefix("::")


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def read_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        fail(f"Cannot read {description} {path}: {error}")
    except json.JSONDecodeError as error:
        fail(f"Invalid JSON in {description} {path}: {error}")


def declaration_index(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if model.get("format") != "clava-declaration-inventory/v1":
        fail("model format must be 'clava-declaration-inventory/v1'")
    source_header = require_object(model.get("source_header"), "model.source_header")
    if not SHA256.fullmatch(required_string(source_header.get("sha256"), "model.source_header.sha256")):
        fail("model.source_header.sha256 must be a lowercase SHA-256 digest")
    required_string(source_header.get("file"), "model.source_header.file")
    declarations = require_list(model.get("declarations"), "model.declarations")
    result: dict[str, dict[str, Any]] = {}
    for declaration in declarations:
        item = require_object(declaration, "model declaration")
        name = required_string(item.get("qualified_name"), "declaration.qualified_name")
        if not CPP_QUALIFIED.fullmatch(name):
            fail(f"Unsupported qualified C++ declaration name: {name}")
        if name in result:
            fail(f"Duplicate declaration in Clava model: {name}")
        if item.get("kind") not in {"record", "enum"}:
            fail(f"Unsupported Clava declaration kind for {name}: {item.get('kind')!r}")
        location = require_object(item.get("location"), f"{name}.location")
        required_string(location.get("file"), f"{name}.location.file")
        positive_int(location.get("line"), f"{name}.location.line")
        positive_int(location.get("column"), f"{name}.location.column")
        result[name] = item
    return result


def validate_manifest(model: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    if metadata.get("format_version") != 1:
        fail("metadata.format_version must be 1")
    package = required_string(metadata.get("proto_package"), "metadata.proto_package")
    if not PACKAGE.fullmatch(package):
        fail(f"Invalid protobuf package name: {package}")
    header_include = required_string(metadata.get("source_header"), "metadata.source_header")
    if Path(header_include).is_absolute() or ".." in Path(header_include).parts:
        fail("metadata.source_header must be a path relative to the generator directory")
    if model["source_header"]["file"] != header_include:
        fail(f"Analyzed header is {model['source_header']['file']!r}, but metadata names {header_include!r}")

    declarations = declaration_index(model)
    nodes = require_list(metadata.get("nodes"), "metadata.nodes")
    enums = require_list(metadata.get("enums"), "metadata.enums")
    by_cpp_node: dict[str, dict[str, Any]] = {}
    by_proto_node: dict[str, dict[str, Any]] = {}
    kind_numbers: set[int] = set()
    kind_names: set[str] = set()
    for node in nodes:
        item = require_object(node, "metadata node")
        cpp_type = required_string(item.get("cpp_type"), "node.cpp_type")
        if not CPP_QUALIFIED.fullmatch(cpp_type):
            fail(f"Invalid node C++ type name: {cpp_type}")
        if cpp_type in by_cpp_node:
            fail(f"Duplicate metadata node: {cpp_type}")
        if declarations.get(cpp_type, {}).get("kind") != "record":
            fail(f"Metadata node {cpp_type} is missing from the Clava record inventory")
        proto_name = required_string(item.get("proto_name"), f"{cpp_type}.proto_name")
        kind_name = required_string(item.get("kind_name"), f"{cpp_type}.kind_name")
        if not IDENT.fullmatch(proto_name) or not IDENT.fullmatch(kind_name):
            fail(f"Invalid protobuf name in metadata for {cpp_type}")
        if proto_name in by_proto_node:
            fail(f"Duplicate protobuf message name: {proto_name}")
        if kind_name in kind_names:
            fail(f"Duplicate node kind name: {kind_name}")
        kind_name_number = positive_int(item.get("kind_number"), f"{cpp_type}.kind_number")
        if kind_name_number in kind_numbers:
            fail(f"Duplicate node kind number: {kind_name_number}")
        kind_numbers.add(kind_name_number)
        kind_names.add(kind_name)
        by_cpp_node[cpp_type] = item
        by_proto_node[proto_name] = item

    by_cpp_enum: dict[str, dict[str, Any]] = {}
    by_proto_enum: dict[str, dict[str, Any]] = {}
    enum_value_names: set[str] = set()
    for enum in enums:
        item = require_object(enum, "metadata enum")
        cpp_type = required_string(item.get("cpp_type"), "enum.cpp_type")
        if not CPP_QUALIFIED.fullmatch(cpp_type):
            fail(f"Invalid enum C++ type name: {cpp_type}")
        if cpp_type in by_cpp_enum:
            fail(f"Duplicate metadata enum: {cpp_type}")
        if declarations.get(cpp_type, {}).get("kind") != "enum":
            fail(f"Metadata enum {cpp_type} is missing from the Clava enum inventory")
        proto_name = required_string(item.get("proto_name"), f"{cpp_type}.proto_name")
        zero_name = required_string(item.get("zero_name"), f"{cpp_type}.zero_name")
        if not IDENT.fullmatch(proto_name) or not IDENT.fullmatch(zero_name):
            fail(f"Invalid protobuf enum name in metadata for {cpp_type}")
        if proto_name in by_proto_enum or proto_name in by_proto_node or proto_name == "NodeKind":
            fail(f"Duplicate protobuf type name: {proto_name}")
        by_cpp_enum[cpp_type] = item
        by_proto_enum[proto_name] = item
        values = require_list(item.get("values"), f"{cpp_type}.values")
        if not values:
            fail(f"Enum mapping for {cpp_type} must include at least one non-zero value")
        numbers = {0}
        names = {zero_name}
        for value in values:
            entry = require_object(value, f"{cpp_type} enum value")
            cpp_name = required_string(entry.get("cpp_name"), f"{cpp_type}.cpp_name")
            proto_value_name = required_string(entry.get("proto_name"), f"{cpp_type}.{cpp_name}.proto_name")
            if not IDENT.fullmatch(cpp_name) or not IDENT.fullmatch(proto_value_name):
                fail(f"Invalid enum constant name for {cpp_type}: {cpp_name}")
            number = positive_int(entry.get("number"), f"{cpp_type}.{cpp_name}.number")
            if number in numbers:
                fail(f"Duplicate protobuf enum number {number} in {proto_name}")
            if proto_value_name in names or proto_value_name in enum_value_names:
                fail(f"Duplicate protobuf enum value name: {proto_value_name}")
            numbers.add(number)
            names.add(proto_value_name)
            enum_value_names.add(proto_value_name)

    if set(declarations) != set(by_cpp_node) | set(by_cpp_enum):
        unknown = sorted(set(declarations) - set(by_cpp_node) - set(by_cpp_enum))
        missing = sorted((set(by_cpp_node) | set(by_cpp_enum)) - set(declarations))
        if unknown:
            fail("Unmapped declarations in Clava inventory: " + ", ".join(unknown))
        fail("Metadata declarations absent from Clava inventory: " + ", ".join(missing))
    if len(nodes) == 0:
        fail("metadata.nodes must not be empty")

    for cpp_type, node in by_cpp_node.items():
        declaration = declarations[cpp_type]
        member_items = require_list(declaration.get("members"), f"{cpp_type}.members")
        members: dict[str, str] = {}
        for member in member_items:
            entry = require_object(member, f"{cpp_type} member")
            name = required_string(entry.get("name"), f"{cpp_type}.member.name")
            type_name = required_string(entry.get("type"), f"{cpp_type}.{name}.type")
            if name in members:
                fail(f"Duplicate member {name} in Clava inventory for {cpp_type}")
            members[name] = normalized_cpp_type(type_name)

        ignored = require_object(node.get("ignored_members"), f"{cpp_type}.ignored_members")
        for member_name, reason in ignored.items():
            if member_name not in members:
                fail(f"Ignored member {member_name!r} is absent from {cpp_type}")
            required_string(reason, f"{cpp_type}.ignored_members.{member_name} reason")

        fields = require_list(node.get("fields"), f"{cpp_type}.fields")
        if not fields:
            fail(f"Node {cpp_type} must generate at least one field")
        tags: set[int] = set()
        mapped_members: set[str] = set(ignored)
        for field in fields:
            entry = require_object(field, f"{cpp_type} field")
            name = required_string(entry.get("name"), f"{cpp_type}.field.name")
            if not IDENT.fullmatch(name):
                fail(f"Invalid protobuf field name in {cpp_type}: {name}")
            tag = positive_int(entry.get("number"), f"{cpp_type}.{name}.number")
            if tag in tags:
                fail(f"Duplicate field number {tag} in {cpp_type}")
            tags.add(tag)
            member_name = required_string(entry.get("source_member"), f"{cpp_type}.{name}.source_member")
            if member_name not in members:
                fail(f"Field {cpp_type}.{name} maps missing C++ member {member_name}")
            if member_name in mapped_members:
                fail(f"C++ member {cpp_type}.{member_name} is mapped more than once")
            mapped_members.add(member_name)
            proto_type = required_string(entry.get("proto_type"), f"{cpp_type}.{name}.proto_type")
            source_type = members[member_name]
            if proto_type in PROTO_SCALARS:
                if source_type not in PROTO_SCALARS[proto_type]:
                    fail(f"Unsupported type mapping for {cpp_type}.{member_name}: {source_type} -> {proto_type}")
            elif proto_type in by_proto_enum:
                if source_type != normalized_cpp_type(by_proto_enum[proto_type]["cpp_type"]):
                    fail(f"Enum type mismatch for {cpp_type}.{member_name}: {source_type} -> {proto_type}")
            elif proto_type in by_proto_node:
                if source_type != normalized_cpp_type(by_proto_node[proto_type]["cpp_type"]):
                    fail(f"Message type mismatch for {cpp_type}.{member_name}: {source_type} -> {proto_type}")
            else:
                fail(f"Unsupported protobuf type in {cpp_type}.{name}: {proto_type}")

            presence_member = entry.get("presence_member")
            if presence_member is not None:
                presence_member = required_string(presence_member, f"{cpp_type}.{name}.presence_member")
                if presence_member not in members or members[presence_member] != "bool":
                    fail(f"Presence member {cpp_type}.{presence_member} must be a discovered bool field")
                if presence_member in mapped_members:
                    fail(f"Presence member {cpp_type}.{presence_member} is mapped more than once")
                if proto_type not in PROTO_SCALARS:
                    fail(f"presence_member is supported only for scalar fields: {cpp_type}.{name}")
                mapped_members.add(presence_member)
        if mapped_members != set(members):
            unaccounted = sorted(set(members) - mapped_members)
            fail(f"Unmapped C++ members in {cpp_type}: " + ", ".join(unaccounted))

    for cpp_type, enum in by_cpp_enum.items():
        declaration_names = {entry["name"] for entry in require_list(declarations[cpp_type].get("constants"), f"{cpp_type}.constants")}
        metadata_names = {entry["cpp_name"] for entry in require_list(enum.get("values"), f"{cpp_type}.values")}
        if declaration_names != metadata_names:
            missing = sorted(declaration_names - metadata_names)
            stale = sorted(metadata_names - declaration_names)
            details = []
            if missing:
                details.append("unmapped constants: " + ", ".join(missing))
            if stale:
                details.append("constants absent from Clava: " + ", ".join(stale))
            fail(f"Enum {cpp_type} does not have complete explicit mapping ({'; '.join(details)})")

    return {
        "package": package,
        "header_include": header_include,
        "nodes": sorted(nodes, key=lambda node: (node["kind_number"], node["cpp_type"])),
        "enums": sorted(enums, key=lambda enum: (enum["proto_name"], enum["cpp_type"])),
        "by_cpp_node": by_cpp_node,
        "by_proto_node": by_proto_node,
        "by_cpp_enum": by_cpp_enum,
        "by_proto_enum": by_proto_enum,
        "declarations": declarations,
    }


def render_proto(plan: dict[str, Any], digest: str) -> str:
    package = plan["package"]
    lines = [
        "syntax = \"proto3\";",
        "",
        f"// Generated by generator/generate.py; probe only, not the production wire protocol.",
        f"// Inputs SHA-256: {digest}",
        f"package {package};",
        "",
        "enum NodeKind {",
        "  NODE_KIND_UNSPECIFIED = 0;",
    ]
    for node in plan["nodes"]:
        lines.append(f"  {node['kind_name']} = {node['kind_number']};")
    lines.extend(["}", ""])

    for enum in plan["enums"]:
        lines.extend([f"enum {enum['proto_name']} {{", f"  {enum['zero_name']} = 0;"])
        for value in sorted(enum["values"], key=lambda item: item["number"]):
            lines.append(f"  {value['proto_name']} = {value['number']};")
        lines.extend(["}", ""])

    for node in plan["nodes"]:
        lines.append(f"message {node['proto_name']} {{")
        for field in sorted(node["fields"], key=lambda item: item["number"]):
            prefix = "optional " if field.get("presence_member") else ""
            lines.append(f"  {prefix}{field['proto_type']} {field['name']} = {field['number']};")
        lines.extend(["}", ""])
    return "\n".join(lines) + "\n"


def cpp_qualified(package: str) -> str:
    return "::" + "::".join(package.split("."))


def render_producer(plan: dict[str, Any], digest: str) -> str:
    proto_ns = cpp_qualified(plan["package"])
    lines = [
        "// Generated by generator/generate.py; probe fragment only, not the production producer.",
        f"// Inputs SHA-256: {digest}",
        f'#include "{plan["header_include"]}"',
        f'#include "{Path(SCHEMA_FILENAME).with_suffix(".pb.h").name}"',
        "#include <stdexcept>",
        "",
        f"namespace {plan['package'].replace('.', '::')} {{",
        "",
    ]

    for enum in plan["enums"]:
        source_enum = "::" + enum["cpp_type"].removeprefix("::")
        lines.extend([
            f"static {proto_ns}::{enum['proto_name']} map_{enum['proto_name']}({source_enum} value) {{",
            "  switch (value) {",
        ])
        for value in sorted(enum["values"], key=lambda item: item["number"]):
            lines.append(f"    case {source_enum}::{value['cpp_name']}: return {proto_ns}::{value['proto_name']};")
        lines.extend([
            "  }",
            f'  throw std::invalid_argument("Unknown value for {enum["cpp_type"]}");',
            "}",
            "",
        ])

    for node in plan["nodes"]:
        source_type = "::" + node["cpp_type"].removeprefix("::")
        lines.append(f"static void encode_{node['proto_name']}(const {source_type}& node, {proto_ns}::{node['proto_name']}* out);")
    lines.append("")

    for node in plan["nodes"]:
        source_type = "::" + node["cpp_type"].removeprefix("::")
        lines.extend([
            f"static void encode_{node['proto_name']}(const {source_type}& node, {proto_ns}::{node['proto_name']}* out) {{",
            "  out->Clear();",
        ])
        for field in sorted(node["fields"], key=lambda item: item["number"]):
            member_expr = f"node.{field['source_member']}"
            set_statement: str
            if field["proto_type"] in PROTO_SCALARS:
                set_statement = f"out->set_{field['name']}({member_expr});"
            elif field["proto_type"] in plan["by_proto_enum"]:
                set_statement = f"out->set_{field['name']}(map_{field['proto_type']}({member_expr}));"
            else:
                set_statement = f"encode_{field['proto_type']}({member_expr}, out->mutable_{field['name']}());"
            if field.get("presence_member"):
                lines.append(f"  if (node.{field['presence_member']}) {{ {set_statement} }}")
            else:
                lines.append(f"  {set_statement}")
        lines.extend(["}", ""])
    lines.extend([f"}} // namespace {plan['package'].replace('.', '::')}", ""])
    return "\n".join(lines) + "\n"


def resolve_clava_command(command: str | None) -> list[str]:
    raw = command or os.environ.get("FLANG_GENERATOR_CLAVA_COMMAND")
    if raw:
        parsed = shlex.split(raw)
        if not parsed:
            fail("Clava command is empty")
        return parsed
    executable = shutil.which("clava")
    if executable:
        return [executable, "classic"]
    fail("Clava was not found. Pass --clava-command 'node /path/to/Clava-JS/code/index.ts classic' or set FLANG_GENERATOR_CLAVA_COMMAND")


def run_clava(header: Path, header_root: Path, output_model: Path, command: str | None, query_module: str | None) -> None:
    if not header.is_file():
        fail(f"Header does not exist: {header}")
    try:
        header.relative_to(header_root)
    except ValueError:
        fail(f"Header {header} must be beneath --header-root {header_root}")
    query_path = query_module or os.environ.get("FLANG_GENERATOR_QUERY_MODULE")
    if not query_path or not Path(query_path).is_file():
        fail("Clava Query module is not known. Pass --query-module /path/to/lara-framework/Lara-JS/api/weaver/Query.ts")
    prefix = resolve_clava_command(command)
    invocation = prefix + [
        str(ANALYZER),
        "-p", str(header.parent),
        "-std", "c++20",
        "-fs", "-I" + str(header_root) + " -I" + str(header.parent),
        "-ncg",
    ]
    environment = os.environ.copy()
    environment.update({
        "FLANG_GENERATOR_HEADER": str(header.resolve()),
        "FLANG_GENERATOR_HEADER_ROOT": str(header_root.resolve()),
        "FLANG_GENERATOR_MODEL_OUT": str(output_model.resolve()),
        "FLANG_GENERATOR_QUERY_MODULE": str(Path(query_path).resolve()),
    })
    result = subprocess.run(invocation, cwd=ROOT.parent, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        detail = result.stdout.rstrip()
        fail(f"Clava header analysis failed with exit code {result.returncode}" + (f":\n{detail}" if detail else ""))
    if not output_model.is_file():
        fail("Clava completed without writing the declaration inventory")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--header", type=Path, default=DEFAULT_HEADER, help="header to analyze with Clava (default: generator fixture)")
    parser.add_argument("--header-root", type=Path, default=ROOT, help="root used to normalize source paths and include the header")
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA, help="reviewed semantic and stable-number manifest")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "generated", help="directory for deterministic generated outputs")
    parser.add_argument("--model", type=Path, help="use an existing Clava inventory instead of invoking Clava")
    parser.add_argument("--clava-command", help="Clava command prefix, for example 'node /path/Clava-JS/code/index.ts classic'")
    parser.add_argument("--query-module", help="absolute path to Clava's Lara Query.ts module")
    args = parser.parse_args(argv)

    try:
        metadata = require_object(read_json(args.metadata, "metadata"), "metadata")
        with tempfile.TemporaryDirectory(prefix="flang-generator-") as temporary_directory:
            raw_model_path = args.model.resolve() if args.model else Path(temporary_directory) / MODEL_FILENAME
            if not args.model:
                header = args.header.resolve()
                header_root = args.header_root.resolve()
                if not header_root.is_dir():
                    fail(f"Header root does not exist or is not a directory: {header_root}")
                run_clava(header, header_root, raw_model_path, args.clava_command, args.query_module)
            model = require_object(read_json(raw_model_path, "Clava model"), "Clava model")
            try:
                header_digest = hashlib.sha256(args.header.read_bytes()).hexdigest()
            except OSError as error:
                fail(f"Cannot read analyzed header {args.header}: {error}")
            source_header = require_object(model.get("source_header"), "model.source_header")
            if source_header.get("sha256") != header_digest:
                fail(f"Clava model is stale for header {args.header}: SHA-256 differs")
            plan = validate_manifest(model, metadata)
            digest_source = {"model": model, "metadata": metadata}
            input_digest = hashlib.sha256(canonical_json(digest_source)).hexdigest()
            output_dir = args.output_dir.resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / MODEL_FILENAME).write_bytes(canonical_json(model))
            (output_dir / SCHEMA_FILENAME).write_text(render_proto(plan, input_digest), encoding="utf-8", newline="\n")
            (output_dir / PRODUCER_FILENAME).write_text(render_producer(plan, input_digest), encoding="utf-8", newline="\n")
            print(f"Generated {SCHEMA_FILENAME}, {PRODUCER_FILENAME}, and {MODEL_FILENAME} in {output_dir}")
            print(f"Input SHA-256: {input_digest}")
            print("Scope: generator probe only; no Flang coverage or production wire contract")
    except GenerationError as error:
        print(f"generation error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
