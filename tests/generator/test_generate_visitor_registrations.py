import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
GENERATOR_PATH = REPO / "generator" / "generate_visitor_registrations.py"
INVENTORY_PATH = REPO / "scripts" / "inventory_dump_handlers.py"
EXTRACTOR_PATH = REPO / "generator" / "extract_handler_bodies.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = load_module("generate_visitor_registrations", GENERATOR_PATH)
INVENTORY = load_module("visitor_inventory_for_test", INVENTORY_PATH)
EXTRACTOR = load_module("extract_handler_bodies_for_test", EXTRACTOR_PATH)


def kind(kind_id, cpp_type, handler_kind="node"):
    return {"id": kind_id, "cpp_type": cpp_type, "handler_kind": handler_kind}


def registration(cpp_type, macro, line, explicit=False):
    handler_kind = GENERATOR.REGISTRATION_KINDS[macro]
    return {
        "fully_qualified_type": cpp_type,
        "registration": macro,
        "handler_kind": handler_kind,
        "source_line": line,
        "manual": macro == "DUMP_NODE_MANUAL",
        "has_explicit_content": explicit,
    }


def kind_manifest(*entries):
    return {"format": GENERATOR.KIND_FORMAT, "kinds": list(entries)}


def inventory_document(*entries):
    return {"schema_version": 1, "registrations": list(entries)}


def bodies_document(*entries):
    return {"format": GENERATOR.BODY_FORMAT, "handlers": list(entries)}


def body(cpp_type, macro, content, line=1):
    return {
        "fully_qualified_type": cpp_type,
        "registration": macro,
        "source_line": line,
        "body": content,
    }


class GenerateVisitorRegistrationsTest(unittest.TestCase):
    def test_nested_body_and_enum_render_in_source_order(self):
        nested_type = "Fortran::parser::NestedNode"
        enum_type = "Fortran::common::State"
        nested_body = (
            "if (std::get<0>(v.t).has_value()) {\n"
            "    dump(std::get<0>(v.t).value(), \"nested\");\n"
            "}"
        )
        kinds = kind_manifest(
            kind(1, nested_type),
            kind(2, enum_type, "enum"),
        )
        inventory = inventory_document(
            registration(nested_type, "DUMP_NODE", 20, explicit=True),
            registration(enum_type, "DUMP_ENUM", 10),
        )
        bodies = bodies_document(body(nested_type, "DUMP_NODE", nested_body))

        rendered = GENERATOR.render_include(kinds, inventory, bodies)

        self.assertIn(
            f"DUMP_NODE({nested_type}, {{{nested_body}}})",
            rendered,
        )
        self.assertLess(rendered.index(f"DUMP_ENUM(Fortran::common, State)"),
                        rendered.index(f"DUMP_NODE({nested_type}"))
        macro_lines = [
            line.rstrip()
            for line in rendered.splitlines()
            if line.lstrip().startswith("DUMP_")
        ]
        self.assertTrue(macro_lines)
        self.assertTrue(all(not line.endswith(";") for line in macro_lines))
        parsed = INVENTORY.parse_registrations(rendered)
        self.assertEqual(
            [(item["fully_qualified_type"], item["registration"]) for item in parsed],
            [(enum_type, "DUMP_ENUM"), (nested_type, "DUMP_NODE")],
        )

    def test_rejects_missing_explicit_body(self):
        cpp_type = "Fortran::parser::NeedsBody"
        with self.assertRaisesRegex(
            GENERATOR.VisitorRegistrationError, "missing explicit handler bodies"
        ):
            GENERATOR.render_include(
                kind_manifest(kind(1, cpp_type)),
                inventory_document(
                    registration(cpp_type, "DUMP_NODE", 1, explicit=True)
                ),
                bodies_document(),
            )

    def test_rejects_body_without_explicit_registration(self):
        cpp_type = "Fortran::parser::NoBody"
        with self.assertRaisesRegex(
            GENERATOR.VisitorRegistrationError,
            "bodies without explicit-content registrations",
        ):
            GENERATOR.render_include(
                kind_manifest(kind(1, cpp_type)),
                inventory_document(registration(cpp_type, "DUMP_NODE", 1)),
                bodies_document(body(cpp_type, "DUMP_NODE", "dump(v);")),
            )

    def test_rejects_body_with_mismatched_macro_kind(self):
        cpp_type = "Fortran::parser::ManualNode"
        with self.assertRaisesRegex(
            GENERATOR.VisitorRegistrationError, "macro kind mismatch"
        ):
            GENERATOR.render_include(
                kind_manifest(kind(1, cpp_type, "manual_node")),
                inventory_document(
                    registration(cpp_type, "DUMP_NODE_MANUAL", 1, explicit=True)
                ),
                bodies_document(body(cpp_type, "DUMP_NODE", "dump(v);")),
            )

    def test_rejects_inventory_kind_disagreement(self):
        cpp_type = "Fortran::parser::Node"
        with self.assertRaisesRegex(
            GENERATOR.VisitorRegistrationError, "handler_kind mismatch"
        ):
            GENERATOR.render_include(
                kind_manifest(kind(1, cpp_type, "manual_node")),
                inventory_document(registration(cpp_type, "DUMP_NODE", 1)),
                bodies_document(),
            )

    def test_rejects_missing_kind_entry(self):
        cpp_type = "Fortran::parser::Node"
        with self.assertRaisesRegex(
            GENERATOR.VisitorRegistrationError, "missing kind entries"
        ):
            GENERATOR.render_include(
                kind_manifest(),
                inventory_document(registration(cpp_type, "DUMP_NODE", 1)),
                bodies_document(),
            )

    def test_check_mode_detects_stale_output(self):
        cpp_type = "Fortran::parser::Node"
        with tempfile.TemporaryDirectory(prefix="flang-visitor-stale-") as temporary:
            root = Path(temporary)
            kinds_path = root / "kinds.json"
            bodies_path = root / "bodies.json"
            inventory_path = root / "inventory.json"
            output_path = root / "registrations.inc"
            kinds_path.write_text(
                json.dumps(kind_manifest(kind(1, cpp_type))), encoding="utf-8"
            )
            bodies_path.write_text(json.dumps(bodies_document()), encoding="utf-8")
            inventory_path.write_text(
                json.dumps(
                    inventory_document(registration(cpp_type, "DUMP_NODE", 1))
                ),
                encoding="utf-8",
            )
            output_path.write_text("stale\n", encoding="utf-8")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                status = GENERATOR.main(
                    [
                        "--kinds",
                        str(kinds_path),
                        "--bodies",
                        str(bodies_path),
                        "--inventory",
                        str(inventory_path),
                        "--output",
                        str(output_path),
                        "--check",
                    ]
                )

            self.assertEqual(status, 1)
            self.assertIn("visitor registration include is stale", stderr.getvalue())

    def test_committed_include_is_fresh_and_matches_original_inventory(self):
        output_path = REPO / "src" / "generated_visitor_registrations.inc"
        with contextlib.redirect_stdout(io.StringIO()):
            status = GENERATOR.main(["--check"])
        self.assertEqual(status, 0)

        original = INVENTORY.inventory(REPO / "src" / "plugin.cpp")["registrations"]
        generated = INVENTORY.inventory(output_path)["registrations"]
        self.assertEqual(len(original), 864)
        self.assertEqual(len(generated), len(original))
        # Source lines naturally move into the generated include. All semantic
        # inventory fields, source order, and explicit-content counts must match.
        fields = (
            "fully_qualified_type",
            "registration",
            "handler_kind",
            "manual",
            "has_explicit_content",
        )
        self.assertEqual(
            [[entry[field] for field in fields] for entry in generated],
            [[entry[field] for field in fields] for entry in original],
        )
        self.assertEqual(
            sum(item["has_explicit_content"] for item in original),
            sum(item["has_explicit_content"] for item in generated),
        )

        original_bodies = EXTRACTOR.extract_handler_bodies(
            (REPO / "src" / "plugin.cpp").read_text(encoding="utf-8"),
            {"schema_version": 1, "registrations": original},
        )
        generated_bodies = EXTRACTOR.extract_handler_bodies(
            output_path.read_text(encoding="utf-8"),
            {"schema_version": 1, "registrations": generated},
        )
        self.assertEqual(
            {
                item["fully_qualified_type"]: (
                    item["registration"],
                    item["body"],
                )
                for item in generated_bodies["handlers"]
            },
            {
                item["fully_qualified_type"]: (
                    item["registration"],
                    item["body"],
                )
                for item in original_bodies["handlers"]
            },
        )


if __name__ == "__main__":
    unittest.main()
