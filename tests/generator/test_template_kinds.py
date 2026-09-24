import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "generator" / "template_kinds.json"
EXISTING_MANIFEST = REPO / "generator" / "kinds.json"
HEADER = REPO / "protocol" / "template_kinds.hpp"


class TemplateKindsTest(unittest.TestCase):
    def test_manifest_has_exact_reviewed_template_kinds(self):
        document = json.loads(MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(
            document,
            {
                "format": "flang-template-kinds/v1",
                "template_kinds": [
                    {
                        "id": 1000001,
                        "cpp_type": "Fortran::parser::Statement",
                        "kind_name": "Statement",
                    },
                    {
                        "id": 1000002,
                        "cpp_type": "Fortran::parser::UnlabeledStatement",
                        "kind_name": "UnlabeledStatement",
                    },
                ],
            },
        )

    def test_template_kind_ids_do_not_collide_with_registered_kinds(self):
        template_document = json.loads(MANIFEST.read_text(encoding="utf-8"))
        registered_document = json.loads(
            EXISTING_MANIFEST.read_text(encoding="utf-8")
        )
        template_ids = {
            item["id"] for item in template_document["template_kinds"]
        }
        registered_ids = {item["id"] for item in registered_document["kinds"]}

        self.assertTrue(template_ids.isdisjoint(registered_ids))

    def test_header_compiles_with_cpp17_static_asserts(self):
        compiler = (
            shutil.which("c++")
            or shutil.which("g++")
            or shutil.which("clang++")
        )
        self.assertIsNotNone(compiler, "a C++ compiler is required for this test")

        source = r'''#include "template_kinds.hpp"

static_assert(flang_dumper::kStatementTemplateKindId == 1000001U);
static_assert(flang_dumper::kUnlabeledStatementTemplateKindId == 1000002U);
static_assert(flang_dumper::kTemplateKindCount == 2U);
static_assert(flang_dumper::find_template_kind_by_name("Statement") !=
              nullptr);
static_assert(
    flang_dumper::find_template_kind_by_name("Statement")->id == 1000001U);
static_assert(flang_dumper::find_template_kind_by_name("UnlabeledStatement")
                  ->id == 1000002U);
static_assert(flang_dumper::find_template_kind_by_name("Unknown") == nullptr);

int main() {}
'''
        with tempfile.TemporaryDirectory(prefix="flang-template-kinds-") as temporary:
            source_path = Path(temporary) / "template_kinds_test.cpp"
            source_path.write_text(source, encoding="utf-8")
            subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-fsyntax-only",
                    "-I",
                    str(HEADER.parent),
                    str(source_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()
