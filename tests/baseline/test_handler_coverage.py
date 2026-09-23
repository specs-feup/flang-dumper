from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import run


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from audit_handler_coverage import AuditInputError, audit_coverage  # noqa: E402


def registration(
    type_name: str,
    macro: str = "DUMP_NODE",
    *,
    line: int = 1,
    content: bool = False,
) -> dict[str, object]:
    handler_kind = {
        "DUMP_NODE": "node",
        "DUMP_NODE_MANUAL": "manual_node",
        "DUMP_ENUM": "enum",
    }[macro]
    return {
        "fully_qualified_type": type_name,
        "registration": macro,
        "handler_kind": handler_kind,
        "source_line": line,
        "manual": macro == "DUMP_NODE_MANUAL",
        "has_explicit_content": content,
    }


def declarations(*items: tuple[str, str]) -> dict[str, object]:
    return {
        "format": "clava-declaration-inventory/v1",
        "source_header": {"file": "fixture.hpp", "sha256": "0" * 64},
        "declarations": [
            {"qualified_name": name, "kind": kind} for name, kind in items
        ],
    }


def sample_inputs() -> tuple[dict[str, object], dict[str, object]]:
    inventory = {
        "schema_version": 1,
        "registrations": [
            registration("::demo :: Foo"),
            registration("demo::ExtraNode", line=2, content=True),
            registration("demo::Manual", "DUMP_NODE_MANUAL", line=3, content=True),
            registration("demo::Direction", "DUMP_ENUM", line=4),
        ],
    }
    model = declarations(
        ("struct demo::Foo", "record"),
        ("demo::Manual", "record"),
        ("demo::Direction", "enum"),
        ("demo::HeaderOnly", "record"),
    )
    return inventory, model


class HandlerCoverageTests(unittest.TestCase):
    def test_reports_name_matches_gaps_and_handler_counts(self) -> None:
        inventory, model = sample_inputs()
        report = audit_coverage(inventory, model)

        self.assertFalse(report["ok"])
        self.assertEqual(
            [row["fully_qualified_type"] for row in report["matched"]],
            ["demo::Direction", "demo::Foo", "demo::Manual"],
        )
        self.assertEqual(
            [row["fully_qualified_type"] for row in report["missing_from_header"]],
            ["demo::ExtraNode"],
        )
        self.assertEqual(
            [row["fully_qualified_type"] for row in report["unregistered_header_declarations"]],
            ["demo::HeaderOnly"],
        )
        self.assertEqual(report["summary"]["manual_registration_count"], 1)
        self.assertEqual(report["summary"]["explicit_content_registration_count"], 2)
        self.assertEqual(report["summary"]["automatic_node_extra_content_count"], 1)
        self.assertEqual(report["summary"]["manual_with_explicit_content_count"], 1)

    def test_reviewed_exact_name_ignores_suppress_only_their_named_gaps(self) -> None:
        inventory, model = sample_inputs()
        ignores = {
            "format": "flang-handler-coverage-ignore/v1",
            "reviewed": True,
            "entries": [
                {
                    "category": "missing_from_header",
                    "fully_qualified_type": "demo :: ExtraNode",
                    "reason": "This registration is defined in the supporting format header.",
                },
                {
                    "category": "unregistered_header",
                    "fully_qualified_type": "::demo::HeaderOnly",
                    "reason": "This helper record is not part of the parse-tree visitor contract.",
                },
            ],
        }
        report = audit_coverage(inventory, model, ignores)
        self.assertTrue(report["ok"])
        self.assertEqual(report["summary"]["ignored_gap_count"], 2)
        self.assertTrue(all(item["ignored"] for item in report["missing_from_header"]))
        self.assertTrue(all(item["ignored"] for item in report["unregistered_header_declarations"]))

    def test_ignore_list_requires_review_reasons_and_exact_categories(self) -> None:
        inventory, model = sample_inputs()
        base = {"format": "flang-handler-coverage-ignore/v1", "reviewed": True}
        invalid_entries = [
            {"category": "missing_from_header", "fully_qualified_type": "*", "reason": "skip all"},
            {
                "category": "missing_from_header",
                "fully_qualified_type": "demo::ExtraNode",
                "reason": "  ",
            },
            {"category": "all", "fully_qualified_type": "demo::ExtraNode", "reason": "skip"},
        ]
        for entry in invalid_entries:
            with self.subTest(entry=entry), self.assertRaises(AuditInputError):
                audit_coverage(inventory, model, {**base, "entries": [entry]})

        unreviewed = {
            "format": "flang-handler-coverage-ignore/v1",
            "entries": [
                {
                    "category": "missing_from_header",
                    "fully_qualified_type": "demo::ExtraNode",
                    "reason": "Specific known declaration location.",
                }
            ],
        }
        with self.assertRaisesRegex(AuditInputError, "reviewed to true"):
            audit_coverage(inventory, model, unreviewed)

        blanket = {
            **base,
            "skip_all": True,
            "entries": [],
        }
        with self.assertRaisesRegex(AuditInputError, "unsupported keys"):
            audit_coverage(inventory, model, blanket)

    def test_stale_ignore_duplicate_registration_and_kind_mismatch_fail(self) -> None:
        inventory, model = sample_inputs()
        stale_ignore = {
            "format": "flang-handler-coverage-ignore/v1",
            "reviewed": True,
            "entries": [
                {
                    "category": "missing_from_header",
                    "fully_qualified_type": "demo::Foo",
                    "reason": "Old exception that should be removed after coverage changes.",
                }
            ],
        }
        report = audit_coverage(inventory, model, stale_ignore)
        self.assertFalse(report["ok"])
        self.assertEqual(report["summary"]["unused_ignore_count"], 1)

        duplicate_inventory = {
            **inventory,
            "registrations": inventory["registrations"]
            + [registration("demo::Foo", "DUMP_NODE_MANUAL", line=5, content=True)],
        }
        duplicate_report = audit_coverage(duplicate_inventory, model)
        self.assertFalse(duplicate_report["ok"])
        self.assertEqual(duplicate_report["summary"]["duplicate_registration_group_count"], 1)

        mismatched_model = declarations(("demo::Direction", "record"))
        mismatch_inventory = {
            "schema_version": 1,
            "registrations": [registration("demo::Direction", "DUMP_ENUM")],
        }
        mismatch_report = audit_coverage(mismatch_inventory, mismatched_model)
        self.assertFalse(mismatch_report["ok"])
        self.assertEqual(mismatch_report["summary"]["kind_mismatch_count"], 1)

    def test_node_handler_can_visit_enum_without_enum_catalog_registration(self) -> None:
        inventory = {
            "schema_version": 1,
            "registrations": [registration("demo::Sign", "DUMP_NODE")],
        }
        model = declarations(("demo::Sign", "enum"))
        report = audit_coverage(inventory, model)
        self.assertTrue(report["ok"])
        self.assertEqual(report["summary"]["kind_mismatch_count"], 0)

    def test_cli_emits_report_and_returns_nonzero_for_unignored_gaps(self) -> None:
        inventory, model = sample_inputs()
        with tempfile.TemporaryDirectory(prefix="handler-coverage-") as temporary:
            root = Path(temporary)
            inventory_path = root / "registrations.json"
            model_path = root / "declarations.json"
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            model_path.write_text(json.dumps(model), encoding="utf-8")
            result = run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "audit_handler_coverage.py"),
                    str(inventory_path),
                    str(model_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["ok"])
        self.assertEqual(output["summary"]["missing_from_header_count"], 1)
        self.assertEqual(output["summary"]["unregistered_header_count"], 1)


if __name__ == "__main__":
    unittest.main()
