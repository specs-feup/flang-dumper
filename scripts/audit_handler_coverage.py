#!/usr/bin/env python3
"""Audit dumper registrations against a Clava declarations.json inventory.

The audit compares normalized C++ qualified names. It reports every gap and
duplicate in JSON; per-type exceptions require a reviewed ignore-list entry
with a reason. It does not generate schemas or assign wire numbers.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


MODEL_FORMAT = "clava-declaration-inventory/v1"
IGNORE_FORMAT = "flang-handler-coverage-ignore/v1"
REGISTRATION_KINDS = {
    "DUMP_NODE": ("node", False),
    "DUMP_NODE_MANUAL": ("manual_node", True),
    "DUMP_ENUM": ("enum", False),
}
QUALIFIED_NAME = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*(?:::[A-Za-z_][A-Za-z_0-9]*)*(?:\s*<.*>)?$")
NAMESPACE_NAME = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*(?:::[A-Za-z_][A-Za-z_0-9]*)*$")
ELABORATED_PREFIX = re.compile(r"^(?:(?:struct|class)\s+|enum(?:\s+(?:class|struct))?\s+)")


class AuditInputError(ValueError):
    """An input file does not follow the inventory or ignore-list contract."""


def normalize_qualified_name(value: Any, description: str = "qualified name") -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuditInputError(f"{description} must be a non-empty string")
    name = value.strip()
    name = ELABORATED_PREFIX.sub("", name, count=1)
    name = re.sub(r"\s*::\s*", "::", name)
    name = re.sub(r"\s*([<>,*&])\s*", r"\1", name)
    name = re.sub(r"\s+", " ", name)
    name = name.removeprefix("::")
    if not QUALIFIED_NAME.fullmatch(name):
        raise AuditInputError(f"{description} is not a supported qualified C++ name: {value!r}")
    return name


def _require_object(value: Any, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuditInputError(f"{description} must be a JSON object")
    return value


def _require_list(value: Any, description: str) -> list[Any]:
    if not isinstance(value, list):
        raise AuditInputError(f"{description} must be a JSON array")
    return value


def _read_registrations(document: Any) -> list[dict[str, Any]]:
    root = _require_object(document, "registration inventory")
    if root.get("schema_version") != 1:
        raise AuditInputError("registration inventory schema_version must be 1")
    registrations: list[dict[str, Any]] = []
    for index, raw in enumerate(_require_list(root.get("registrations"), "registrations")):
        item = _require_object(raw, f"registrations[{index}]")
        macro = item.get("registration")
        if macro not in REGISTRATION_KINDS:
            raise AuditInputError(f"registrations[{index}].registration is unsupported: {macro!r}")
        expected_handler, expected_manual = REGISTRATION_KINDS[macro]
        handler = item.get("handler_kind")
        if handler != expected_handler:
            raise AuditInputError(
                f"registrations[{index}].handler_kind must be {expected_handler!r} for {macro}"
            )
        manual = item.get("manual")
        if not isinstance(manual, bool) or manual != expected_manual:
            raise AuditInputError(
                f"registrations[{index}].manual must be {expected_manual} for {macro}"
            )
        explicit_content = item.get("has_explicit_content")
        if not isinstance(explicit_content, bool):
            raise AuditInputError(f"registrations[{index}].has_explicit_content must be a boolean")
        type_name = normalize_qualified_name(
            item.get("fully_qualified_type"), f"registrations[{index}].fully_qualified_type"
        )
        line = item.get("source_line")
        if isinstance(line, bool) or not isinstance(line, int) or line < 1:
            raise AuditInputError(f"registrations[{index}].source_line must be a positive integer")
        registrations.append(
            {
                "fully_qualified_type": type_name,
                "registration": macro,
                "handler_kind": handler,
                "source_line": line,
                "manual": manual,
                "has_explicit_content": explicit_content,
            }
        )
    return registrations


def _normalize_inline_namespaces(values: list[str] | tuple[str, ...]) -> list[str]:
    namespaces: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        namespace = normalize_qualified_name(value, f"inline namespace {index + 1}")
        if not NAMESPACE_NAME.fullmatch(namespace):
            raise AuditInputError(
                f"inline namespace {index + 1} must be a qualified namespace name: {value!r}"
            )
        if namespace in seen:
            raise AuditInputError(f"duplicate inline namespace option: {namespace}")
        seen.add(namespace)
        namespaces.append(namespace)
    return namespaces


def _canonicalize_declaration_name(name: str, inline_namespaces: list[str]) -> str:
    """Remove configured inline namespace segments at their qualified prefix."""
    components = name.split("::")
    remove_indexes: set[int] = set()
    for namespace in inline_namespaces:
        namespace_components = namespace.split("::")
        if (
            len(components) > len(namespace_components)
            and components[: len(namespace_components)] == namespace_components
        ):
            remove_indexes.add(len(namespace_components) - 1)
    return "::".join(
        component for index, component in enumerate(components) if index not in remove_indexes
    )


def _read_declarations(
    document: Any, inline_namespaces: list[str]
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    root = _require_object(document, "Clava declarations model")
    if root.get("format") != MODEL_FORMAT:
        raise AuditInputError(f"Clava model format must be {MODEL_FORMAT!r}")
    source_header = _require_object(root.get("source_header"), "model.source_header")
    source_file = source_header.get("file")
    source_digest = source_header.get("sha256")
    if not isinstance(source_file, str) or not source_file.strip():
        raise AuditInputError("model.source_header.file must be a non-empty string")
    if not isinstance(source_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", source_digest):
        raise AuditInputError("model.source_header.sha256 must be a lowercase SHA-256 digest")
    declarations: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_require_list(root.get("declarations"), "model.declarations")):
        item = _require_object(raw, f"model.declarations[{index}]")
        original_name = item.get("qualified_name")
        normalized_name = normalize_qualified_name(
            original_name, f"model.declarations[{index}].qualified_name"
        )
        type_name = _canonicalize_declaration_name(normalized_name, inline_namespaces)
        kind = item.get("kind")
        if kind not in {"record", "enum"}:
            raise AuditInputError(f"model.declarations[{index}].kind must be 'record' or 'enum'")
        if type_name in declarations:
            previous = declarations[type_name]
            if previous["normalized_name"] == normalized_name:
                raise AuditInputError(
                    f"duplicate Clava declaration after name normalization: {type_name}"
                )
            previous_path = previous.get("path") or "<path unavailable>"
            location = item.get("location")
            current_path = (
                location.get("file", "<path unavailable>")
                if isinstance(location, dict)
                else "<path unavailable>"
            )
            raise AuditInputError(
                f"inline namespace canonicalization collision for {type_name}: "
                f"{previous['original_name']} ({previous_path}) and "
                f"{original_name} ({current_path})"
            )
        location = item.get("location")
        path = location.get("file") if isinstance(location, dict) else None
        declarations[type_name] = {
            "kind": kind,
            "normalized_name": normalized_name,
            "original_name": original_name,
            "path": path if isinstance(path, str) else None,
        }
    return declarations, {"file": source_file, "sha256": source_digest}


def _read_ignores(document: Any | None) -> dict[tuple[str, str], str]:
    if document is None:
        return {}
    root = _require_object(document, "coverage ignore list")
    if root.get("format") != IGNORE_FORMAT:
        raise AuditInputError(f"ignore list format must be {IGNORE_FORMAT!r}")
    unexpected_root_keys = set(root) - {"format", "reviewed", "entries"}
    if unexpected_root_keys:
        raise AuditInputError(
            "ignore list contains unsupported keys: " + ", ".join(sorted(unexpected_root_keys))
        )
    entries = _require_list(root.get("entries"), "ignore-list entries")
    if entries and root.get("reviewed") is not True:
        raise AuditInputError("non-empty ignore list must set reviewed to true")

    ignores: dict[tuple[str, str], str] = {}
    allowed_categories = {"missing_from_header", "unregistered_header"}
    for index, raw in enumerate(entries):
        item = _require_object(raw, f"ignore-list entries[{index}]")
        unexpected_entry_keys = set(item) - {"category", "fully_qualified_type", "reason"}
        if unexpected_entry_keys:
            raise AuditInputError(
                f"ignore-list entries[{index}] contains unsupported keys: "
                + ", ".join(sorted(unexpected_entry_keys))
            )
        category = item.get("category")
        if category not in allowed_categories:
            raise AuditInputError(
                f"ignore-list entries[{index}].category must be one of "
                f"{sorted(allowed_categories)}"
            )
        type_name = normalize_qualified_name(
            item.get("fully_qualified_type"),
            f"ignore-list entries[{index}].fully_qualified_type",
        )
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise AuditInputError(f"ignore-list entries[{index}].reason must be non-empty")
        key = (category, type_name)
        if key in ignores:
            raise AuditInputError(f"duplicate ignore-list entry for {category}: {type_name}")
        ignores[key] = reason.strip()
    return ignores


def audit_coverage(
    registration_document: Any,
    model_document: Any,
    ignore_document: Any | None = None,
    inline_namespaces: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    normalized_inline_namespaces = _normalize_inline_namespaces(inline_namespaces)
    registrations = _read_registrations(registration_document)
    declaration_info, source_header = _read_declarations(
        model_document, normalized_inline_namespaces
    )
    declarations = {
        name: info["kind"] for name, info in declaration_info.items()
    }
    ignores = _read_ignores(ignore_document)

    by_type: dict[str, list[dict[str, Any]]] = {}
    for registration in registrations:
        by_type.setdefault(registration["fully_qualified_type"], []).append(registration)

    duplicates = [
        {
            "fully_qualified_type": type_name,
            "registrations": [
                {"registration": item["registration"], "source_line": item["source_line"]}
                for item in rows
            ],
        }
        for type_name, rows in sorted(by_type.items())
        if len(rows) > 1
    ]

    registered_names = set(by_type)
    declaration_names = set(declarations)
    matched_names = registered_names & declaration_names
    missing_names = registered_names - declaration_names
    unregistered_names = declaration_names - registered_names

    missing_from_header = [
        {
            "fully_qualified_type": name,
            "registration_lines": [item["source_line"] for item in by_type[name]],
            "ignored": (reason := ignores.get(("missing_from_header", name))) is not None,
            **({"reason": reason} if reason is not None else {}),
        }
        for name in sorted(missing_names)
    ]
    unregistered_header = [
        {
            "fully_qualified_type": name,
            "declaration_kind": declarations[name],
            "ignored": (reason := ignores.get(("unregistered_header", name))) is not None,
            **({"reason": reason} if reason is not None else {}),
        }
        for name in sorted(unregistered_names)
    ]

    kind_mismatches = []
    for name in sorted(matched_names):
        handler_kind = by_type[name][0]["handler_kind"]
        # DUMP_NODE can visit an enum directly (Fortran::parser::Sign does).
        # DUMP_ENUM specifically requires an enum for its EnumToString loop.
        expected_kind = "enum" if handler_kind == "enum" else "record or enum"
        mismatch = declarations[name] != "enum" if handler_kind == "enum" else declarations[name] not in {"record", "enum"}
        if mismatch:
            kind_mismatches.append(
                {
                    "fully_qualified_type": name,
                    "registration_kind": expected_kind,
                    "declaration_kind": declarations[name],
                }
            )

    used_ignore_keys = {
        ("missing_from_header", item["fully_qualified_type"])
        for item in missing_from_header
        if item["ignored"]
    } | {
        ("unregistered_header", item["fully_qualified_type"])
        for item in unregistered_header
        if item["ignored"]
    }
    unused_ignores = [
        {"category": category, "fully_qualified_type": type_name, "reason": reason}
        for (category, type_name), reason in sorted(ignores.items())
        if (category, type_name) not in used_ignore_keys
    ]

    manual_count = sum(item["manual"] for item in registrations)
    explicit_count = sum(item["has_explicit_content"] for item in registrations)
    extra_content_count = sum(
        item["registration"] == "DUMP_NODE" and item["has_explicit_content"]
        for item in registrations
    )
    manual_explicit_count = sum(
        item["manual"] and item["has_explicit_content"] for item in registrations
    )
    ignored_gap_count = sum(item["ignored"] for item in missing_from_header + unregistered_header)
    unexpected_missing = sum(not item["ignored"] for item in missing_from_header)
    unexpected_unregistered = sum(not item["ignored"] for item in unregistered_header)
    ok = not (
        unexpected_missing
        or unexpected_unregistered
        or duplicates
        or kind_mismatches
        or unused_ignores
    )

    def declaration_trace(name: str) -> dict[str, Any]:
        if not normalized_inline_namespaces:
            return {}
        info = declaration_info[name]
        return {
            "declaration_qualified_name": info["original_name"],
            "declaration_path": info["path"],
        }

    report = {
        "format": "flang-handler-coverage-report/v1",
        "ok": ok,
        "source_header": source_header,
        "summary": {
            "registration_count": len(registrations),
            "unique_registered_type_count": len(registered_names),
            "declaration_count": len(declarations),
            "matched_type_count": len(matched_names),
            "missing_from_header_count": len(missing_from_header),
            "unregistered_header_count": len(unregistered_header),
            "duplicate_registration_group_count": len(duplicates),
            "kind_mismatch_count": len(kind_mismatches),
            "ignored_gap_count": ignored_gap_count,
            "unused_ignore_count": len(unused_ignores),
            "manual_registration_count": manual_count,
            "explicit_content_registration_count": explicit_count,
            "automatic_node_extra_content_count": extra_content_count,
            "manual_with_explicit_content_count": manual_explicit_count,
        },
        "matched": [
            {
                "fully_qualified_type": name,
                "registration_kind": by_type[name][0]["handler_kind"],
                "declaration_kind": declarations[name],
                **declaration_trace(name),
            }
            for name in sorted(matched_names)
        ],
        "missing_from_header": missing_from_header,
        "unregistered_header_declarations": [
            {**item, **declaration_trace(item["fully_qualified_type"])}
            for item in unregistered_header
        ],
        "duplicate_registrations": duplicates,
        "kind_mismatches": kind_mismatches,
        "unused_ignores": unused_ignores,
    }
    if normalized_inline_namespaces:
        report["inline_namespaces"] = normalized_inline_namespaces
    return report


def _read_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise AuditInputError(f"cannot read {description} {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise AuditInputError(f"invalid JSON in {description} {path}: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registrations", type=Path, help="JSON from inventory_dump_handlers.py")
    parser.add_argument("declarations", type=Path, help="Clava declarations.json model")
    parser.add_argument("--ignore-list", type=Path, help="reviewed exact-name gap exceptions")
    parser.add_argument(
        "--inline-namespace",
        action="append",
        default=[],
        metavar="QUALIFIED_NAMESPACE",
        help="elide this inline namespace from declaration names (repeatable)",
    )
    args = parser.parse_args(argv)
    try:
        registration_document = _read_json(args.registrations, "registration inventory")
        model_document = _read_json(args.declarations, "Clava declarations model")
        ignore_document = _read_json(args.ignore_list, "coverage ignore list") if args.ignore_list else None
        report = audit_coverage(
            registration_document,
            model_document,
            ignore_document,
            inline_namespaces=args.inline_namespace,
        )
    except AuditInputError as error:
        print(f"coverage audit error: {error}", file=sys.stderr)
        return 2

    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
