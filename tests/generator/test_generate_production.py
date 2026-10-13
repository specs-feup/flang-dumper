import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
GENERATOR = REPO / "generator" / "generate_production.py"
PIN = REPO / "generator" / "flang22-declarations.json"
SCHEMA = REPO / "protocol" / "ast_stream.proto"
SPEC = importlib.util.spec_from_file_location("generate_production", GENERATOR)
assert SPEC is not None and SPEC.loader is not None
PRODUCTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PRODUCTION)


class ProductionGeneratorTest(unittest.TestCase):
    def test_malformed_registration_manifest_fails_before_header_analysis(self):
        with tempfile.TemporaryDirectory(prefix="flang-production-bad-manifest-") as temporary:
            root = Path(temporary)
            malformed = root / "registrations.json"
            malformed.write_text('{"schema_version":99,"registrations":[]}', encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    "--analyzer",
                    "clang",
                    "--header-root",
                    str(root),
                    "--include-dir",
                    str(root),
                    "--output-dir",
                    str(root / "output"),
                    "--protoc",
                    str(root / "missing-protoc"),
                    "--registrations",
                    str(malformed),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("schema_version 1", result.stderr)
            self.assertNotIn("cannot start", result.stderr)
            self.assertFalse((root / "output").exists())

    def test_stale_pinned_header_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="flang-production-stale-header-") as temporary:
            root = Path(temporary) / "usr"
            relative = "lib/llvm-22/include/flang/Parser/parse-tree.h"
            source = root / relative
            source.parent.mkdir(parents=True)
            source.write_text("struct PinnedHeader {}\n", encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            model = {
                "format": "clava-declaration-inventory/v1",
                "source_header": {"file": relative, "sha256": digest},
                "source_files": [{"file": relative, "sha256": digest}],
                "declarations": [],
            }
            include_dir = root / "lib/llvm-22/include"
            PRODUCTION.validate_model_against_pin(model, model, root, include_dir)

            source.write_text("struct ChangedHeader {}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                PRODUCTION.ProductionGenerationError, "pinned Flang header input is stale"
            ):
                PRODUCTION.validate_model_against_pin(model, model, root, include_dir)

    def test_two_production_runs_are_byte_identical_when_toolchain_is_configured(self):
        header_root = os.environ.get("FLANG22_HEADER_ROOT")
        include_dir = os.environ.get("FLANG22_INCLUDE_DIR")
        protoc = os.environ.get("PROTOC")
        if not header_root or not include_dir or not protoc:
            self.skipTest(
                "set FLANG22_HEADER_ROOT, FLANG22_INCLUDE_DIR, and PROTOC for the real Flang generation check"
            )

        analyzer = os.environ.get("FLANG22_ANALYZER", "snapshot")
        with tempfile.TemporaryDirectory(prefix="flang-production-determinism-") as temporary:
            root = Path(temporary)
            output_dirs = [root / "first", root / "second"]
            for output in output_dirs:
                invocation = [
                    sys.executable,
                    str(GENERATOR),
                    "--analyzer",
                    analyzer,
                    "--header-root",
                    header_root,
                    "--include-dir",
                    include_dir,
                    "--output-dir",
                    str(output),
                    "--protoc",
                    protoc,
                ]
                if analyzer == "snapshot":
                    invocation.extend(["--inventory", str(PIN)])
                elif analyzer == "clang":
                    invocation.extend(
                        ["--clang-command", os.environ.get("FLANG22_CLANG_COMMAND", "clang++-21")]
                    )
                elif analyzer == "clava":
                    clava_entry = os.environ.get("FLANG22_CLAVA_ENTRY")
                    query_module = os.environ.get("FLANG22_QUERY_MODULE")
                    if not clava_entry or not query_module:
                        self.skipTest(
                            "FLANG22_ANALYZER=clava also requires FLANG22_CLAVA_ENTRY and FLANG22_QUERY_MODULE"
                        )
                    invocation.extend(
                        ["--clava-entry", clava_entry, "--query-module", query_module]
                    )
                result = subprocess.run(
                    invocation, capture_output=True, text=True, check=False
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            def files(directory: Path) -> dict[str, bytes]:
                return {
                    path.relative_to(directory).as_posix(): path.read_bytes()
                    for path in sorted(directory.rglob("*"))
                    if path.is_file()
                }

            self.assertEqual(files(output_dirs[0]), files(output_dirs[1]))
            self.assertEqual(
                (output_dirs[0] / "ast_stream.proto").read_bytes(), SCHEMA.read_bytes()
            )
            coverage = json.loads(
                (output_dirs[0] / "handler-coverage.json").read_text(encoding="utf-8")
            )
            self.assertEqual(coverage["summary"]["registration_count"], 865)
            self.assertEqual(coverage["summary"]["unregistered_header_count"], 199)


if __name__ == "__main__":
    unittest.main()
