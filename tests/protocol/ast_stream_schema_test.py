#!/usr/bin/env python3
"""Compile and inspect ast_stream.proto using only protoc and the stdlib."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROTO = Path(__file__).resolve().parents[2] / "protocol" / "ast_stream.proto"


def _read_varint(data, offset):
    value = 0
    shift = 0
    while offset < len(data) and shift < 70:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
    raise AssertionError("malformed varint in protoc descriptor output")


def _wire_fields(data):
    """Yield (field_number, wire_type, value) from a protobuf byte string."""
    offset = 0
    while offset < len(data):
        tag, offset = _read_varint(data, offset)
        number = tag >> 3
        wire_type = tag & 7
        if number == 0:
            raise AssertionError("invalid field number in protoc descriptor output")
        if wire_type == 0:
            value, offset = _read_varint(data, offset)
        elif wire_type == 1:
            if offset + 8 > len(data):
                raise AssertionError("truncated fixed64 in protoc descriptor output")
            value = data[offset : offset + 8]
            offset += 8
        elif wire_type == 2:
            length, offset = _read_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise AssertionError("truncated bytes in protoc descriptor output")
            value = data[offset:end]
            offset = end
        elif wire_type == 5:
            if offset + 4 > len(data):
                raise AssertionError("truncated fixed32 in protoc descriptor output")
            value = data[offset : offset + 4]
            offset += 4
        else:
            raise AssertionError("unsupported wire type in protoc descriptor output")
        yield number, wire_type, value


def _length_delimited(data, number):
    return [value for field, wire, value in _wire_fields(data)
            if field == number and wire == 2]


def _first_string(data, number):
    values = _length_delimited(data, number)
    if not values:
        raise AssertionError("missing descriptor string field %d" % number)
    return values[0].decode("utf-8")


def _messages(file_descriptor):
    return {
        _first_string(descriptor, 1): descriptor
        for descriptor in _length_delimited(file_descriptor, 4)
    }


def _oneof_names(message_descriptor):
    return [_first_string(oneof, 1)
            for oneof in _length_delimited(message_descriptor, 8)]


def _fields(message_descriptor):
    result = {}
    for descriptor in _length_delimited(message_descriptor, 2):
        values = {number: value for number, wire, value in _wire_fields(descriptor)
                  if wire == 0}
        field = {
            "name": _first_string(descriptor, 1),
            "number": values[3],
            "label": values[4],
            "type": values[5],
        }
        type_names = _length_delimited(descriptor, 6)
        if type_names:
            field["type_name"] = type_names[0].decode("utf-8")
        if 9 in values:
            field["oneof_index"] = values[9]
        result[field["name"]] = field
    return result


class AstStreamSchemaTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("PROTOC"), "set PROTOC to run schema checks")
    def test_compiles_and_has_expected_transport_shape(self):
        protoc = os.environ["PROTOC"]
        if not Path(protoc).is_file() and shutil.which(protoc) is None:
            self.fail("PROTOC does not name an executable: %s" % protoc)

        with tempfile.TemporaryDirectory(prefix="ast-stream-schema-") as temp_dir:
            descriptor_path = Path(temp_dir) / "ast_stream.pb"
            completed = subprocess.run(
                [protoc, "--proto_path=%s" % PROTO.parent,
                 "--descriptor_set_out=%s" % descriptor_path, str(PROTO)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(
                completed.returncode,
                0,
                "protoc failed:\n%s\n%s" % (completed.stdout, completed.stderr),
            )

            descriptor_set = descriptor_path.read_bytes()
            files = _length_delimited(descriptor_set, 1)
            self.assertEqual(len(files), 1, "expected one compiled schema file")
            file_descriptor = files[0]
            self.assertEqual(_first_string(file_descriptor, 2),
                             "flang_dumper.protocol")
            self.assertEqual(_first_string(file_descriptor, 12), "proto3")
            messages = _messages(file_descriptor)

        self.assertEqual(
            set(messages),
            {"StreamRecord", "NodeRecord", "Attribute", "AttributeValue",
             "Value", "ValueList", "NullValue", "CommentRecord", "EnumCatalog",
             "EnumEntry"},
        )
        field_type = {
            "uint64": 4,
            "uint32": 13,
            "double": 1,
            "string": 9,
            "sint64": 18,
            "bool": 8,
            "bytes": 12,
            "message": 11,
        }
        optional = 1
        repeated = 3

        stream_record = _fields(messages["StreamRecord"])
        self.assertEqual(_oneof_names(messages["StreamRecord"]), ["record"])
        self.assertEqual(set(stream_record), {"node", "comment", "enum_catalog"})
        self.assertEqual(
            [(name, stream_record[name]["number"], stream_record[name]["type"],
              stream_record[name].get("oneof_index"))
             for name in ("node", "comment", "enum_catalog")],
            [("node", 1, field_type["message"], 0),
             ("comment", 2, field_type["message"], 0),
             ("enum_catalog", 3, field_type["message"], 0)],
        )

        node_fields = _fields(messages["NodeRecord"])
        self.assertEqual(
            [(name, node_fields[name]["number"], node_fields[name]["type"])
             for name in ("node_id", "kind_id", "kind_name")],
            [("node_id", 1, field_type["uint64"]),
             ("kind_id", 2, field_type["uint32"]),
             ("kind_name", 3, field_type["string"])],
        )
        self.assertEqual(node_fields["attributes"]["number"], 4)
        self.assertEqual(node_fields["attributes"]["label"], repeated)
        self.assertEqual(node_fields["attributes"]["type"], field_type["message"])
        self.assertEqual(node_fields["attributes"]["type_name"],
                         ".flang_dumper.protocol.Attribute")

        attribute_fields = _fields(messages["Attribute"])
        self.assertEqual(attribute_fields["key"]["type"], field_type["string"])
        self.assertEqual(attribute_fields["value"]["type"], field_type["message"])
        self.assertEqual(attribute_fields["value"]["type_name"],
                         ".flang_dumper.protocol.AttributeValue")

        expected_variants = {
            "string_value": (1, field_type["string"]),
            "integer_value": (2, field_type["sint64"]),
            "bool_value": (3, field_type["bool"]),
            "node_reference": (4, field_type["uint64"]),
            "list_value": (5, field_type["message"]),
            "null_value": (6, field_type["message"]),
            "double_value": (7, field_type["double"]),
            "bytes_value": (8, field_type["bytes"]),
            "uint64_value": (9, field_type["uint64"]),
        }
        for message_name in ("AttributeValue", "Value"):
            descriptor = messages[message_name]
            self.assertEqual(_oneof_names(descriptor), ["value"])
            variants = _fields(descriptor)
            self.assertEqual(set(variants), set(expected_variants))
            for name, (number, kind) in expected_variants.items():
                self.assertEqual(variants[name]["number"], number)
                self.assertEqual(variants[name]["type"], kind)
                self.assertEqual(variants[name].get("oneof_index"), 0)
            self.assertEqual(variants["list_value"]["type_name"],
                             ".flang_dumper.protocol.ValueList")
            self.assertEqual(variants["null_value"]["type_name"],
                             ".flang_dumper.protocol.NullValue")

        list_items = _fields(messages["ValueList"])["items"]
        self.assertEqual(list_items["label"], repeated)
        self.assertEqual(list_items["type"], field_type["message"])
        self.assertEqual(list_items["type_name"], ".flang_dumper.protocol.Value")
        self.assertEqual(_fields(messages["NullValue"]), {})

        comment_fields = _fields(messages["CommentRecord"])
        self.assertEqual(
            [(name, comment_fields[name]["number"], comment_fields[name]["type"])
             for name in ("text", "stmt_node_id", "trailing")],
            [("text", 1, field_type["string"]),
             ("stmt_node_id", 2, field_type["uint64"]),
             ("trailing", 3, field_type["bool"])],
        )

        catalog_fields = _fields(messages["EnumCatalog"])
        self.assertEqual(catalog_fields["enum_type_name"]["type"], field_type["string"])
        self.assertEqual(catalog_fields["entries"]["label"], repeated)
        entry_fields = _fields(messages["EnumEntry"])
        self.assertEqual(entry_fields["name"]["type"], field_type["string"])
        self.assertEqual(entry_fields["number"]["type"], field_type["sint64"])


if __name__ == "__main__":
    unittest.main()
