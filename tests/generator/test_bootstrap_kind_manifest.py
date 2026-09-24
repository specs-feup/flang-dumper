import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
BOOTSTRAP_PATH = REPO / "generator" / "bootstrap_kind_manifest.py"
SPEC = importlib.util.spec_from_file_location("bootstrap_kind_manifest", BOOTSTRAP_PATH)
assert SPEC is not None and SPEC.loader is not None
BOOTSTRAP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOOTSTRAP)


REGISTRATION_FOR_KIND = {
    "node": ("DUMP_NODE", False),
    "manual_node": ("DUMP_NODE_MANUAL", True),
    "enum": ("DUMP_ENUM", False),
}


def inventory(*entries):
    registrations = []
    for name, kind in entries:
        registration, manual = REGISTRATION_FOR_KIND[kind]
        registrations.append(
            {
                "fully_qualified_type": name,
                "handler_kind": kind,
                "has_explicit_content": False,
                "manual": manual,
                "registration": registration,
                "source_line": len(registrations) + 1,
            }
        )
    return {"schema_version": 1, "registrations": registrations}


def manifest(*entries):
    return {"format": "flang-kind-manifest/v1", "kinds": list(entries)}


def kind(kind_id, cpp_type, handler_kind):
    return {"id": kind_id, "cpp_type": cpp_type, "handler_kind": handler_kind}


class BootstrapKindManifestTest(unittest.TestCase):
    def test_initial_manifest_assigns_ids_by_sorted_cpp_type(self):
        result = BOOTSTRAP.build_manifest(
            inventory(
                ("Fortran::parser::Zed", "node"),
                ("Fortran::common::Alpha", "enum"),
                ("Fortran::parser::Manual", "manual_node"),
            )
        )

        self.assertEqual(result["format"], "flang-kind-manifest/v1")
        self.assertEqual(
            result["kinds"],
            [
                kind(1, "Fortran::common::Alpha", "enum"),
                kind(2, "Fortran::parser::Manual", "manual_node"),
                kind(3, "Fortran::parser::Zed", "node"),
            ],
        )

    def test_existing_ids_are_preserved_and_new_names_append_sorted(self):
        existing = manifest(
            kind(1, "Fortran::common::Alpha", "enum"),
            kind(2, "Fortran::parser::Beta", "node"),
        )
        result = BOOTSTRAP.build_manifest(
            inventory(
                ("Fortran::parser::Zeta", "manual_node"),
                ("Fortran::parser::Beta", "node"),
                ("Fortran::parser::Gamma", "node"),
                ("Fortran::common::Alpha", "enum"),
            ),
            existing,
        )

        self.assertEqual(
            result["kinds"],
            [
                kind(1, "Fortran::common::Alpha", "enum"),
                kind(2, "Fortran::parser::Beta", "node"),
                kind(3, "Fortran::parser::Gamma", "node"),
                kind(4, "Fortran::parser::Zeta", "manual_node"),
            ],
        )

    def test_rejects_duplicate_inventory_registrations(self):
        with self.assertRaisesRegex(BOOTSTRAP.ManifestError, "duplicate registration"):
            BOOTSTRAP.build_manifest(
                inventory(("Fortran::parser::Node", "node"), ("Fortran::parser::Node", "node"))
            )

    def test_rejects_unsupported_or_inconsistent_registration_kind(self):
        source = inventory(("Fortran::parser::Node", "node"))
        source["registrations"][0]["handler_kind"] = "unknown"
        with self.assertRaisesRegex(BOOTSTRAP.ManifestError, "handler_kind is unsupported"):
            BOOTSTRAP.build_manifest(source)

        source = inventory(("Fortran::parser::Node", "node"))
        source["registrations"][0]["handler_kind"] = "enum"
        with self.assertRaisesRegex(BOOTSTRAP.ManifestError, "must be 'node'"):
            BOOTSTRAP.build_manifest(source)

    def test_rejects_removed_or_renamed_existing_type(self):
        existing = manifest(kind(1, "Fortran::parser::OldName", "node"))
        current = inventory(("Fortran::parser::NewName", "node"))

        with self.assertRaisesRegex(BOOTSTRAP.ManifestError, "removal or rename is not allowed"):
            BOOTSTRAP.build_manifest(current, existing)

    def test_rejects_handler_kind_changes(self):
        existing = manifest(kind(1, "Fortran::parser::Stable", "node"))
        current = inventory(("Fortran::parser::Stable", "manual_node"))

        with self.assertRaisesRegex(BOOTSTRAP.ManifestError, "handler_kind changed"):
            BOOTSTRAP.build_manifest(current, existing)

    def test_rejects_id_gaps_collisions_and_non_id_order(self):
        current = inventory(("Fortran::parser::Alpha", "node"))
        invalid_manifests = [
            manifest(kind(1, "Fortran::parser::One", "node"), kind(3, "Fortran::parser::Three", "node")),
            manifest(kind(1, "Fortran::parser::One", "node"), kind(1, "Fortran::parser::Two", "node")),
            manifest(kind(2, "Fortran::parser::Two", "node"), kind(1, "Fortran::parser::One", "node")),
        ]
        for existing in invalid_manifests:
            with self.subTest(existing=existing):
                with self.assertRaisesRegex(BOOTSTRAP.ManifestError, "ID"):
                    BOOTSTRAP.build_manifest(current, existing)

    def test_rejects_duplicate_cpp_types_in_existing_manifest(self):
        existing = manifest(
            kind(1, "Fortran::parser::Same", "node"),
            kind(2, "Fortran::parser::Same", "node"),
        )

        with self.assertRaisesRegex(BOOTSTRAP.ManifestError, "duplicate cpp_type"):
            BOOTSTRAP.read_manifest(existing)

    def test_rejects_malformed_inventory_and_manifest_shapes(self):
        with self.assertRaisesRegex(BOOTSTRAP.ManifestError, "schema_version"):
            BOOTSTRAP.build_manifest({"schema_version": True, "registrations": []})

        with self.assertRaisesRegex(BOOTSTRAP.ManifestError, "at least one"):
            BOOTSTRAP.build_manifest(inventory())

        with self.assertRaisesRegex(BOOTSTRAP.ManifestError, "fully qualified"):
            BOOTSTRAP.build_manifest(inventory(("Node", "node")))

        with self.assertRaisesRegex(BOOTSTRAP.ManifestError, "format must be"):
            BOOTSTRAP.build_manifest(inventory(("Fortran::parser::Node", "node")), {"format": "bad", "kinds": []})

    def test_cli_writes_manifest_and_does_not_overwrite_inputs(self):
        document = inventory(("Fortran::parser::Node", "node"))
        with tempfile.TemporaryDirectory(prefix="flang-kind-manifest-") as temporary:
            root = Path(temporary)
            inventory_path = root / "registrations.json"
            output_path = root / "kinds.json"
            inventory_path.write_text(json.dumps(document), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                status = BOOTSTRAP.main(
                    [str(inventory_path), "--output", str(output_path)]
                )
            self.assertEqual(status, 0)
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8")),
                manifest(kind(1, "Fortran::parser::Node", "node")),
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = BOOTSTRAP.main(
                    [str(inventory_path), "--output", str(inventory_path)]
                )
            self.assertEqual(status, 2)
            self.assertIn("must not overwrite an input", stderr.getvalue())
            self.assertEqual(
                json.loads(inventory_path.read_text(encoding="utf-8")), document
            )


if __name__ == "__main__":
    unittest.main()
