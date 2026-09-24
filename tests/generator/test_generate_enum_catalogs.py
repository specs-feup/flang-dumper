import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
GENERATOR_PATH = REPO / "generator" / "generate_enum_catalogs.py"
SPEC = importlib.util.spec_from_file_location("generate_enum_catalogs", GENERATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


def registration(cpp_type, macro="DUMP_ENUM", **updates):
    entry = {
        "fully_qualified_type": cpp_type,
        "registration": macro,
        "handler_kind": GENERATOR.REGISTRATION_KINDS[macro],
        "source_line": 1,
        "manual": macro == "DUMP_NODE_MANUAL",
        "has_explicit_content": False,
    }
    entry.update(updates)
    return entry


def inventory(*entries):
    return {"schema_version": 1, "registrations": list(entries)}


class GenerateEnumCatalogsTest(unittest.TestCase):
    def test_pinned_catalogs_match_enum_registration_source_order(self):
        pinned = json.loads(
            (REPO / "generator" / "registrations.json").read_text(encoding="utf-8")
        )
        enum_types = [
            item["fully_qualified_type"]
            for item in pinned["registrations"]
            if item["registration"] == "DUMP_ENUM"
        ]
        rendered = GENERATOR.render_include(pinned)
        calls = [line for line in rendered.splitlines() if line.startswith("EMIT_ENUM_CATALOG(")]
        expected_calls = [
            f"EMIT_ENUM_CATALOG({cpp_type.rsplit('::', 1)[0]}, {cpp_type.rsplit('::', 1)[1]})"
            for cpp_type in enum_types
        ]

        self.assertEqual(len(calls), 62)
        self.assertEqual(calls, expected_calls)
        self.assertTrue(all(not call.endswith(";") for call in calls))
        self.assertEqual(rendered, GENERATOR.render_include(pinned))

    def test_rejects_malformed_registration(self):
        malformed = registration("Fortran::common::State")
        del malformed["handler_kind"]

        with self.assertRaisesRegex(GENERATOR.EnumCatalogError, "contain exactly"):
            GENERATOR.render_include(inventory(malformed))

    def test_rejects_duplicate_registration_type(self):
        entry = registration("Fortran::common::State")

        with self.assertRaisesRegex(GENERATOR.EnumCatalogError, "duplicate inventory registration"):
            GENERATOR.render_include(inventory(entry, dict(entry)))

    def test_committed_include_is_fresh(self):
        with contextlib.redirect_stdout(io.StringIO()):
            status = GENERATOR.main(["--check"])

        self.assertEqual(status, 0)


if __name__ == "__main__":
    unittest.main()
