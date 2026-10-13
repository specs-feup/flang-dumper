#!/usr/bin/env python3
"""Validate the pinned Flang 22 model and generate production artifacts.

The protocol schema remains the generic graph schema in protocol/ast_stream.proto.
This command validates the Flang inventory against reviewed registration/kind
metadata, regenerates the production visitor/kind/catalog artifacts, and runs
protoc for the selected language outputs. It does not invent per-node messages
for declarations without reviewed serialization mappings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

sys.dont_write_bytecode = True


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = REPO_ROOT / "generator"
SCRIPTS_DIR = REPO_ROOT / "scripts"
DRIVER_SCRIPT = REPO_ROOT / "clava_driver" / "driver.mjs"
DEFAULT_PIN = GENERATOR_DIR / "flang22-declarations.json"
DEFAULT_REGISTRATIONS = GENERATOR_DIR / "registrations.json"
DEFAULT_KINDS = GENERATOR_DIR / "kinds.json"
DEFAULT_BODIES = GENERATOR_DIR / "handler_bodies.json"
DEFAULT_IGNORE_LIST = REPO_ROOT / "tests" / "baseline" / "handler_coverage_ignores.json"
DEFAULT_SCHEMA = REPO_ROOT / "protocol" / "ast_stream.proto"
HEADER_FILTERS = (
    ("flang/Parser/parse-tree.h", "Fortran::parser"),
    ("flang/Support/Fortran.h", "Fortran::common"),
    ("flang/Parser/format-specification.h", "Fortran::format"),
)
INLINE_NAMESPACES = (
    "Fortran::parser::arguments",
    "Fortran::parser::traits",
    "Fortran::parser::modifier",
)

for directory in (GENERATOR_DIR, SCRIPTS_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import build_flang22_model  # noqa: E402
import generate_enum_catalogs  # noqa: E402
import generate_kind_header  # noqa: E402
import generate_visitor_registrations  # noqa: E402
import merge_inventories  # noqa: E402
from audit_handler_coverage import AuditInputError, audit_coverage  # noqa: E402
from check_registered_coverage import check_registered_coverage  # noqa: E402


class ProductionGenerationError(ValueError):
    """The production generation inputs are stale, malformed, or unsupported."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ProductionGenerationError(f"cannot read {label} {path}: {error}") from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ProductionGenerationError(f"invalid {label} JSON in {path}: {error}") from error


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ProductionGenerationError(f"cannot read input {path}: {error}") from error


def _clava_failure_detail(output: str) -> str:
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    relevant = [
        line.strip()
        for line in lines
        if "Could not decode protobuf AST for" in line
        or "Unsupported emitted node class" in line
        or "Expected file to be a folder" in line
        or "error:" in line.lower()
    ]
    unique: list[str] = []
    for line in relevant:
        if line not in unique:
            unique.append(line)
    if unique:
        return "\n".join(unique[:8])
    return "\n".join(lines[-32:])


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def validate_metadata(
    registrations_path: Path,
    kinds_path: Path,
    bodies_path: Path,
) -> tuple[Any, Any, Any, str, str, str]:
    """Parse every reviewed manifest and validate its cross-file contracts."""
    registrations = _read_json(registrations_path, "registration manifest")
    kinds = _read_json(kinds_path, "kind manifest")
    bodies = _read_json(bodies_path, "handler-body manifest")
    visitor = generate_visitor_registrations.render_include(kinds, registrations, bodies)
    catalogs = generate_enum_catalogs.render_include(registrations)
    kind_header = generate_kind_header.render_header(kinds)
    return registrations, kinds, bodies, visitor, catalogs, kind_header


def _verify_live_source_hashes(model: dict[str, Any], header_root: Path) -> None:
    source_header = model.get("source_header")
    if not isinstance(source_header, dict) or not isinstance(source_header.get("file"), str):
        raise ProductionGenerationError("pinned inventory has no source_header.file")
    files: dict[str, str] = {}
    for item in model.get("source_files", []):
        if not isinstance(item, dict) or not isinstance(item.get("file"), str):
            raise ProductionGenerationError("pinned inventory has an invalid source_files entry")
        files[item["file"]] = item.get("sha256")
    files.setdefault(source_header["file"], source_header.get("sha256"))

    stale: list[str] = []
    for relative, expected in sorted(files.items()):
        source = (header_root / relative).resolve()
        try:
            source.relative_to(header_root.resolve())
        except ValueError:
            raise ProductionGenerationError(f"pinned source path escapes header root: {relative}")
        if not source.is_file():
            stale.append(f"{relative}: missing")
            continue
        actual = _sha256(source)
        if actual != expected:
            stale.append(f"{relative}: expected {expected}, found {actual}")
    if stale:
        raise ProductionGenerationError("pinned Flang header input is stale or mismatched:\n  " + "\n  ".join(stale))


def validate_model_against_pin(
    model: dict[str, Any],
    pinned_model: dict[str, Any],
    header_root: Path,
    include_dir: Path,
) -> None:
    """Reject source drift and any AST model differing from the reviewed pin."""
    _verify_live_source_hashes(pinned_model, header_root)
    expected_header = include_dir / HEADER_FILTERS[0][0]
    pinned_header = (header_root / pinned_model["source_header"]["file"]).resolve()
    if expected_header.resolve() != pinned_header:
        raise ProductionGenerationError(
            "--include-dir does not identify the pinned Flang 22 parse-tree.h: "
            f"expected {pinned_header}, got {expected_header.resolve()}"
        )
    if _canonical_json(model) != _canonical_json(pinned_model):
        expected_names = {item.get("qualified_name") for item in pinned_model.get("declarations", [])}
        actual_names = {item.get("qualified_name") for item in model.get("declarations", [])}
        missing = sorted(expected_names - actual_names)
        added = sorted(actual_names - expected_names)
        details: list[str] = []
        if missing:
            details.append("missing declarations: " + ", ".join(missing[:12]))
        if added:
            details.append("new declarations: " + ", ".join(added[:12]))
        raise ProductionGenerationError(
            "fresh analyzer model differs from generator/flang22-declarations.json"
            + (" (" + "; ".join(details) + ")" if details else " (member/type/location data differs)")
        )


def _clava_model(
    *,
    header_root: Path,
    include_dir: Path,
    clava_entry: Path,
    query_module: Path,
    python_cwd: Path,
) -> dict[str, Any]:
    if not clava_entry.is_file():
        raise ProductionGenerationError(f"Clava entry does not exist: {clava_entry}")
    if not query_module.is_file():
        raise ProductionGenerationError(f"Clava Query module does not exist: {query_module}")
    node = shutil.which("node")
    if node is None:
        raise ProductionGenerationError("Node.js is required to invoke the selected Clava entry")

    inventories: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="flang22-clava-") as temporary:
        temporary_dir = Path(temporary)
        for index, (relative_header, qualified_prefix) in enumerate(HEADER_FILTERS):
            header = include_dir / relative_header
            if not header.is_file():
                raise ProductionGenerationError(f"pinned Flang header does not exist: {header}")
            probe_dir = temporary_dir / f"probe-{index}"
            probe_dir.mkdir()
            probe_source = probe_dir / "probe.cpp"
            probe_include = Path(relative_header).as_posix()
            probe_source.write_text(f'#include "{probe_include}"\n', encoding="utf-8", newline="\n")
            output_model = temporary_dir / f"inventory-{index}.json"
            # Keep Flang's quoted includes user-visible; use the system path for angle includes.
            flags = f"-iquote {include_dir} -isystem {include_dir}"
            invocation = [
                node,
                str(clava_entry.resolve()),
                "classic",
                str(DRIVER_SCRIPT),
                "-p",
                str(probe_dir),
                "-std",
                "c++20",
                "-fs",
                flags,
                "-ist",
                "0",
                "-ncg",
            ]
            environment = os.environ.copy()
            environment.update(
                {
                    "FLANG_GENERATOR_REPO_ROOT": str(REPO_ROOT),
                    "FLANG_GENERATOR_HEADER": str(header.resolve()),
                    "FLANG_GENERATOR_HEADER_ROOT": str(header_root.resolve()),
                    "FLANG_GENERATOR_MODEL_OUT": str(output_model),
                    "FLANG_GENERATOR_QUERY_MODULE": str(query_module.resolve()),
                    "FLANG_GENERATOR_QUALIFIED_PREFIX": qualified_prefix,
                }
            )
            print(f"[production] Clava analysis {index + 1}/{len(HEADER_FILTERS)}: {header}", flush=True)
            result = subprocess.run(
                invocation,
                cwd=python_cwd,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if result.returncode != 0:
                detail = _clava_failure_detail(result.stdout)
                raise ProductionGenerationError(
                    f"selected Clava analyzer failed for {relative_header} with exit code {result.returncode}"
                    + (f":\n{detail}" if detail else "")
                )
            if not output_model.is_file():
                raise ProductionGenerationError(
                    f"Clava completed without writing its inventory for {relative_header}"
                )
            inventories.append(_read_json(output_model, f"Clava inventory for {relative_header}"))

    try:
        return merge_inventories.merge_inventories(inventories)
    except merge_inventories.MergeError as error:
        raise ProductionGenerationError(f"Clava inventories could not be merged: {error}") from error


def _protoc(
    *,
    protoc: Path,
    schema: Path,
    output_dir: Path,
    java: bool,
) -> tuple[str, list[Path]]:
    if not protoc.is_file() or not os.access(protoc, os.X_OK):
        raise ProductionGenerationError(f"protoc is not an executable file: {protoc}")
    version = subprocess.run(
        [str(protoc), "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if version.returncode != 0:
        raise ProductionGenerationError(f"protoc --version failed: {version.stdout.rstrip()}")
    cpp_out = output_dir / "protoc" / "cpp"
    cpp_out.mkdir(parents=True, exist_ok=True)
    outputs = [cpp_out / "ast_stream.pb.h", cpp_out / "ast_stream.pb.cc"]
    java_output = output_dir / "protoc" / "java" / "flang_dumper" / "protocol" / "AstStream.java"
    for old_output in (*outputs, java_output):
        old_output.unlink(missing_ok=True)
    invocation = [
        str(protoc),
        f"--proto_path={schema.parent}",
        f"--cpp_out={cpp_out}",
    ]
    java_out = output_dir / "protoc" / "java"
    if java:
        java_out.mkdir(parents=True, exist_ok=True)
        invocation.append(f"--java_out={java_out}")
        outputs.append(java_output)
    invocation.append(schema.name)
    result = subprocess.run(
        invocation,
        cwd=schema.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise ProductionGenerationError(f"protoc failed with exit code {result.returncode}:\n{result.stdout.rstrip()}")
    missing = [path for path in outputs if not path.is_file()]
    if missing:
        raise ProductionGenerationError("protoc completed without writing: " + ", ".join(map(str, missing)))
    return version.stdout.strip(), outputs


def generate(
    *,
    analyzer: str,
    header_root: Path,
    include_dir: Path,
    output_dir: Path,
    protoc: Path,
    clava_entry: Path | None = None,
    query_module: Path | None = None,
    model_path: Path | None = None,
    clang_command: str = "clang++-21",
    registrations_path: Path = DEFAULT_REGISTRATIONS,
    kinds_path: Path = DEFAULT_KINDS,
    bodies_path: Path = DEFAULT_BODIES,
    ignore_list_path: Path = DEFAULT_IGNORE_LIST,
    schema_path: Path = DEFAULT_SCHEMA,
    pinned_model_path: Path = DEFAULT_PIN,
    generate_java: bool = False,
) -> dict[str, Any]:
    header_root = header_root.resolve()
    include_dir = include_dir.resolve()
    if not header_root.is_dir():
        raise ProductionGenerationError(f"header root does not exist: {header_root}")
    if not include_dir.is_dir():
        raise ProductionGenerationError(f"Flang include directory does not exist: {include_dir}")
    if not schema_path.is_file():
        raise ProductionGenerationError(f"production protobuf schema does not exist: {schema_path}")

    registrations, kinds, bodies, visitor, catalogs, kind_header = validate_metadata(
        registrations_path, kinds_path, bodies_path
    )
    pinned_model = _read_json(pinned_model_path, "pinned Flang declaration model")
    if analyzer == "clang":
        model = build_flang22_model.build_model(
            header_root=header_root,
            include_dir=include_dir,
            clang_command=clang_command,
        )
    elif analyzer == "clava":
        if clava_entry is None or query_module is None:
            raise ProductionGenerationError("Clava mode requires both --clava-entry and --query-module")
        model = _clava_model(
            header_root=header_root,
            include_dir=include_dir,
            clava_entry=clava_entry,
            query_module=query_module,
            python_cwd=REPO_ROOT,
        )
    elif analyzer == "snapshot":
        if model_path is None:
            raise ProductionGenerationError("snapshot mode requires --inventory")
        model = _read_json(model_path, "saved declaration inventory")
    else:
        raise ProductionGenerationError(f"unsupported analyzer: {analyzer}")

    if not isinstance(model, dict):
        raise ProductionGenerationError("declaration model must be a JSON object")
    validate_model_against_pin(model, pinned_model, header_root, include_dir)

    try:
        coverage = audit_coverage(
            registrations,
            model,
            _read_json(ignore_list_path, "handler coverage ignore list"),
            inline_namespaces=INLINE_NAMESPACES,
        )
        coverage_summary = check_registered_coverage(
            registrations,
            model,
            _read_json(ignore_list_path, "handler coverage ignore list"),
        )
    except AuditInputError as error:
        raise ProductionGenerationError(f"handler coverage validation failed: {error}") from error
    if not coverage_summary["ok"]:
        raise ProductionGenerationError(
            "registered handler coverage does not match the reviewed manifest: "
            + json.dumps(coverage_summary, sort_keys=True)
        )

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_bytes(output_dir / "declarations.json", (json.dumps(model, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    _write_bytes(output_dir / "handler-coverage.json", (json.dumps(coverage, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    _write_bytes(output_dir / "generated_visitor_registrations.inc", visitor.encode("utf-8"))
    _write_bytes(output_dir / "generated_binary_enum_catalogs.inc", catalogs.encode("utf-8"))
    _write_bytes(output_dir / "ast_kinds.hpp", kind_header.encode("utf-8"))
    schema_bytes = schema_path.read_bytes()
    schema_output = output_dir / "ast_stream.proto"
    _write_bytes(schema_output, schema_bytes)

    protoc_version, protoc_outputs = _protoc(
        protoc=protoc.resolve(), schema=schema_output, output_dir=output_dir, java=generate_java
    )

    input_paths = {
        "generator/flang22-declarations.json": pinned_model_path,
        "generator/registrations.json": registrations_path,
        "generator/kinds.json": kinds_path,
        "generator/handler_bodies.json": bodies_path,
        "tests/baseline/handler_coverage_ignores.json": ignore_list_path,
        "protocol/ast_stream.proto": schema_path,
    }
    generation_manifest = {
        "format": "flang-production-generation/v1",
        "analysis_mode": analyzer,
        "inputs_sha256": {name: _sha256(path) for name, path in sorted(input_paths.items())},
        "source_files": model.get("source_files", []),
        "coverage_summary": coverage["summary"],
        "registered_coverage_gate": coverage_summary,
        "protocol_schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
        "protoc_version": protoc_version,
        "generated_outputs": [
            "declarations.json",
            "handler-coverage.json",
            "generated_visitor_registrations.inc",
            "generated_binary_enum_catalogs.inc",
            "ast_kinds.hpp",
            "ast_stream.proto",
            *[path.relative_to(output_dir).as_posix() for path in protoc_outputs],
        ],
    }
    _write_bytes(
        output_dir / "generation.json",
        (json.dumps(generation_manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    return generation_manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analyzer", choices=("clava", "clang", "snapshot"), required=True,
                        help="select exactly one analyzer; snapshot validates a saved inventory but does not parse headers")
    parser.add_argument("--header-root", type=Path, required=True,
                        help="common root containing the extracted Flang and LLVM 22 headers")
    parser.add_argument("--include-dir", type=Path, required=True,
                        help="Flang 22 include directory containing flang/Parser/parse-tree.h")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--protoc", type=Path, required=True)
    parser.add_argument("--clava-entry", type=Path,
                        help="Clava-JS/code/index.ts; required for --analyzer clava")
    parser.add_argument("--query-module", type=Path,
                        help="Lara-JS/api/weaver/Query.ts; required for --analyzer clava")
    parser.add_argument("--clang-command", default="clang++-21")
    parser.add_argument("--inventory", type=Path,
                        help="saved model used only with --analyzer snapshot")
    parser.add_argument("--registrations", type=Path, default=DEFAULT_REGISTRATIONS)
    parser.add_argument("--kinds", type=Path, default=DEFAULT_KINDS)
    parser.add_argument("--bodies", type=Path, default=DEFAULT_BODIES)
    parser.add_argument("--ignore-list", type=Path, default=DEFAULT_IGNORE_LIST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--pinned-model", type=Path, default=DEFAULT_PIN)
    parser.add_argument("--java", action="store_true", help="also ask protoc to emit Java bindings")
    args = parser.parse_args(argv)

    if args.analyzer == "snapshot" and args.inventory is None:
        parser.error("--analyzer snapshot requires --inventory")
    if args.analyzer != "snapshot" and args.inventory is not None:
        parser.error("--inventory is allowed only with --analyzer snapshot")
    if args.analyzer == "clava" and (args.clava_entry is None or args.query_module is None):
        parser.error("--analyzer clava requires --clava-entry and --query-module")
    if args.analyzer != "clava" and (args.clava_entry is not None or args.query_module is not None):
        parser.error("--clava-entry and --query-module are allowed only with --analyzer clava")

    try:
        manifest = generate(
            analyzer=args.analyzer,
            header_root=args.header_root,
            include_dir=args.include_dir,
            output_dir=args.output_dir,
            protoc=args.protoc,
            clava_entry=args.clava_entry,
            query_module=args.query_module,
            model_path=args.inventory,
            clang_command=args.clang_command,
            registrations_path=args.registrations,
            kinds_path=args.kinds,
            bodies_path=args.bodies,
            ignore_list_path=args.ignore_list,
            schema_path=args.schema,
            pinned_model_path=args.pinned_model,
            generate_java=args.java,
        )
    except (
        ProductionGenerationError,
        build_flang22_model.ANALYZER.AnalyzerError,
        build_flang22_model.MERGER.MergeError,
        generate_enum_catalogs.EnumCatalogError,
        generate_kind_header.KindHeaderError,
        generate_kind_header.bootstrap_kind_manifest.ManifestError,
        generate_visitor_registrations.VisitorRegistrationError,
        KeyError,
        OSError,
        subprocess.SubprocessError,
        TypeError,
    ) as error:
        print(f"production generation error: {error}", file=sys.stderr)
        return 2

    print(
        "Generated production inventory, visitor/kind/enum artifacts, generic schema, "
        f"and protoc bindings in {args.output_dir.resolve()}"
    )
    summary = manifest["coverage_summary"]
    print(
        "Coverage: "
        f"{summary['matched_type_count']}/{summary['registration_count']} registered types matched; "
        f"{summary['unregistered_header_count']} Flang declarations remain without visitor registrations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
