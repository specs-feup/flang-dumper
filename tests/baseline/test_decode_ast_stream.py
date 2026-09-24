from __future__ import annotations

import json
import os
import shutil
import struct
import sys
import unittest
from pathlib import Path


BASELINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASELINE_DIR))

from compare_graphs import JsonObject, compare_graphs  # noqa: E402
from decode_ast_stream import (  # noqa: E402
    MAGIC,
    MAX_RECORD_SIZE,
    _json_text,
    _load_record_class,
    decode_stream,
)


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while value >= 0x80:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _header(version: int = 1) -> bytes:
    return MAGIC + struct.pack("<I", version)


def _frame(payload: bytes) -> bytes:
    return _varint(len(payload)) + payload


class DecodeAstStreamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        protoc = os.environ.get("PROTOC") or shutil.which("protoc")
        if not protoc:
            raise RuntimeError("set PROTOC or add protoc to PATH to run decoder tests")
        cls.Record = _load_record_class(protoc)

    def _new_record(self, variant: str):
        record = self.Record()
        return record, getattr(record, variant)

    def _node_record(self, node_id: int, kind_id: int, kind_name: str):
        record, node = self._new_record("node")
        node.node_id = node_id
        node.kind_id = kind_id
        node.kind_name = kind_name
        return record, node

    def _stream(self, *records) -> bytes:
        return _header() + b"".join(_frame(record.SerializeToString()) for record in records)

    def test_forward_refs_duplicate_attributes_lists_comments_and_enums(self) -> None:
        root_record, root = self._node_record(0x10, 1, "Program")
        root.attributes.add(key="statement").value.node_reference = 0x20
        root.attributes.add(key="label").value.string_value = "first"
        root.attributes.add(key="label").value.string_value = "second"
        root.attributes.add(key="empty").value.list_value.SetInParent()

        nested = root.attributes.add(key="items").value.list_value.items
        nested.add().string_value = "x"
        nested.add().list_value.items.add().integer_value = 5
        nested.add().uint64_value = 0xFFFFFFFFFFFFFFFF
        root.attributes.add(key="integer").value.integer_value = -7
        root.attributes.add(key="unsigned").value.uint64_value = 0xFFFFFFFFFFFFFFFF
        root.attributes.add(key="enabled").value.bool_value = True
        root.attributes.add(key="ratio").value.double_value = 1.25

        comment_record, comment = self._new_record("comment")
        comment.text = "! trailing"
        comment.stmt_node_id = 0x20
        comment.trailing = True

        enum_record, enum_catalog = self._new_record("enum_catalog")
        enum_catalog.enum_type_name = "UseStmt::ModuleNature"
        enum_catalog.entries.add(name="Intrinsic", number=0)
        enum_catalog.entries.add(name="Non_Intrinsic", number=1)

        child_record, child = self._node_record(0x20, 2, "AssignmentStmt")
        child.attributes.add(key="owner").value.node_reference = 0x10

        stream = self._stream(root_record, comment_record, enum_record, child_record)
        actual = decode_stream(stream, self.Record)
        expected = JsonObject(
            [
                (
                    "nodes",
                    [
                        JsonObject(
                            [
                                ("id", "0x10-Program"),
                                ("statement", "0x20-AssignmentStmt"),
                                ("label", "first"),
                                ("label", "second"),
                                ("empty", []),
                                ("items", ["x", ["5"], "18446744073709551615"]),
                                ("integer", "-7"),
                                ("unsigned", "18446744073709551615"),
                                ("enabled", "1"),
                                ("ratio", "1.25"),
                            ]
                        ),
                        JsonObject(
                            [
                                ("id", "0x20-AssignmentStmt"),
                                ("owner", "0x10-Program"),
                            ]
                        ),
                    ],
                ),
                (
                    "comments",
                    [
                        JsonObject(
                            [
                                ("text", "! trailing"),
                                ("stmtId", "0x20-AssignmentStmt"),
                                ("trailing", True),
                            ]
                        )
                    ],
                ),
                (
                    "enums",
                    JsonObject(
                        [("UseStmt::ModuleNature", ["Intrinsic", "Non_Intrinsic"])]
                    ),
                ),
            ]
        )
        self.assertTrue(compare_graphs(expected, actual))

        reparsed = json.loads(_json_text(actual), object_pairs_hook=JsonObject)
        self.assertTrue(compare_graphs(expected, reparsed))
        self.assertEqual(actual.get("nodes")[0].pairs[2:4], [("label", "first"), ("label", "second")])

    def test_rejects_bad_or_truncated_framing(self) -> None:
        malformed = [
            (b"FLASTPB1", "truncated protocol header"),
            (b"NOTASTPB" + struct.pack("<I", 1), "invalid protocol magic"),
            (_header(2), "unsupported protocol version"),
            (_header() + b"\x00", "zero-length protobuf records"),
            (_header() + b"\x81\x00", "not canonical"),
            (_header() + b"\x80", "truncated record length varint"),
            (_header() + b"\x80\x80\x80\x80\x10", "overflows uint32"),
            (_header() + _varint(2) + b"\x08", "truncated protobuf record payload"),
            (_header() + _varint(MAX_RECORD_SIZE + 1), "exceeds 64 MiB"),
            (_header() + _frame(b"\x0f"), "protobuf parsing failed"),
            # Unknown protobuf fields parse, but do not select the record oneof.
            (_header() + _frame(b"\x98\x06\x01"), "no selected record variant"),
        ]
        for data, message in malformed:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                decode_stream(data, self.Record)

    def test_rejects_non_node_first_record(self) -> None:
        record, comment = self._new_record("comment")
        comment.text = "! before the first node"
        comment.stmt_node_id = 1
        with self.assertRaisesRegex(ValueError, "first stream record must be a node"):
            decode_stream(self._stream(record), self.Record)

    def test_rejects_invalid_nodes_and_unresolved_references(self) -> None:
        invalid_nodes = [
            (0, 1, "Program", "zero node ID"),
            (1, 0, "Program", "zero kind ID"),
            (1, 1, "", "empty kind name"),
        ]
        for node_id, kind_id, kind_name, message in invalid_nodes:
            record, _ = self._node_record(node_id, kind_id, kind_name)
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                decode_stream(self._stream(record), self.Record)

        first, node = self._node_record(1, 1, "Program")
        node.attributes.add(key="child").value.node_reference = 2
        with self.assertRaisesRegex(ValueError, "references unknown node ID 2"):
            decode_stream(self._stream(first), self.Record)

        first, _ = self._node_record(1, 1, "Program")
        duplicate, _ = self._node_record(1, 1, "Duplicate")
        with self.assertRaisesRegex(ValueError, "repeats node ID 1"):
            decode_stream(self._stream(first, duplicate), self.Record)

    def test_rejects_unset_attribute_value_and_unresolved_comment(self) -> None:
        first, node = self._node_record(1, 1, "Program")
        node.attributes.add(key="missing-value")
        with self.assertRaisesRegex(ValueError, "has no selected value"):
            decode_stream(self._stream(first), self.Record)

        first, _ = self._node_record(1, 1, "Program")
        comment_record, comment = self._new_record("comment")
        comment.text = "! orphan"
        comment.stmt_node_id = 2
        with self.assertRaisesRegex(ValueError, r"comments\[0\] references unknown node ID 2"):
            decode_stream(self._stream(first, comment_record), self.Record)


if __name__ == "__main__":
    unittest.main()
