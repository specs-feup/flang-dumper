#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/flang-dumper-ast-reader-test.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT

PROTOC="${PROTOC:-protoc}"
CXX="${CXX:-g++}"
PROTOBUF_INCLUDE_DIR="${PROTOBUF_INCLUDE_DIR:-/usr/include}"
PROTOBUF_LIB_DIR="${PROTOBUF_LIB_DIR:-/usr/lib}"
PROTOBUF_LIBS="${PROTOBUF_LIBS:--lprotobuf}"

export LD_LIBRARY_PATH="$PROTOBUF_LIB_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

mkdir -p "$build_dir/protocol"
"$PROTOC" --version
"$PROTOC" --proto_path="$repo_root/protocol" --cpp_out="$build_dir/protocol" \
  "$repo_root/protocol/ast_stream.proto"

read -r -a protobuf_libs <<< "$PROTOBUF_LIBS"
"$CXX" -std=c++17 -Wall -Wextra -Werror -pedantic \
  -I"$repo_root" -I"$PROTOBUF_INCLUDE_DIR" -I"$build_dir" \
  "$repo_root/protocol/framing.cpp" \
  "$repo_root/protocol/ast_reader.cpp" \
  "$build_dir/protocol/ast_stream.pb.cc" \
  "$script_dir/ast_reader_test.cpp" \
  -L"$PROTOBUF_LIB_DIR" "${protobuf_libs[@]}" \
  -Wl,-rpath,"$PROTOBUF_LIB_DIR" \
  -o "$build_dir/ast_reader_test"

"$build_dir/ast_reader_test"
