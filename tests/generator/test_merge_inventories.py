import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MERGER_PATH = REPO / "generator" / "merge_inventories.py"
SPEC = importlib.util.spec_from_file_location("merge_inventories", MERGER_PATH)
assert SPEC is not None and SPEC.loader is not None
MERGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MERGER)


def inventory(header, header_digest, declaration, source_files=None):
    return {
        "format": "clava-declaration-inventory/v1",
        "source_header": {"file": header, "sha256": header_digest},
        "source_files": source_files or [{"file": header, "sha256": header_digest}],
        "declarations": [declaration],
    }


def record(name, file_path, member_name="value", member_type="int"):
    location = {"file": file_path, "line": 1, "column": 1, "end_line": 2, "end_column": 1}
    return {
        "kind": "record",
        "qualified_name": name,
        "location": location,
        "members": [
            {
                "name": member_name,
                "type": member_type,
                "location": {"file": file_path, "line": 2, "column": 3, "end_line": 2, "end_column": 12},
            }
        ],
    }


def enum(name, file_path):
    return {
        "kind": "enum",
        "qualified_name": name,
        "location": {"file": file_path, "line": 1, "column": 1, "end_line": 1, "end_column": 10},
        "constants": [
            {
                "name": "First",
                "source": "ENUM_CLASS",
                "location": {"file": file_path, "line": 1, "column": 1, "end_line": 1, "end_column": 10},
            }
        ],
    }


class MergeInventoriesTest(unittest.TestCase):
    def test_union_is_sorted_and_reproducible(self):
        parse_tree = inventory(
            "include/flang/Parser/parse-tree.h",
            "a" * 64,
            record("Fortran::parser::Zed", "include/flang/Parser/parse-tree.h"),
            [
                {"file": "include/flang/Parser/parse-tree.h", "sha256": "a" * 64},
                {"file": "include/flang/Common/Shared.h", "sha256": "c" * 64},
            ],
        )
        support = inventory(
            "include/flang/Support/Fortran.h",
            "b" * 64,
            record("Fortran::common::Alpha", "include/flang/Support/Fortran.h"),
            [
                {"file": "include/flang/Support/Fortran.h", "sha256": "b" * 64},
                {"file": "include/flang/Common/Shared.h", "sha256": "c" * 64},
            ],
        )
        expected = MERGER.merge_inventories([parse_tree, support])

        self.assertEqual(expected["source_header"], parse_tree["source_header"])
        self.assertEqual(
            [item["file"] for item in expected["source_files"]],
            [
                "include/flang/Common/Shared.h",
                "include/flang/Parser/parse-tree.h",
                "include/flang/Support/Fortran.h",
            ],
        )
        self.assertEqual(
            [item["qualified_name"] for item in expected["declarations"]],
            ["Fortran::common::Alpha", "Fortran::parser::Zed"],
        )
        self.assertEqual(expected, MERGER.merge_inventories([parse_tree, support]))

    def test_identical_duplicate_declaration_is_idempotent(self):
        declaration = record("Fortran::common::Shared", "include/Fortran.h")
        first = inventory("include/Fortran.h", "a" * 64, declaration)
        second = inventory(
            "include/Other.h",
            "b" * 64,
            declaration,
            [
                {"file": "include/Other.h", "sha256": "b" * 64},
                {"file": "include/Fortran.h", "sha256": "a" * 64},
            ],
        )

        result = MERGER.merge_inventories([first, second])

        self.assertEqual(result["declarations"], [declaration])

    def test_rejects_duplicate_with_different_member_layout(self):
        original = record("Fortran::common::Shared", "include/Fortran.h")
        changed_layout = record(
            "Fortran::common::Shared", "include/Other.h", member_name="different"
        )
        first = inventory("include/Fortran.h", "a" * 64, original)
        second = inventory("include/Other.h", "b" * 64, changed_layout)

        with self.assertRaisesRegex(MERGER.MergeError, "conflicting duplicate declaration"):
            MERGER.merge_inventories([first, second])

    def test_rejects_duplicate_with_different_kind(self):
        name = "Fortran::common::Shared"
        first = inventory("include/Fortran.h", "a" * 64, record(name, "include/Fortran.h"))
        second = inventory("include/Other.h", "b" * 64, enum(name, "include/Other.h"))

        with self.assertRaisesRegex(MERGER.MergeError, "conflicting duplicate declaration"):
            MERGER.merge_inventories([first, second])

    def test_rejects_source_digest_conflict(self):
        first = inventory(
            "include/First.h",
            "a" * 64,
            record("Fortran::one::A", "include/First.h"),
            [
                {"file": "include/First.h", "sha256": "a" * 64},
                {"file": "include/Shared.h", "sha256": "c" * 64},
            ],
        )
        second = inventory(
            "include/Second.h",
            "b" * 64,
            record("Fortran::two::B", "include/Second.h"),
            [
                {"file": "include/Second.h", "sha256": "b" * 64},
                {"file": "include/Shared.h", "sha256": "d" * 64},
            ],
        )

        with self.assertRaisesRegex(MERGER.MergeError, "source digest conflict.*include/Shared.h"):
            MERGER.merge_inventories([first, second])

    def test_rejects_case_only_path_collision(self):
        first = inventory("include/Flang.h", "a" * 64, record("Fortran::one::A", "include/Flang.h"))
        second = inventory("include/flang.h", "b" * 64, record("Fortran::two::B", "include/flang.h"))

        with self.assertRaisesRegex(MERGER.MergeError, "source path collision"):
            MERGER.merge_inventories([first, second])

    def test_rejects_missing_or_malformed_hash(self):
        model = inventory("include/Fortran.h", "a" * 64, record("Fortran::common::A", "include/Fortran.h"))
        del model["source_header"]["sha256"]
        with self.assertRaisesRegex(MERGER.MergeError, "source_header.sha256"):
            MERGER.merge_inventories([model])

        model = inventory("include/Fortran.h", "A" * 64, record("Fortran::common::A", "include/Fortran.h"))
        with self.assertRaisesRegex(MERGER.MergeError, "lowercase SHA-256"):
            MERGER.merge_inventories([model])

    def test_rejects_noncanonical_paths_and_declarations_missing_hash_sources(self):
        model = inventory("include/../Fortran.h", "a" * 64, record("Fortran::common::A", "include/../Fortran.h"))
        with self.assertRaisesRegex(MERGER.MergeError, "canonical relative POSIX path"):
            MERGER.merge_inventories([model])

        model = inventory("include/Fortran.h", "a" * 64, record("Fortran::common::A", "include/Missing.h"))
        with self.assertRaisesRegex(MERGER.MergeError, "absent from source_files"):
            MERGER.merge_inventories([model])

    def test_cli_writes_output_and_never_overwrites_an_input(self):
        model = inventory("include/Fortran.h", "a" * 64, record("Fortran::common::A", "include/Fortran.h"))
        with tempfile.TemporaryDirectory(prefix="flang-inventory-merge-") as temporary:
            root = Path(temporary)
            input_path = root / "input.json"
            output_path = root / "merged.json"
            input_path.write_text(json.dumps(model), encoding="utf-8")

            self.assertEqual(
                MERGER.main([str(input_path), "--output", str(output_path)]), 0
            )
            self.assertEqual(json.loads(output_path.read_text()), model)
            self.assertEqual(
                MERGER.main([str(input_path), "--output", str(input_path)]), 2
            )
            self.assertEqual(json.loads(input_path.read_text()), model)


if __name__ == "__main__":
    unittest.main()
