#!/usr/bin/env python3
"""Check registration coverage while leaving unregistered declarations visible.

This gate checks only types with dumper registrations. It permits the four
reviewed aliases in the baseline ignore list and reports declarations without
registrations as remaining work without failing the gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from audit_handler_coverage import AuditInputError, audit_coverage  # noqa: E402


DEFAULT_REGISTRATIONS = REPO_ROOT / "generator" / "registrations.json"
DEFAULT_DECLARATIONS = REPO_ROOT / "generator" / "flang22-declarations.json"
DEFAULT_IGNORE_LIST = REPO_ROOT / "tests" / "baseline" / "handler_coverage_ignores.json"

INLINE_NAMESPACES = (
    "Fortran::parser::arguments",
    "Fortran::parser::traits",
    "Fortran::parser::modifier",
)

REVIEWED_ALIASES = frozenset(
    {
        "Fortran::parser::Block",
        "Fortran::parser::AcImpliedDoControl::Bounds",
        "Fortran::parser::DataImpliedDo::Bounds",
        "Fortran::parser::LoopControl::Bounds",
    }
)


def check_registered_coverage(
    registration_document: Any,
    model_document: Any,
    ignore_document: Any | None,
) -> dict[str, Any]:
    """Return the short gate summary from the complete coverage audit report."""
    report = audit_coverage(
        registration_document,
        model_document,
        ignore_document,
        inline_namespaces=INLINE_NAMESPACES,
    )

    missing = report["missing_from_header"]
    missing_names = {item["fully_qualified_type"] for item in missing}
    ignored_missing_names = {
        item["fully_qualified_type"] for item in missing if item["ignored"]
    }
    if ignore_document is None:
        configured_exceptions: set[tuple[str, str]] = set()
    else:
        configured_exceptions = {
            (item["category"], item["fully_qualified_type"])
            for item in ignore_document["entries"]
        }
    expected_exceptions = {
        ("missing_from_header", name) for name in REVIEWED_ALIASES
    }

    audit_summary = report["summary"]
    alias_set_matches = (
        missing_names == REVIEWED_ALIASES
        and ignored_missing_names == REVIEWED_ALIASES
        and configured_exceptions == expected_exceptions
    )
    gate_ok = (
        alias_set_matches
        and not report["duplicate_registrations"]
        and not report["kind_mismatches"]
        and not report["unused_ignores"]
    )

    return {
        "ok": gate_ok,
        "registrations": audit_summary["registration_count"],
        "matched": audit_summary["matched_type_count"],
        "reviewed_aliases": len(ignored_missing_names & REVIEWED_ALIASES),
        "unregistered": audit_summary["unregistered_header_count"],
        "unreviewed_missing": len(missing_names - REVIEWED_ALIASES),
        "duplicate_groups": audit_summary["duplicate_registration_group_count"],
        "kind_mismatches": audit_summary["kind_mismatch_count"],
        "unused_exceptions": audit_summary["unused_ignore_count"],
        "unexpected_exceptions": len(configured_exceptions - expected_exceptions),
        "exception_set_matches_reviewed_aliases": alias_set_matches,
    }


def _read_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise AuditInputError(f"cannot read {description} {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise AuditInputError(f"invalid JSON in {description} {path}: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registrations", type=Path, default=DEFAULT_REGISTRATIONS)
    parser.add_argument("--declarations", type=Path, default=DEFAULT_DECLARATIONS)
    parser.add_argument("--ignore-list", type=Path, default=DEFAULT_IGNORE_LIST)
    args = parser.parse_args(argv)

    try:
        summary = check_registered_coverage(
            _read_json(args.registrations, "registration inventory"),
            _read_json(args.declarations, "Clava declarations model"),
            _read_json(args.ignore_list, "coverage ignore list"),
        )
    except AuditInputError as error:
        print(f"registered coverage error: {error}", file=sys.stderr)
        return 2

    json.dump(summary, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
