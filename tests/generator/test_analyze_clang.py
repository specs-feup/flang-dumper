import importlib.util
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ANALYZER_PATH = REPO / "generator" / "analyze_clang.py"
SPEC = importlib.util.spec_from_file_location("analyze_clang", ANALYZER_PATH)
assert SPEC is not None and SPEC.loader is not None
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


class ClangAnalyzerLocationTest(unittest.TestCase):
    def test_macro_decl_uses_spelling_location_when_it_names_the_declaration(self):
        with tempfile.TemporaryDirectory(prefix="flang-generator-macro-location-") as temporary:
            header = Path(temporary) / "parse-tree.h"
            source = b"EMPTY_CLASS(ErrorRecovery)\n"
            header.write_bytes(source)
            name_offset = source.index(b"ErrorRecovery")
            location = {
                "spellingLoc": {
                    "file": str(header),
                    "offset": name_offset,
                    "line": 1,
                    "col": name_offset + 1,
                    "tokLen": len(b"ErrorRecovery"),
                },
                "expansionLoc": {
                    "file": str(header),
                    "offset": 0,
                    "line": 1,
                    "col": 1,
                    "tokLen": len(b"EMPTY_CLASS"),
                },
            }

            result = ANALYZER._declaration_location(location, "ErrorRecovery", str(header), {}, {})

            self.assertEqual(result["offset"], name_offset)
            self.assertEqual(result["file"], str(header.resolve()))
            self.assertEqual(source[result["offset"] : result["offset"] + result["tokLen"]], b"ErrorRecovery")

    def test_cross_file_range_uses_the_field_identifier_location(self):
        with tempfile.TemporaryDirectory(prefix="flang-generator-cross-file-range-") as temporary:
            root = Path(temporary).resolve()
            header = root / "flang" / "parse-tree.h"
            macro_header = root / "llvm" / "OMP.inc"
            header.parent.mkdir()
            macro_header.parent.mkdir()
            header.write_text("#include \"../llvm/OMP.inc\"\n", encoding="utf-8")
            macro_source = "struct Absent { int v; };\n"
            macro_header.write_text(macro_source, encoding="utf-8")
            field_offset = macro_source.index("v;")
            field_column = field_offset + 1
            macro_end = len(macro_source.rstrip("\n")) - 1
            node = {
                "kind": "FieldDecl",
                "name": "v",
                "loc": {
                    "file": str(macro_header),
                    "offset": field_offset,
                    "line": 1,
                    "col": field_column,
                    "tokLen": 1,
                },
                "range": {
                    "begin": {
                        "file": str(header),
                        "offset": 0,
                        "line": 1,
                        "col": 1,
                        "tokLen": 8,
                    },
                    "end": {
                        "file": str(macro_header),
                        "offset": macro_end,
                        "line": 1,
                        "col": macro_end + 1,
                        "tokLen": 1,
                    },
                },
            }

            result = ANALYZER._source_location(
                node,
                str(header),
                root,
                {},
                {},
                description="field Fortran::parser::OmpClause::Absent.v",
            )

            self.assertEqual(
                result,
                {
                    "file": "llvm/OMP.inc",
                    "line": 1,
                    "column": field_column,
                    "end_line": 1,
                    "end_column": field_column,
                },
            )


if __name__ == "__main__":
    unittest.main()
