import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
GENERATOR_PATH = REPO / "generator" / "generate_kind_header.py"
SPEC = importlib.util.spec_from_file_location("generate_kind_header", GENERATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GENERATOR)


def manifest(*entries):
    return {"format": "flang-kind-manifest/v1", "kinds": list(entries)}


def kind(kind_id, cpp_type, handler_kind="node"):
    return {"id": kind_id, "cpp_type": cpp_type, "handler_kind": handler_kind}


class GenerateKindHeaderTest(unittest.TestCase):
    def test_rendering_is_deterministic(self):
        source = manifest(
            kind(1, "Fortran::common::Alpha", "enum"),
            kind(2, "Fortran::parser::Node", "manual_node"),
        )

        first = GENERATOR.render_header(source)
        second = GENERATOR.render_header(source)

        self.assertEqual(first, second)
        self.assertIn("enum class AstKind : std::uint32_t", first)
        self.assertIn('"Fortran::common::Alpha", "enum"', first)

    def test_rejects_enum_name_collisions(self):
        source = manifest(
            kind(1, "Fortran::parser::A_B"),
            kind(2, "Fortran::parser_A::B"),
        )

        with self.assertRaisesRegex(GENERATOR.KindHeaderError, "enum name collision"):
            GENERATOR.render_header(source)

    def test_rejects_invalid_manifest(self):
        with self.assertRaises(GENERATOR.bootstrap_kind_manifest.ManifestError):
            GENERATOR.render_header({"format": "wrong", "kinds": []})

    def test_check_mode_detects_stale_output(self):
        with tempfile.TemporaryDirectory(prefix="flang-kind-header-") as temporary:
            root = Path(temporary)
            manifest_path = root / "kinds.json"
            output_path = root / "ast_kinds.hpp"
            manifest_path.write_text(
                json.dumps(manifest(kind(1, "Fortran::parser::Node"))),
                encoding="utf-8",
            )
            output_path.write_text("stale\n", encoding="utf-8")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                status = GENERATOR.main(
                    [
                        "--manifest",
                        str(manifest_path),
                        "--output",
                        str(output_path),
                        "--check",
                    ]
                )

            self.assertEqual(status, 1)
            self.assertIn("kind header is stale", stderr.getvalue())

    def test_committed_header_is_fresh(self):
        with contextlib.redirect_stdout(io.StringIO()):
            status = GENERATOR.main(["--check"])

        self.assertEqual(status, 0)


if __name__ == "__main__":
    unittest.main()
