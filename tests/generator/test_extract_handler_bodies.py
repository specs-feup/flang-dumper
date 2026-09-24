import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
EXTRACTOR_PATH = REPO / "generator" / "extract_handler_bodies.py"
INVENTORY_PATH = REPO / "scripts" / "inventory_dump_handlers.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXTRACTOR = load_module("extract_handler_bodies", EXTRACTOR_PATH)
INVENTORY = load_module("inventory_dump_handlers", INVENTORY_PATH)


class ExtractHandlerBodiesTest(unittest.TestCase):
    def setUp(self):
        self.source = '''
// DUMP_NODE(Fortran::parser::CommentedOut, { dump(v, "ignored"); })
const char *example = R"tag(DUMP_NODE(Fortran::parser::RawString, { nope(); }))tag";
DUMP_ENUM(Fortran::parser, Mode)
DUMP_NODE(Fortran::parser::Empty, {})
DUMP_NODE(Fortran::parser::Alpha,
          { dump("text with , ) and }", "label"); /*keep this comment*/ })
DUMP_NODE_MANUAL(
    Fortran::parser::Manual,
    {
      dump(std::pair<int, int>{1, 2}, "value");
      if (v.has_value()) { dump(v.value(), "nested"); }
    })
'''
        self.inventory = {
            "schema_version": 1,
            "registrations": INVENTORY.parse_registrations(self.source),
        }

    def test_extracts_only_explicit_node_bodies_and_preserves_body_text(self):
        result = EXTRACTOR.extract_handler_bodies(self.source, self.inventory)

        self.assertEqual(result["format"], "flang-handler-bodies/v1")
        self.assertEqual(
            [item["fully_qualified_type"] for item in result["handlers"]],
            ["Fortran::parser::Alpha", "Fortran::parser::Manual"],
        )
        alpha, manual = result["handlers"]
        self.assertEqual(alpha["registration"], "DUMP_NODE")
        self.assertEqual(alpha["source_line"], 6)
        self.assertEqual(
            alpha["body"],
            'dump("text with , ) and }", "label"); /*keep this comment*/',
        )
        self.assertEqual(manual["registration"], "DUMP_NODE_MANUAL")
        self.assertEqual(manual["source_line"], 8)
        self.assertEqual(
            manual["body"],
            'dump(std::pair<int, int>{1, 2}, "value");\n'
            '      if (v.has_value()) { dump(v.value(), "nested"); }',
        )

    def test_rejects_duplicate_names_and_inventory_count_mismatch(self):
        duplicate_source = self.source + '\nDUMP_NODE(Fortran::parser::Alpha, { dump(v, "again"); })\n'
        duplicate_inventory = {"schema_version": 1, "registrations": INVENTORY.parse_registrations(duplicate_source)}
        with self.assertRaisesRegex(EXTRACTOR.ExtractionError, "duplicate explicit-content registration"):
            EXTRACTOR.extract_handler_bodies(duplicate_source, duplicate_inventory)

        stale_inventory = json.loads(json.dumps(self.inventory))
        stale_inventory["registrations"] = [
            entry
            for entry in stale_inventory["registrations"]
            if entry["fully_qualified_type"] != "Fortran::parser::Manual"
        ]
        with self.assertRaisesRegex(EXTRACTOR.ExtractionError, "count mismatch"):
            EXTRACTOR.extract_handler_bodies(self.source, stale_inventory)

    def test_cli_writes_and_checks_a_fresh_artifact(self):
        with tempfile.TemporaryDirectory(prefix="flang-handler-bodies-") as temporary:
            root = Path(temporary)
            source_path = root / "plugin.cpp"
            inventory_path = root / "registrations.json"
            output_path = root / "handler_bodies.json"
            source_path.write_text(self.source, encoding="utf-8")
            inventory_path.write_text(json.dumps(self.inventory), encoding="utf-8")

            status = EXTRACTOR.main([str(source_path), str(inventory_path), "--output", str(output_path)])
            self.assertEqual(status, 0)
            expected = json.dumps(
                EXTRACTOR.extract_handler_bodies(self.source, self.inventory),
                indent=2,
                ensure_ascii=False,
            ) + "\n"
            self.assertEqual(output_path.read_text(encoding="utf-8"), expected)
            self.assertEqual(
                EXTRACTOR.main(
                    [str(source_path), str(inventory_path), "--output", str(output_path), "--check"]
                ),
                0,
            )

            output_path.write_text("{}\n", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = EXTRACTOR.main(
                    [str(source_path), str(inventory_path), "--output", str(output_path), "--check"]
                )
            self.assertEqual(status, 2)
            self.assertIn("is stale", stderr.getvalue())
            self.assertEqual(output_path.read_text(encoding="utf-8"), "{}\n")


if __name__ == "__main__":
    unittest.main()
