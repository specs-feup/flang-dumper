# Binary protobuf framing

This library frames protobuf `MessageLite` values on binary C++ streams. It is
independent of any generated AST schema, so callers can pass a generated
per-node `StreamRecord` message when that schema is available. There is no
text or JSON fallback.

The stream starts with exactly 12 bytes:

| Offset | Size | Meaning |
| --- | ---: | --- |
| 0 | 8 | ASCII bytes `FLASTPB1` |
| 8 | 4 | Protocol version as an unsigned little-endian integer; current version is `1` |

After the header, each record consists of an unsigned protobuf-style varint32
byte length followed by exactly that many serialized protobuf bytes. Lengths
must use the shortest varint encoding and must be nonzero. The largest
representable record is `UINT32_MAX` bytes; readers and writers also enforce a
caller-supplied maximum, which defaults to 64 MiB. The reader checks the length
against that maximum before allocating payload storage.

Call `ReadHeader` once before reading records. `ReadRecord` returns `false`
only when the stream reaches clean EOF between records. EOF inside a varint or
payload is an error, as are invalid protobuf bytes, a zero length, a length
above the configured maximum, an incorrect magic value, or an unsupported
version. Writers finish protobuf serialization before writing a record prefix,
so a serialization failure does not leave a partial record in the stream.

The caller must open file streams in binary mode. For example:

```cpp
std::ofstream output(path, std::ios::binary);
flang_dumper::protocol::WriteHeader(output);
flang_dumper::protocol::WriteRecord(output, stream_record);
```

The standalone test runner compiles a tiny test-only schema with `protoc` and
links the framing library against protobuf. Set `PROTOC`, `PROTOBUF_INCLUDE_DIR`,
and `PROTOBUF_LIB_DIR` to use a local protobuf installation.
