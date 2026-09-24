#!/usr/bin/env python3
"""Create or extend a reviewed candidate Flang handler kind manifest.

Initial IDs are assigned in sorted C++ type-name order. When an existing
manifest is supplied, its IDs and handler kinds stay fixed and newly registered
types receive consecutive IDs after the current maximum, in sorted name order.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence


INVENTORY_SCHEMA_VERSION = 1
MANIFEST_FORMAT = "flang-kind-manifest/v1"
HANDLER_KINDS = {"node", "manual_node", "enum"}
_NO_EXISTING = object()
REGISTRATION_KINDS = {
    "DUMP_NODE": ("node", False),
    "DUMP_NODE_MANUAL": ("manual_node", True),
    "DUMP_ENUM": ("enum", False),
}
QUALIFIED_NAME = re.compile(
    r"^[A-Za-z_][A-Za-z_0-9]*(?:::[A-Za-z_][A-Za-z_0-9]*)*(?:\s*<.*>)?$"
)


class ManifestError(ValueError):
    """An input inventory or existing manifest is malformed or inconsistent."""


def _object(value: Any, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{description} must be a JSON object")
    return value


def _array(value: Any, description: str) -> list[Any]:
    if not isinstance(value, list):
        raise ManifestError(f"{description} must be a JSON array")
    return value


def _qualified_type(value: Any, description: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or "::" not in value
        or not QUALIFIED_NAME.fullmatch(value)
    ):
        raise ManifestError(f"{description} must be a fully qualified C++ type name")
    return value


def read_inventory(document: Any) -> dict[str, str]:
    """Validate a handler registration inventory and return name -> kind."""
    root = _object(document, "registration inventory")
    if set(root) != {"schema_version", "registrations"}:
        raise ManifestError(
            "registration inventory must contain exactly ['registrations', 'schema_version']"
        )
    version = root.get("schema_version")
    if isinstance(version, bool) or version != INVENTORY_SCHEMA_VERSION:
        raise ManifestError(f"registration inventory schema_version must be {INVENTORY_SCHEMA_VERSION}")

    registrations = _array(root.get("registrations"), "registrations")
    if not registrations:
        raise ManifestError("registration inventory must contain at least one registration")
    result: dict[str, str] = {}
    expected_keys = {
        "fully_qualified_type",
        "handler_kind",
        "has_explicit_content",
        "manual",
        "registration",
        "source_line",
    }
    for index, raw in enumerate(registrations):
        description = f"registrations[{index}]"
        item = _object(raw, description)
        if set(item) != expected_keys:
            raise ManifestError(f"{description} must contain exactly {sorted(expected_keys)}")
        type_name = _qualified_type(item.get("fully_qualified_type"), f"{description}.fully_qualified_type")
        registration = item.get("registration")
        if not isinstance(registration, str) or registration not in REGISTRATION_KINDS:
            raise ManifestError(f"{description}.registration is unsupported: {registration!r}")
        expected_handler, expected_manual = REGISTRATION_KINDS[registration]
        handler_kind = item.get("handler_kind")
        if not isinstance(handler_kind, str) or handler_kind not in HANDLER_KINDS:
            raise ManifestError(f"{description}.handler_kind is unsupported: {handler_kind!r}")
        if handler_kind != expected_handler:
            raise ManifestError(
                f"{description}.handler_kind must be {expected_handler!r} for {registration}"
            )
        if item.get("manual") is not expected_manual:
            raise ManifestError(f"{description}.manual must be {expected_manual} for {registration}")
        if not isinstance(item.get("has_explicit_content"), bool):
            raise ManifestError(f"{description}.has_explicit_content must be a boolean")
        source_line = item.get("source_line")
        if isinstance(source_line, bool) or not isinstance(source_line, int) or source_line < 1:
            raise ManifestError(f"{description}.source_line must be a positive integer")
        if type_name in result:
            raise ManifestError(f"duplicate registration for {type_name}")
        result[type_name] = handler_kind
    return result


def read_manifest(document: Any) -> list[dict[str, Any]]:
    """Validate canonical existing manifest structure and consecutive IDs."""
    root = _object(document, "existing kind manifest")
    if set(root) != {"format", "kinds"}:
        raise ManifestError("existing kind manifest must contain exactly ['format', 'kinds']")
    if root.get("format") != MANIFEST_FORMAT:
        raise ManifestError(f"existing kind manifest format must be {MANIFEST_FORMAT!r}")

    kinds = _array(root.get("kinds"), "existing kind manifest.kinds")
    ids: list[int] = []
    names: set[str] = set()
    expected_keys = {"id", "cpp_type", "handler_kind"}
    for index, raw in enumerate(kinds):
        description = f"existing kind manifest.kinds[{index}]"
        item = _object(raw, description)
        if set(item) != expected_keys:
            raise ManifestError(f"{description} must contain exactly ['cpp_type', 'handler_kind', 'id']")
        kind_id = item.get("id")
        if isinstance(kind_id, bool) or not isinstance(kind_id, int) or kind_id < 1:
            raise ManifestError(f"{description}.id must be a positive integer")
        ids.append(kind_id)
        type_name = _qualified_type(item.get("cpp_type"), f"{description}.cpp_type")
        if type_name in names:
            raise ManifestError(f"duplicate cpp_type in existing kind manifest: {type_name}")
        names.add(type_name)
        handler_kind = item.get("handler_kind")
        if not isinstance(handler_kind, str) or handler_kind not in HANDLER_KINDS:
            raise ManifestError(
                f"{description}.handler_kind is unsupported: {handler_kind!r}"
            )

    expected_ids = list(range(1, len(kinds) + 1))
    if ids != expected_ids:
        if len(set(ids)) != len(ids):
            raise ManifestError("existing kind manifest contains an ID collision")
        raise ManifestError("existing kind manifest IDs must be sorted and consecutive from 1")
    return kinds


def build_manifest(inventory_document: Any, existing_document: Any = _NO_EXISTING) -> dict[str, Any]:
    """Build initial sorted IDs or append new names to an existing manifest."""
    registrations = read_inventory(inventory_document)
    if existing_document is _NO_EXISTING:
        ordered_names = sorted(registrations)
        kinds = [
            {"id": index, "cpp_type": name, "handler_kind": registrations[name]}
            for index, name in enumerate(ordered_names, start=1)
        ]
        return {"format": MANIFEST_FORMAT, "kinds": kinds}

    existing = read_manifest(existing_document)
    existing_by_name = {item["cpp_type"]: item for item in existing}
    missing = sorted(set(existing_by_name) - set(registrations))
    if missing:
        raise ManifestError(
            "existing cpp_type is missing from the registration inventory "
            "(removal or rename is not allowed): " + ", ".join(missing)
        )
    for name, item in existing_by_name.items():
        current_kind = registrations[name]
        if current_kind != item["handler_kind"]:
            raise ManifestError(
                f"handler_kind changed for {name}: {item['handler_kind']} -> {current_kind}"
            )

    kinds = [dict(item) for item in existing]
    next_id = len(kinds) + 1
    for name in sorted(set(registrations) - set(existing_by_name)):
        kinds.append({"id": next_id, "cpp_type": name, "handler_kind": registrations[name]})
        next_id += 1
    return {"format": MANIFEST_FORMAT, "kinds": kinds}


def _read_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ManifestError(f"cannot read {description} {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ManifestError(f"invalid JSON in {description} {path}: {error}") from error


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path, help="JSON from inventory_dump_handlers.py")
    parser.add_argument("--existing", type=Path, help="existing flang-kind-manifest/v1 to preserve")
    parser.add_argument("--output", type=Path, required=True, help="write the candidate manifest here")
    args = parser.parse_args(argv)

    try:
        output_path = args.output.resolve()
        input_paths = {args.inventory.resolve()}
        if args.existing is not None:
            input_paths.add(args.existing.resolve())
        if output_path in input_paths:
            raise ManifestError("output path must not overwrite an input file")
        inventory = _read_json(args.inventory, "registration inventory")
        existing = _read_json(args.existing, "existing kind manifest") if args.existing else _NO_EXISTING
        manifest = build_manifest(inventory, existing)
        serialized = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8", newline="\n")
    except ManifestError as error:
        print(f"kind manifest error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"kind manifest error: {error}", file=sys.stderr)
        return 2

    print(f"Wrote {len(manifest['kinds'])} kind IDs to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
