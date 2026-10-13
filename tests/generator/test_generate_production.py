import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def test_namespace_drift_is_rejected_by_the_pinned_model(self):
        with tempfile.TemporaryDirectory(prefix="flang-production-namespace-pin-") as temporary:
            root = Path(temporary) / "usr"
            relative = "lib/llvm-22/include/flang/Parser/parse-tree.h"
            source = root / relative
            source.parent.mkdir(parents=True)
            source.write_text("struct PinnedHeader {};\n", encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            location = {
                "file": relative,
                "line": 1,
                "column": 1,
                "end_line": 1,
                "end_column": 2,
            }
            declaration = {
                "kind": "record",
                "qualified_name": "Fortran::parser::PinnedHeader",
                "location": location,
                "members": [],
            }
            pinned_model = {
                "format": "clava-declaration-inventory/v1",
                "source_header": {"file": relative, "sha256": digest},
                "source_files": [{"file": relative, "sha256": digest}],
                "declarations": [declaration],
            }
            changed_model = json.loads(json.dumps(pinned_model))
            changed_model["declarations"][0]["qualified_name"] = "Fortran::other::PinnedHeader"

            with self.assertRaisesRegex(
                PRODUCTION.ProductionGenerationError,
                "fresh analyzer model differs.*missing declarations.*Fortran::parser::PinnedHeader",
            ):
                PRODUCTION.validate_model_against_pin(
                    changed_model,
                    pinned_model,
                    root,
                    root / "lib/llvm-22/include",
                )

    def test_clava_uses_one_probe_tu_and_preserves_header_hashes_and_prefixes(self):
        with tempfile.TemporaryDirectory(prefix="flang-production-clava-probes-") as temporary:
            root = Path(temporary) / "usr"
            include_dir = root / "lib/llvm-22/include"
            include_dir.mkdir(parents=True)
            clava_entry = Path(temporary) / "clava-index.ts"
            query_module = Path(temporary) / "Query.ts"
            clava_entry.write_text("// Clava entry\n", encoding="utf-8")
            query_module.write_text("// Query module\n", encoding="utf-8")

            expected_headers: list[tuple[Path, str, str]] = []
            for index, (relative_header, prefix) in enumerate(PRODUCTION.HEADER_FILTERS):
                header = include_dir / relative_header
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text(f"struct Header{index} {{}};\n", encoding="utf-8")
                expected_headers.append((header, relative_header, prefix))

            invocations: list[list[str]] = []

            def fake_run(invocation, *, cwd, env, **kwargs):
                self.assertEqual(cwd, PRODUCTION.REPO_ROOT)
                index = len(invocations)
                self.assertLess(index, len(expected_headers))
                invocations.append(list(invocation))
                header, relative_header, prefix = expected_headers[index]
                probe_dir = Path(invocation[invocation.index("-p") + 1])
                self.assertEqual(sorted(path.name for path in probe_dir.iterdir()), ["probe.cpp"])
                self.assertEqual(
                    (probe_dir / "probe.cpp").read_text(encoding="utf-8"),
                    f'#include "{Path(relative_header).as_posix()}"\n',
                )
                self.assertEqual(env["FLANG_GENERATOR_HEADER"], str(header.resolve()))
                self.assertEqual(env["FLANG_GENERATOR_QUALIFIED_PREFIX"], prefix)
                self.assertEqual(env["FLANG_GENERATOR_HEADER_ROOT"], str(root.resolve()))
                self.assertIn("-fs", invocation)
                self.assertFalse(any(argument.startswith("-I") for argument in invocation))
                self.assertNotIn("-is", invocation)
                self.assertEqual(
                    invocation[invocation.index("-fs") + 1],
                    f"-iquote {include_dir.resolve()} -isystem {include_dir.resolve()}",
                )
                self.assertEqual(invocation[invocation.index("-ist") + 1], "0")

                relative_source = header.relative_to(root).as_posix()
                digest = hashlib.sha256(header.read_bytes()).hexdigest()
                location = {
                    "file": relative_source,
                    "line": 1,
                    "column": 1,
                    "end_line": 1,
                    "end_column": 2,
                }
                model = {
                    "format": "clava-declaration-inventory/v1",
                    "source_header": {"file": relative_source, "sha256": digest},
                    "source_files": [{"file": relative_source, "sha256": digest}],
                    "declarations": [
                        {
                            "kind": "record",
                            "qualified_name": f"{prefix}::InventoryProbe{index}",
                            "location": location,
                            "members": [],
                        }
                    ],
                }
                Path(env["FLANG_GENERATOR_MODEL_OUT"]).write_text(
                    json.dumps(model), encoding="utf-8"
                )
                return subprocess.CompletedProcess(invocation, 0, "")

            with patch.object(PRODUCTION.shutil, "which", return_value="/usr/bin/node"), patch.object(
                PRODUCTION.subprocess, "run", side_effect=fake_run
            ):
                model = PRODUCTION._clava_model(
                    header_root=root,
                    include_dir=include_dir,
                    clava_entry=clava_entry,
                    query_module=query_module,
                    python_cwd=PRODUCTION.REPO_ROOT,
                )

            self.assertEqual(len(invocations), len(PRODUCTION.HEADER_FILTERS))
            self.assertEqual(
                model["source_header"],
                {
                    "file": expected_headers[0][0].relative_to(root).as_posix(),
                    "sha256": hashlib.sha256(expected_headers[0][0].read_bytes()).hexdigest(),
                },
            )
            self.assertEqual(
                [item["qualified_name"] for item in model["declarations"]],
                sorted(
                    f"{prefix}::InventoryProbe{index}"
                    for index, (_, _, prefix) in enumerate(expected_headers)
                ),
            )
            for header, _, _ in expected_headers:
                relative_source = header.relative_to(root).as_posix()
                self.assertIn(
                    {"file": relative_source, "sha256": hashlib.sha256(header.read_bytes()).hexdigest()},
                    model["source_files"],
                )

    def test_clava_parse_failure_stops_without_fallback(self):
        with tempfile.TemporaryDirectory(prefix="flang-production-clava-failure-") as temporary:
            root = Path(temporary) / "usr"
            include_dir = root / "lib/llvm-22/include"
            clava_entry = Path(temporary) / "clava-index.ts"
            query_module = Path(temporary) / "Query.ts"
            clava_entry.touch()
            query_module.touch()
            header = include_dir / PRODUCTION.HEADER_FILTERS[0][0]
            header.parent.mkdir(parents=True)
            header.touch()
            calls = []

            def failing_run(invocation, **kwargs):
                calls.append(invocation)
                return subprocess.CompletedProcess(
                    invocation, 19, "error: synthetic Clava parse failure\n"
                )

            with patch.object(PRODUCTION.shutil, "which", return_value="/usr/bin/node"), patch.object(
                PRODUCTION.subprocess, "run", side_effect=failing_run
            ):
                with self.assertRaisesRegex(
                    PRODUCTION.ProductionGenerationError,
                    "(?s)selected Clava analyzer failed.*parse-tree.h.*exit code 19.*synthetic Clava parse failure",
                ):
                    PRODUCTION._clava_model(
                        header_root=root,
                        include_dir=include_dir,
                        clava_entry=clava_entry,
                        query_module=query_module,
                        python_cwd=PRODUCTION.REPO_ROOT,
                    )

            self.assertEqual(len(calls), 1)

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
