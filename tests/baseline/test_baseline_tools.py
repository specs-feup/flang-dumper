from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from inventory_dump_handlers import parse_registrations  # noqa: E402
from compare_graphs import compare_graphs  # noqa: E402


class InventoryParserTests(unittest.TestCase):
    def test_multiline_macros_nested_content_and_ignored_comments(self) -> None:
        source = '''
// DUMP_NODE(Fortran::fake::Commented, {})
const char *not_code = R"tag(DUMP_ENUM(Fortran::fake, StringValue))tag";
/* DUMP_NODE_MANUAL(Fortran::fake::BlockComment, {}) */
DUMP_NODE(
    Fortran::parser::TupleLike,
    {
      dump(make_pair(1, 2), "pair");
      if (ready()) { dump("comma, and (paren)", "value"); }
    })
DUMP_NODE_MANUAL(Fortran::parser::EmptyManual, { /* comment only */ })
DUMP_ENUM(
    Fortran::parser::UseStmt,
    ModuleNature)
'''
        registrations = parse_registrations(source)
        self.assertEqual(
            [item["fully_qualified_type"] for item in registrations],
            [
                "Fortran::parser::TupleLike",
                "Fortran::parser::EmptyManual",
                "Fortran::parser::UseStmt::ModuleNature",
            ],
        )
        self.assertEqual(
            [item["handler_kind"] for item in registrations],
            ["node", "manual_node", "enum"],
        )
        self.assertEqual([item["manual"] for item in registrations], [False, True, False])
        self.assertEqual(
            [item["has_explicit_content"] for item in registrations],
            [True, False, False],
        )
        self.assertEqual([item["source_line"] for item in registrations], [5, 11, 12])

    def test_current_plugin_registrations_are_extracted(self) -> None:
        source_file = REPO_ROOT / "src" / "plugin.cpp"
        source = source_file.read_text(encoding="utf-8")
        first = parse_registrations(source)
        second = parse_registrations(source)

        self.assertEqual(first, second)
        self.assertGreater(len(first), 700)
        entries = {
            (entry["fully_qualified_type"], entry["registration"]): entry for entry in first
        }
        self.assertEqual(
            entries[("Fortran::parser::ComplexLiteralConstant", "DUMP_NODE_MANUAL")][
                "handler_kind"
            ],
            "manual_node",
        )
        self.assertTrue(
            entries[("Fortran::parser::ComplexLiteralConstant", "DUMP_NODE_MANUAL")]["manual"]
        )
        self.assertTrue(
            entries[("Fortran::parser::ComplexLiteralConstant", "DUMP_NODE_MANUAL")][
                "has_explicit_content"
            ]
        )
        self.assertEqual(
            entries[("Fortran::parser::UseStmt::ModuleNature", "DUMP_ENUM")]["handler_kind"],
            "enum",
        )
        self.assertEqual(
            entries[("Fortran::format::DerivedTypeDataEditDesc", "DUMP_NODE")]["source_line"],
            426,
        )


class GraphComparisonTests(unittest.TestCase):
    def test_pointer_addresses_are_normalized_without_changing_relationships(self) -> None:
        expected = {
            "nodes": [
                {
                    "id": "0x10-Program",
                    "statement": "0x20-AssignmentStmt",
                    "source": "sample.f90:1:1-1:8",
                },
                {"id": "0x20-AssignmentStmt", "value": "0x10-Program"},
            ],
            "comments": [{"text": "! before", "stmtId": "0x10-Program", "trailing": False}],
            "enums": {"UseStmt::ModuleNature": ["Intrinsic", "Non_Intrinsic"]},
        }
        actual = {
            "nodes": [
                {
                    "id": "0xf00-Program",
                    "statement": "0xbeef-AssignmentStmt",
                    "source": "sample.f90:1:1-1:8",
                },
                {"id": "0xbeef-AssignmentStmt", "value": "0xf00-Program"},
            ],
            "comments": [{"text": "! before", "stmtId": "0xf00-Program", "trailing": False}],
            "enums": {"UseStmt::ModuleNature": ["Intrinsic", "Non_Intrinsic"]},
        }
        self.assertTrue(compare_graphs(expected, actual))

        actual["nodes"][1]["value"] = "0xbeef-AssignmentStmt"
        self.assertFalse(compare_graphs(expected, actual))

    def test_attribute_presence_order_comments_enums_and_source_remain_significant(self) -> None:
        baseline = {
            "nodes": [
                {
                    "id": "0x10-Node",
                    "first": "alpha",
                    "second": "beta",
                    "source": "sample.f90:4:1-4:5",
                }
            ],
            "comments": [{"text": "! original", "stmtId": "0x10-Node", "trailing": True}],
            "enums": {"Kind": ["A", "B"]},
        }

        changed_presence = {
            **baseline,
            "nodes": [{key: value for key, value in baseline["nodes"][0].items() if key != "second"}],
        }
        self.assertFalse(compare_graphs(baseline, changed_presence))

        changed_order = {
            **baseline,
            "nodes": [
                {
                    "id": "0x10-Node",
                    "second": "beta",
                    "first": "alpha",
                    "source": "sample.f90:4:1-4:5",
                }
            ],
        }
        self.assertFalse(compare_graphs(baseline, changed_order))

        changed_comment = {**baseline, "comments": [{**baseline["comments"][0], "text": "! changed"}]}
        self.assertFalse(compare_graphs(baseline, changed_comment))
        changed_source = {
            **baseline,
            "nodes": [{**baseline["nodes"][0], "source": "sample.f90:5:1-5:5"}],
        }
        self.assertFalse(compare_graphs(baseline, changed_source))
        changed_enum = {**baseline, "enums": {"Kind": ["B", "A"]}}
        self.assertFalse(compare_graphs(baseline, changed_enum))

    def test_duplicate_node_ids_are_rejected(self) -> None:
        duplicate = {
            "nodes": [
                {"id": "0x10-Node", "value": "first"},
                {"id": "0x10-Node", "value": "second"},
            ],
            "comments": [],
            "enums": {},
        }
        with self.assertRaisesRegex(ValueError, "repeats node ID"):
            compare_graphs(duplicate, duplicate)


if __name__ == "__main__":
    unittest.main()
