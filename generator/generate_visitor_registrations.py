#!/usr/bin/env python3
"""Generate the visitor macro registrations from reviewed JSON inputs."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
KIND_FORMAT = "flang-kind-manifest/v1"
BODY_FORMAT = "flang-handler-bodies/v1"
REGISTRATION_KINDS = {
    "DUMP_NODE": "node",
    "DUMP_NODE_MANUAL": "manual_node",
    "DUMP_ENUM": "enum",
}


class VisitorRegistrationError(ValueError):
    """A visitor registration include cannot be generated from these inputs."""


def _load_inventory_module():
    parser_path = SCRIPTS_DIR / "inventory_dump_handlers.py"
    spec = importlib.util.spec_from_file_location(
        "visitor_registration_inventory", parser_path
    )
    if spec is None or spec.loader is None:
        raise VisitorRegistrationError(f"cannot load inventory parser {parser_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise VisitorRegistrationError(f"cannot read {description} {path}: {error}") from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise VisitorRegistrationError(f"invalid {description} {path}: {error}") from error


def _object(value: Any, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VisitorRegistrationError(f"{description} must be a JSON object")
    return value


def _array(value: Any, description: str) -> list[Any]:
    if not isinstance(value, list):
        raise VisitorRegistrationError(f"{description} must be a JSON array")
    return value


def _qualified_type(value: Any, description: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or "::" not in value
        or any(not segment for segment in value.split("::"))
    ):
        raise VisitorRegistrationError(
            f"{description} must be a fully qualified C++ type name"
        )
    return value


def _read_kinds(document: Any) -> list[dict[str, Any]]:
    root = _object(document, "kind manifest")
    if set(root) != {"format", "kinds"} or root.get("format") != KIND_FORMAT:
        raise VisitorRegistrationError(
            f"kind manifest must use format {KIND_FORMAT!r} and contain kinds"
        )
    entries = _array(root.get("kinds"), "kind manifest kinds")
    kinds: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, raw in enumerate(entries):
        entry = _object(raw, f"kinds[{index}]")
        if set(entry) != {"id", "cpp_type", "handler_kind"}:
            raise VisitorRegistrationError(
                f"kinds[{index}] must contain exactly id, cpp_type, and handler_kind"
            )
        kind_id = entry.get("id")
        if isinstance(kind_id, bool) or not isinstance(kind_id, int) or kind_id != index + 1:
            raise VisitorRegistrationError("kind IDs must be consecutive from 1")
        cpp_type = _qualified_type(entry.get("cpp_type"), f"kinds[{index}].cpp_type")
        handler_kind = entry.get("handler_kind")
        if handler_kind not in set(REGISTRATION_KINDS.values()):
            raise VisitorRegistrationError(
                f"kinds[{index}].handler_kind is unsupported: {handler_kind!r}"
            )
        if cpp_type in names:
            raise VisitorRegistrationError(f"duplicate kind entry for {cpp_type}")
        names.add(cpp_type)
        kinds.append(
            {"id": kind_id, "cpp_type": cpp_type, "handler_kind": handler_kind}
        )
    return kinds


def _read_inventory(document: Any) -> list[dict[str, Any]]:
    root = _object(document, "registration inventory")
    if set(root) != {"schema_version", "registrations"} or root.get("schema_version") != 1:
        raise VisitorRegistrationError(
            "registration inventory must use schema_version 1 and contain registrations"
        )
    entries = _array(root.get("registrations"), "registration inventory registrations")
    registrations: list[dict[str, Any]] = []
    names: set[str] = set()
    expected_keys = {
        "fully_qualified_type",
        "registration",
        "handler_kind",
        "source_line",
        "manual",
        "has_explicit_content",
    }
    for index, raw in enumerate(entries):
        item = _object(raw, f"registrations[{index}]")
        if set(item) != expected_keys:
            raise VisitorRegistrationError(
                f"registrations[{index}] must contain exactly {sorted(expected_keys)}"
            )
        cpp_type = _qualified_type(
            item.get("fully_qualified_type"),
            f"registrations[{index}].fully_qualified_type",
        )
        if cpp_type in names:
            raise VisitorRegistrationError(f"duplicate inventory registration for {cpp_type}")
        names.add(cpp_type)
        registration = item.get("registration")
        if registration not in REGISTRATION_KINDS:
            raise VisitorRegistrationError(
                f"registrations[{index}].registration is unsupported: {registration!r}"
            )
        expected_kind = REGISTRATION_KINDS[registration]
        if item.get("handler_kind") != expected_kind:
            raise VisitorRegistrationError(
                f"handler_kind mismatch for {cpp_type}: {item.get('handler_kind')!r} "
                f"does not match {registration}"
            )
        source_line = item.get("source_line")
        if (
            isinstance(source_line, bool)
            or not isinstance(source_line, int)
            or source_line < 1
        ):
            raise VisitorRegistrationError(
                f"registrations[{index}].source_line must be a positive integer"
            )
        if item.get("manual") is not (registration == "DUMP_NODE_MANUAL"):
            raise VisitorRegistrationError(
                f"manual flag mismatch for {cpp_type} and {registration}"
            )
        explicit = item.get("has_explicit_content")
        if not isinstance(explicit, bool):
            raise VisitorRegistrationError(
                f"registrations[{index}].has_explicit_content must be a boolean"
            )
        if registration == "DUMP_ENUM" and explicit:
            raise VisitorRegistrationError(f"enum registration {cpp_type} cannot have a body")
        registrations.append(
            {
                "fully_qualified_type": cpp_type,
                "registration": registration,
                "handler_kind": expected_kind,
                "source_line": source_line,
                "manual": item["manual"],
                "has_explicit_content": explicit,
            }
        )
    return registrations


def _read_bodies(document: Any) -> dict[str, dict[str, Any]]:
    root = _object(document, "handler bodies")
    if set(root) != {"format", "handlers"} or root.get("format") != BODY_FORMAT:
        raise VisitorRegistrationError(
            f"handler bodies must use format {BODY_FORMAT!r} and contain handlers"
        )
    entries = _array(root.get("handlers"), "handler bodies handlers")
    bodies: dict[str, dict[str, Any]] = {}
    expected_keys = {"fully_qualified_type", "registration", "source_line", "body"}
    for index, raw in enumerate(entries):
        item = _object(raw, f"handlers[{index}]")
        if set(item) != expected_keys:
            raise VisitorRegistrationError(
                f"handlers[{index}] must contain exactly {sorted(expected_keys)}"
            )
        cpp_type = _qualified_type(
            item.get("fully_qualified_type"), f"handlers[{index}].fully_qualified_type"
        )
        if cpp_type in bodies:
            raise VisitorRegistrationError(f"duplicate handler body for {cpp_type}")
        registration = item.get("registration")
        if registration not in ("DUMP_NODE", "DUMP_NODE_MANUAL"):
            raise VisitorRegistrationError(
                f"handlers[{index}].registration is unsupported: {registration!r}"
            )
        source_line = item.get("source_line")
        if (
            isinstance(source_line, bool)
            or not isinstance(source_line, int)
            or source_line < 1
        ):
            raise VisitorRegistrationError(
                f"handlers[{index}].source_line must be a positive integer"
            )
        body = item.get("body")
        if not isinstance(body, str):
            raise VisitorRegistrationError(f"handlers[{index}].body must be a string")
        bodies[cpp_type] = {
            "registration": registration,
            "body": body,
            "source_line": source_line,
        }
    return bodies


def _validate_inputs(
    kinds_document: Any, inventory_document: Any, bodies_document: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    kinds = _read_kinds(kinds_document)
    registrations = _read_inventory(inventory_document)
    bodies = _read_bodies(bodies_document)

    kinds_by_type = {item["cpp_type"]: item for item in kinds}
    registration_by_type = {
        item["fully_qualified_type"]: item for item in registrations
    }
    kind_types = set(kinds_by_type)
    registration_types = set(registration_by_type)
    missing_kinds = sorted(registration_types - kind_types)
    extra_kinds = sorted(kind_types - registration_types)
    if missing_kinds or extra_kinds:
        details = []
        if missing_kinds:
            details.append("missing kind entries: " + ", ".join(missing_kinds))
        if extra_kinds:
            details.append("unregistered kind entries: " + ", ".join(extra_kinds))
        raise VisitorRegistrationError("kind and inventory entries differ; " + "; ".join(details))

    for cpp_type, registration in registration_by_type.items():
        kind = kinds_by_type[cpp_type]
        if kind["handler_kind"] != registration["handler_kind"]:
            raise VisitorRegistrationError(
                f"handler_kind mismatch for {cpp_type}: kind manifest has "
                f"{kind['handler_kind']!r}, inventory has {registration['handler_kind']!r}"
            )

    explicit_types = {
        cpp_type
        for cpp_type, item in registration_by_type.items()
        if item["has_explicit_content"]
    }
    body_types = set(bodies)
    missing_bodies = sorted(explicit_types - body_types)
    extra_bodies = sorted(body_types - explicit_types)
    if missing_bodies or extra_bodies:
        details = []
        if missing_bodies:
            details.append("missing explicit handler bodies: " + ", ".join(missing_bodies))
        if extra_bodies:
            details.append("bodies without explicit-content registrations: " + ", ".join(extra_bodies))
        raise VisitorRegistrationError("; ".join(details))

    for cpp_type, body in bodies.items():
        registration = registration_by_type[cpp_type]
        if body["registration"] != registration["registration"]:
            raise VisitorRegistrationError(
                f"macro kind mismatch for body {cpp_type}: {body['registration']} "
                f"does not match inventory {registration['registration']}"
            )

    registrations.sort(key=lambda item: item["source_line"])
    return kinds, registrations, bodies


def _canonical_digest(
    kinds_document: Any, bodies_document: Any, registrations: list[dict[str, Any]]
) -> str:
    # Registration order carries source order. Physical source lines change when
    # the include replaces the old block, so they do not belong in this digest.
    canonical_registrations = [
        {
            key: item[key]
            for key in (
                "fully_qualified_type",
                "registration",
                "handler_kind",
                "manual",
                "has_explicit_content",
            )
        }
        for item in registrations
    ]
    canonical = json.dumps(
        {
            "kinds": kinds_document,
            "handler_bodies": bodies_document,
            "registrations_in_source_order": canonical_registrations,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def render_include(
    kinds_document: Any, inventory_document: Any, bodies_document: Any
) -> str:
    """Validate the inputs and return the registration include text."""
    _, registrations, bodies = _validate_inputs(
        kinds_document, inventory_document, bodies_document
    )
    digest = _canonical_digest(kinds_document, bodies_document, registrations)
    lines = [
        "// Generated by generator/generate_visitor_registrations.py.",
        f"// Canonical input SHA-256: {digest}",
        "",
    ]
    for item in registrations:
        cpp_type = item["fully_qualified_type"]
        registration = item["registration"]
        if registration == "DUMP_ENUM":
            namespace, enum_type = cpp_type.rsplit("::", 1)
            lines.append(f"DUMP_ENUM({namespace}, {enum_type})")
            continue
        body = bodies.get(cpp_type, {}).get("body", "")
        lines.append(f"{registration}({cpp_type}, {{{body}}})")
    return "\n".join(lines) + "\n"


def _default_inventory() -> dict[str, Any]:
    parser = _load_inventory_module()
    source_path = REPO_ROOT / "src" / "plugin.cpp"
    document = parser.inventory(source_path)
    if document["registrations"]:
        return document

    # Once plugin.cpp includes the generated file, read the registrations from
    # that file. This keeps regeneration and --check usable after integration.
    generated_path = REPO_ROOT / "src" / "generated_visitor_registrations.inc"
    if generated_path.is_file():
        generated = parser.inventory(generated_path)
        if generated["registrations"]:
            return generated
    return document


def _read_inventory_argument(path: Path | None) -> dict[str, Any]:
    if path is None:
        return _default_inventory()
    return _read_json(path, "registration inventory")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kinds",
        type=Path,
        default=REPO_ROOT / "generator" / "kinds.json",
        help="kind manifest (default: generator/kinds.json)",
    )
    parser.add_argument(
        "--bodies",
        type=Path,
        default=REPO_ROOT / "generator" / "handler_bodies.json",
        help="explicit handler bodies (default: generator/handler_bodies.json)",
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        help="registration inventory JSON from inventory_dump_handlers.py",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "src" / "generated_visitor_registrations.inc",
        help="include to write or check",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if --output differs from generated content",
    )
    args = parser.parse_args(argv)

    try:
        kinds_document = _read_json(args.kinds, "kind manifest")
        bodies_document = _read_json(args.bodies, "handler bodies")
        inventory_document = _read_inventory_argument(args.inventory)
        rendered = render_include(kinds_document, inventory_document, bodies_document)
        if args.check:
            actual = args.output.read_text(encoding="utf-8")
            if actual != rendered:
                print(f"visitor registration include is stale: {args.output}", file=sys.stderr)
                return 1
        else:
            args.output.write_text(rendered, encoding="utf-8")
    except (OSError, UnicodeError, ValueError) as error:
        print(f"visitor registration generation error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
