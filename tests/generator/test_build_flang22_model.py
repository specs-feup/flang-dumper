import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "generator" / "build_flang22_model.py"
SPEC = importlib.util.spec_from_file_location("build_flang22_model", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def model_for(header: Path, header_root: Path, qualified_name: str, digest: str) -> dict:
    relative_header = header.relative_to(header_root).as_posix()
    location = {"file": relative_header, "line": 1, "column": 1, "end_line": 1, "end_column": 10}
    return {
        "format": "clava-declaration-inventory/v1",
        "source_header": {"file": relative_header, "sha256": digest},
        "source_files": [{"file": relative_header, "sha256": digest}],
        "declarations": [
            {
                "kind": "record",
                "qualified_name": qualified_name,
                "location": location,
                "members": [
                    {
                        "name": "value",
                        "type": "int",
                        "location": {"file": relative_header, "line": 1, "column": 3, "end_line": 1, "end_column": 8},
                    }
                ],
            }
        ],
    }


class BuildFlang22ModelTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="flang22-model-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.header_root = self.root / "usr"
        self.include_dir = self.header_root / "lib" / "llvm-22" / "include"
        for relative_header, _ast_filter in BUILDER.HEADER_FILTERS:
            header = self.include_dir / relative_header
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text("struct Fixture { int value; };\n", encoding="utf-8")

    def test_uses_fixed_headers_filters_and_parse_tree_as_merge_primary(self):
        calls = []

        def analyze(**kwargs):
            calls.append(kwargs)
            index = len(calls) - 1
            names = [
                "Fortran::parser::ParseTreeFixture",
                "Fortran::common::SupportFixture",
                "Fortran::format::FormatFixture",
            ]
            return model_for(kwargs["header"], self.header_root, names[index], f"{index + 1:x}" * 64)

        with mock.patch.object(BUILDER.ANALYZER, "analyze", side_effect=analyze):
            result = BUILDER.build_model(
                header_root=self.header_root,
                include_dir=self.include_dir,
                clang_command="clang++-21 --target=x86_64-linux-gnu",
            )

        self.assertEqual(
            [call["header"] for call in calls],
            [self.include_dir / relative for relative, _ in BUILDER.HEADER_FILTERS],
        )
        self.assertEqual(
            [call["ast_filter"] for call in calls],
            ["Fortran::parser", "Fortran::common", "Fortran::format"],
        )
        self.assertEqual([call["qualified_prefix"] for call in calls], ["Fortran"] * 3)
        self.assertEqual([call["include_dirs"] for call in calls], [[self.include_dir]] * 3)
        self.assertEqual([call["compiler"] for call in calls], ["clang++-21 --target=x86_64-linux-gnu"] * 3)
        self.assertEqual(
            result["source_header"]["file"],
            "lib/llvm-22/include/flang/Parser/parse-tree.h",
        )
        self.assertEqual(
            [declaration["qualified_name"] for declaration in result["declarations"]],
            ["Fortran::common::SupportFixture", "Fortran::format::FormatFixture", "Fortran::parser::ParseTreeFixture"],
        )

    def test_analyzer_failure_returns_error_without_writing_output(self):
        output = self.root / "model.json"
        with mock.patch.object(
            BUILDER.ANALYZER,
            "analyze",
            side_effect=BUILDER.ANALYZER.AnalyzerError("Clang failed"),
        ):
            result = BUILDER.main(
                ["--header-root", str(self.header_root), "--include-dir", str(self.include_dir), "--output", str(output)]
            )
        self.assertEqual(result, 2)
        self.assertFalse(output.exists())

    def test_check_passes_on_identical_model_and_fails_on_drift(self):
        outputs = self.root / "model.json"
        names = [
            "Fortran::parser::ParseTreeFixture",
            "Fortran::common::SupportFixture",
            "Fortran::format::FormatFixture",
        ]

        def analyze(**kwargs):
            index = BUILDER.HEADER_FILTERS.index(
                (kwargs["header"].relative_to(self.include_dir).as_posix(), kwargs["ast_filter"])
            )
            return model_for(kwargs["header"], self.header_root, names[index], f"{index + 1:x}" * 64)

        with mock.patch.object(BUILDER.ANALYZER, "analyze", side_effect=analyze):
            built = BUILDER.build_model(
                header_root=self.header_root,
                include_dir=self.include_dir,
                clang_command="clang++-21",
            )
            outputs.write_text(BUILDER.serialize_model(built), encoding="utf-8")
            common = ["--header-root", str(self.header_root), "--include-dir", str(self.include_dir), "--output", str(outputs)]
            self.assertEqual(BUILDER.main([*common, "--check"]), 0)
            outputs.write_text("{}\n", encoding="utf-8")
            self.assertEqual(BUILDER.main([*common, "--check"]), 1)
            self.assertEqual(json.loads(outputs.read_text(encoding="utf-8")), {})


if __name__ == "__main__":
    unittest.main()
