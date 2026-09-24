#!/usr/bin/env python3
"""Decode the binary AST stream into the legacy JSON graph shape for tests.

This is a test comparison adapter, not the production Metafor reader.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from compare_graphs import JsonObject


MAGIC = b"FLASTPB1"
PROTOCOL_VERSION = 1
HEADER_SIZE = 12
MAX_RECORD_SIZE = 64 * 1024 * 1024
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROTO_FILE = REPOSITORY_ROOT / "protocol" / "ast_stream.proto"


def _read_varint32(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for index in range(5):
        if offset >= len(data):
            raise ValueError("truncated record length varint")
        byte = data[offset]
        offset += 1

        if index == 4 and byte & 0xF0:
            raise ValueError("record length varint overflows uint32")

        value |= (byte & 0x7F) << (7 * index)
        if byte & 0x80 == 0:
            encoded_size = 1
            remaining = value
            while remaining >= 0x80:
                remaining >>= 7
                encoded_size += 1
            if encoded_size != index + 1:
                raise ValueError("record length varint is not canonical")
            return value, offset

    raise ValueError("record length varint is too long")


def _records(data: bytes, record_class: type) -> list[Any]:
    if len(data) < HEADER_SIZE:
        raise ValueError("truncated protocol header")
    if data[:8] != MAGIC:
        raise ValueError("invalid protocol magic")

    version = int.from_bytes(data[8:12], "little", signed=False)
    if version != PROTOCOL_VERSION:
        raise ValueError(f"unsupported protocol version: {version}")

    records = []
    offset = HEADER_SIZE
    while offset < len(data):
        length, offset = _read_varint32(data, offset)
        if length == 0:
            raise ValueError("zero-length protobuf records are not allowed")
        if length > MAX_RECORD_SIZE:
            raise ValueError("protobuf record exceeds 64 MiB maximum")
        end = offset + length
        if end > len(data):
            raise ValueError("truncated protobuf record payload")

        record = record_class()
        try:
            record.ParseFromString(data[offset:end])
        except Exception as error:
            raise ValueError("protobuf parsing failed") from error
        offset = end

        try:
            record_kind = record.WhichOneof("record")
        except (AttributeError, ValueError) as error:
            raise ValueError("record class has no 'record' oneof") from error
        if record_kind is None:
            raise ValueError("stream record has no selected record variant")
        records.append(record)

    if not records or records[0].WhichOneof("record") != "node":
        raise ValueError("first stream record must be a node")
    return records


def _selected_value(message: Any, where: str) -> tuple[str, Any]:
    try:
        value_kind = message.WhichOneof("value")
    except (AttributeError, ValueError) as error:
        raise ValueError(f"{where} has no 'value' oneof") from error
    if value_kind is None:
        raise ValueError(f"{where} has no selected value")
    return value_kind, getattr(message, value_kind)


def _legacy_scalar(kind: str, value: Any, where: str) -> Any:
    if kind == "string_value":
        return value
    if kind == "integer_value":
        return str(value)
    if kind == "uint64_value":
        return str(value)
    if kind == "bool_value":
        # The legacy C++ dumper writes bool attributes as 0 or 1 inside strings.
        return "1" if value else "0"
    if kind == "double_value":
        return str(value)
    if kind == "null_value":
        return None
    if kind == "bytes_value":
        raise ValueError(f"{where} uses bytes, which has no legacy JSON mapping")
    raise ValueError(f"{where} has unsupported value kind {kind!r}")


def _convert_value(message: Any, node_ids: dict[int, str], where: str) -> Any:
    kind, value = _selected_value(message, where)
    if kind == "node_reference":
        try:
            return node_ids[value]
        except KeyError as error:
            raise ValueError(f"{where} references unknown node ID {value}") from error
    if kind == "list_value":
        return [
            _convert_value(item, node_ids, f"{where}[{index}]")
            for index, item in enumerate(value.items)
        ]
    return _legacy_scalar(kind, value, where)


def decode_stream(data: bytes, RecordClass: type) -> JsonObject:
    """Decode framed StreamRecord bytes into a duplicate-key-preserving graph."""
    records = _records(data, RecordClass)
    nodes = []
    comments = []
    enums = []
    node_records = []
    node_ids: dict[int, str] = {}

    for record_index, record in enumerate(records):
        record_kind = record.WhichOneof("record")
        if record_kind == "node":
            node = record.node
            if node.node_id == 0:
                raise ValueError(f"nodes record {record_index} has zero node ID")
            if node.node_id in node_ids:
                raise ValueError(f"nodes record {record_index} repeats node ID {node.node_id}")
            if node.kind_id == 0:
                raise ValueError(f"nodes record {record_index} has zero kind ID")
            if not node.kind_name:
                raise ValueError(f"nodes record {record_index} has empty kind name")
            node_ids[node.node_id] = f"0x{node.node_id:x}-{node.kind_name}"
            node_records.append(node)
        elif record_kind == "comment":
            comments.append(record.comment)
        elif record_kind == "enum_catalog":
            enums.append(record.enum_catalog)

    for index, node in enumerate(node_records):
        pairs = [("id", node_ids[node.node_id])]
        for attribute_index, attribute in enumerate(node.attributes):
            pairs.append(
                (
                    attribute.key,
                    _convert_value(
                        attribute.value,
                        node_ids,
                        f"nodes[{index}].attributes[{attribute_index}] ({attribute.key!r})",
                    ),
                )
            )
        nodes.append(JsonObject(pairs))

    for index, comment in enumerate(comments):
        if comment.stmt_node_id not in node_ids:
            raise ValueError(
                f"comments[{index}] references unknown node ID {comment.stmt_node_id}"
            )

    comment_graph = [
        JsonObject(
            [
                ("text", comment.text),
                ("stmtId", node_ids[comment.stmt_node_id]),
                ("trailing", comment.trailing),
            ]
        )
        for comment in comments
    ]
    enum_graph = JsonObject(
        [
            (catalog.enum_type_name, [entry.name for entry in catalog.entries])
            for catalog in enums
        ]
    )
    return JsonObject(
        [("nodes", nodes), ("comments", comment_graph), ("enums", enum_graph)]
    )


def _load_record_class(protoc: str) -> type:
    with tempfile.TemporaryDirectory(prefix="flang-ast-stream-py-") as temporary:
        output_dir = Path(temporary)
        command = [
            protoc,
            f"--proto_path={PROTO_FILE.parent}",
            f"--python_out={output_dir}",
            str(PROTO_FILE),
        ]
        try:
            result = subprocess.run(command, text=True, capture_output=True, check=False)
        except OSError as error:
            raise ValueError(f"could not run protoc at {protoc!r}: {error}") from error
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip()
            raise ValueError(f"protoc failed with status {result.returncode}: {details}")

        generated_file = output_dir / "ast_stream_pb2.py"
        spec = importlib.util.spec_from_file_location("_flang_ast_stream_pb2", generated_file)
        if spec is None or spec.loader is None:
            raise ValueError(f"could not load generated protobuf module {generated_file}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.StreamRecord


def _json_text(value: Any) -> str:
    if isinstance(value, JsonObject):
        return "{" + ",".join(
            f"{json.dumps(key, ensure_ascii=False)}:{_json_text(child)}"
            for key, child in value.pairs
        ) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_json_text(child) for child in value) + "]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protoc", help="protoc executable (defaults to PROTOC or PATH)")
    parser.add_argument("binary_file", type=Path)
    args = parser.parse_args(argv)

    protoc = args.protoc or os.environ.get("PROTOC") or shutil.which("protoc")
    if not protoc:
        parser.error("provide --protoc or set PROTOC to the protoc executable")

    try:
        stream = args.binary_file.read_bytes()
        decoded = decode_stream(stream, _load_record_class(protoc))
        sys.stdout.write(_json_text(decoded) + "\n")
    except (OSError, ValueError, TypeError) as error:
        print(f"AST stream decode error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
