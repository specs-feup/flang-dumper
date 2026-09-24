import contextlib
import copy
import importlib.util
import io
import json
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO / "generator" / "check_registered_coverage.py"
SPEC = importlib.util.spec_from_file_location("check_registered_coverage", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class CheckRegisteredCoverageTest(unittest.TestCase):
    def setUp(self):
        self.registrations = load_json(REPO / "generator" / "registrations.json")
        self.declarations = load_json(REPO / "generator" / "flang22-declarations.json")
        self.ignores = load_json(REPO / "tests" / "baseline" / "handler_coverage_ignores.json")

    def check(self, registrations=None, declarations=None, ignores=None):
        return CHECKER.check_registered_coverage(
            self.registrations if registrations is None else registrations,
            self.declarations if declarations is None else declarations,
            self.ignores if ignores is None else ignores,
        )

    def test_default_cli_reports_current_registration_only_gate_counts(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = CHECKER.main([])

        summary = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["registrations"], 864)
        self.assertEqual(summary["matched"], 860)
        self.assertEqual(summary["reviewed_aliases"], 4)
        self.assertEqual(summary["unregistered"], 200)
        self.assertEqual(summary["unreviewed_missing"], 0)

    def test_unexpected_fifth_missing_registration_fails(self):
        registrations = copy.deepcopy(self.registrations)
        registrations["registrations"].append(
            {
                "fully_qualified_type": "Fortran::parser::UnreviewedAlias",
                "registration": "DUMP_NODE",
                "handler_kind": "node",
                "source_line": 2000,
                "manual": False,
                "has_explicit_content": False,
            }
        )

        summary = self.check(registrations=registrations)

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["unreviewed_missing"], 1)
        self.assertFalse(summary["exception_set_matches_reviewed_aliases"])

    def test_unreviewed_exception_outside_alias_allowlist_fails(self):
        ignores = copy.deepcopy(self.ignores)
        ignores["reviewed"] = False
        ignores["entries"].append(
            {
                "category": "missing_from_header",
                "fully_qualified_type": "Fortran::parser::UnreviewedAlias",
                "reason": "Added without generator review.",
            }
        )

        with self.assertRaisesRegex(CHECKER.AuditInputError, "reviewed to true"):
            self.check(ignores=ignores)

    def test_unused_exception_fails(self):
        ignores = copy.deepcopy(self.ignores)
        ignores["entries"].append(
            {
                "category": "missing_from_header",
                "fully_qualified_type": "Fortran::parser::StaleAlias",
                "reason": "This name is not a missing registration.",
            }
        )

        summary = self.check(ignores=ignores)

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["unused_exceptions"], 1)
        self.assertEqual(summary["unexpected_exceptions"], 1)
        self.assertFalse(summary["exception_set_matches_reviewed_aliases"])

    def test_kind_mismatch_fails(self):
        declarations = copy.deepcopy(self.declarations)
        enum_registration = next(
            item
            for item in self.registrations["registrations"]
            if item["registration"] == "DUMP_ENUM"
        )
        target_name = enum_registration["fully_qualified_type"]
        declaration = next(
            item
            for item in declarations["declarations"]
            if item["qualified_name"] == target_name
        )
        declaration["kind"] = "record"

        summary = self.check(declarations=declarations)

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["kind_mismatches"], 1)

    def test_duplicate_registration_fails(self):
        registrations = copy.deepcopy(self.registrations)
        duplicate = copy.deepcopy(registrations["registrations"][0])
        duplicate["source_line"] += 2000
        registrations["registrations"].append(duplicate)

        summary = self.check(registrations=registrations)

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["duplicate_groups"], 1)


if __name__ == "__main__":
    unittest.main()
