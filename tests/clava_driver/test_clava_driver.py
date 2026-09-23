from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import run


REPO_ROOT = Path(__file__).resolve().parents[2]
CLAVA_ENTRY = os.environ.get("FLANG_DRIVER_TEST_CLAVA")
QUERY_MODULE = os.environ.get("FLANG_DRIVER_TEST_QUERY_MODULE")


@unittest.skipUnless(
    CLAVA_ENTRY and QUERY_MODULE,
    "set FLANG_DRIVER_TEST_CLAVA and FLANG_DRIVER_TEST_QUERY_MODULE for the Clava integration tests",
)
class ClavaDriverIntegrationTests(unittest.TestCase):
    def _run_with_fake_protoc(self, protoc_exit: int) -> tuple[object, Path, list[str]]:
        temporary = tempfile.TemporaryDirectory(prefix="clava-driver-test-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        output_dir = root / "generated"
        protoc_log = root / "protoc-argv.json"
        fake_protoc = root / "fake-protoc"
        fake_protoc.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

arguments = sys.argv[1:]
Path(os.environ["FAKE_PROTOC_ARGV_PATH"]).write_text(json.dumps(arguments), encoding="utf-8")
failure = int(os.environ["FAKE_PROTOC_EXIT_CODE"])
if failure:
    raise SystemExit(failure)
cpp_output = next(item.split("=", 1)[1] for item in arguments if item.startswith("--cpp_out="))
output = Path(cpp_output)
(output / "flang_ast.pb.h").write_text("// fake protoc header\\n", encoding="utf-8")
(output / "flang_ast.pb.cc").write_text("// fake protoc source\\n", encoding="utf-8")
""",
            encoding="utf-8",
        )
        fake_protoc.chmod(0o755)

        header = REPO_ROOT / "generator" / "fixtures" / "parse_tree_fixture.hpp"
        header_root = REPO_ROOT / "generator"
        metadata = REPO_ROOT / "generator" / "metadata.json"
        command = [
            "bash",
            str(REPO_ROOT / "clava_driver" / "run.sh"),
            "--clava",
            str(CLAVA_ENTRY),
            "--query-module",
            str(QUERY_MODULE),
            "--header",
            str(header),
            "--header-root",
            str(header_root),
            "--metadata",
            str(metadata),
            "--output-dir",
            str(output_dir),
            "--protoc",
            str(fake_protoc),
        ]
        environment = {
            **os.environ,
            "FAKE_PROTOC_ARGV_PATH": str(protoc_log),
            "FAKE_PROTOC_EXIT_CODE": str(protoc_exit),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        result = run(command, capture_output=True, text=True, check=False, env=environment)
        recorded_args = json.loads(protoc_log.read_text(encoding="utf-8")) if protoc_log.exists() else []
        return result, output_dir, recorded_args

    def test_runs_fixture_generation_then_fake_protoc(self) -> None:
        result, output_dir, protoc_args = self._run_with_fake_protoc(0)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Clava analysis", result.stdout)
        self.assertIn("Python generation", result.stdout)
        self.assertIn("protoc generation", result.stdout)
        self.assertIn("[clava-driver] Complete:", result.stdout)
        self.assertEqual(
            protoc_args,
            [
                f"--proto_path={output_dir}",
                f"--cpp_out={output_dir}",
                str(output_dir / "flang_ast.proto"),
            ],
        )
        for filename in (
            "declarations.json",
            "flang_ast.proto",
            "producer.fragment.cpp",
            "flang_ast.pb.h",
            "flang_ast.pb.cc",
        ):
            self.assertTrue((output_dir / filename).is_file(), filename)

    def test_nonzero_protoc_exit_fails_the_clava_run_without_fallback(self) -> None:
        result, output_dir, protoc_args = self._run_with_fake_protoc(23)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("protoc generation failed with exit code 23", result.stdout + result.stderr)
        self.assertEqual(len(protoc_args), 3)
        self.assertTrue((output_dir / "declarations.json").is_file())
        self.assertTrue((output_dir / "flang_ast.proto").is_file())
        self.assertFalse((output_dir / "flang_ast.pb.h").exists())
        self.assertFalse((output_dir / "flang_ast.pb.cc").exists())


if __name__ == "__main__":
    unittest.main()
