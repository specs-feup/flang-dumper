import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
GENERATOR = REPO / "generator" / "generate.py"
METADATA = REPO / "generator" / "metadata.json"
HEADER = REPO / "generator" / "fixtures" / "parse_tree_fixture.hpp"
INVENTORY = Path(__file__).parent / "fixtures" / "clava-inventory.json"
OUTPUTS = ("declarations.json", "flang_ast.proto", "producer.fragment.cpp")


class GeneratorTest(unittest.TestCase):
    def test_clava_inventory_matches_fixture_and_regeneration_is_byte_equal(self):
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
        self.assertEqual(inventory["source_header"]["file"], "fixtures/parse_tree_fixture.hpp")
        self.assertEqual(
            inventory["source_header"]["sha256"],
            hashlib.sha256(HEADER.read_bytes()).hexdigest(),
        )

        with tempfile.TemporaryDirectory(prefix="flang-generator-test-") as temporary:
            root = Path(temporary)
            output_a = root / "a"
            output_b = root / "b"
            for output in (output_a, output_b):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(GENERATOR),
                        "--metadata",
                        str(METADATA),
                        "--model",
                        str(INVENTORY),
                        "--output-dir",
                        str(output),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            for name in OUTPUTS:
                self.assertEqual((output_a / name).read_bytes(), (output_b / name).read_bytes(), name)

            schema = (output_a / "flang_ast.proto").read_text(encoding="utf-8")
            producer = (output_a / "producer.fragment.cpp").read_text(encoding="utf-8")
            self.assertIn("float real = 1;", schema)
            self.assertIn("optional float value = 1;", schema)
            self.assertIn("EXPRESSION_OPERATION_ADD = 1;", schema)
            self.assertIn("map_ExpressionOperation(node.operation)", producer)

    def test_unmapped_clava_declaration_fails_closed(self):
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
        inventory["declarations"].append(
            {
                "kind": "record",
                "qualified_name": "generator_fixture::UnknownRecord",
                "location": {
                    "file": "fixtures/parse_tree_fixture.hpp",
                    "line": 1,
                    "column": 1,
                },
                "members": [],
            }
        )

        with tempfile.TemporaryDirectory(prefix="flang-generator-negative-") as temporary:
            root = Path(temporary)
            model_path = root / "unmapped.json"
            model_path.write_text(json.dumps(inventory), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    "--metadata",
                    str(METADATA),
                    "--model",
                    str(model_path),
                    "--output-dir",
                    str(root / "generated"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("Unmapped declarations in Clava inventory", result.stderr)
            self.assertIn("generator_fixture::UnknownRecord", result.stderr)

    def test_saved_model_with_changed_header_digest_is_rejected(self):
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
        inventory["source_header"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory(prefix="flang-generator-stale-") as temporary:
            model_path = Path(temporary) / "stale.json"
            model_path.write_text(json.dumps(inventory), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(GENERATOR), "--model", str(model_path),
                 "--output-dir", str(Path(temporary) / "generated")],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("Clava model is stale", result.stderr)

    def test_saved_multifile_model_with_changed_included_file_is_rejected(self):
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="flang-generator-included-stale-") as temporary:
            root = Path(temporary)
            header_path = root / "fixtures" / "parse_tree_fixture.hpp"
            included_path = root / "includes" / "omp.inc"
            header_path.parent.mkdir(parents=True)
            included_path.parent.mkdir(parents=True)
            header_path.write_bytes(HEADER.read_bytes())
            included_path.write_text("struct IncludedMarker {};\n", encoding="utf-8")

            inventory["declarations"][0]["members"][0]["location"]["file"] = "includes/omp.inc"
            inventory["source_files"] = [
                {
                    "file": "fixtures/parse_tree_fixture.hpp",
                    "sha256": hashlib.sha256(header_path.read_bytes()).hexdigest(),
                },
                {
                    "file": "includes/omp.inc",
                    "sha256": hashlib.sha256(included_path.read_bytes()).hexdigest(),
                },
            ]
            model_path = root / "inventory.json"
            model_path.write_text(json.dumps(inventory), encoding="utf-8")

            command = [
                sys.executable,
                str(GENERATOR),
                "--header",
                str(header_path),
                "--header-root",
                str(root),
                "--metadata",
                str(METADATA),
                "--model",
                str(model_path),
                "--output-dir",
                str(root / "generated"),
            ]
            fresh = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(fresh.returncode, 0, fresh.stdout + fresh.stderr)

            included_path.write_text("struct ChangedMarker {};\n", encoding="utf-8")
            stale = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(stale.returncode, 2, stale.stdout + stale.stderr)
            self.assertIn("stale for source file 'includes/omp.inc'", stale.stderr)

if __name__ == "__main__":
    unittest.main()
