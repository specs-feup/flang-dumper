#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
FLANG_INCLUDE_DIR="${FLANG_INCLUDE_DIR:-/tmp/flang22-libflang.woWtRQ/extracted/usr/lib/llvm-22/include}"
LLVM_LIB_DIR="${LLVM_LIB_DIR:-/tmp/flang22-libflang.woWtRQ/extracted/usr/lib/llvm-22/lib}"
CXX="${CXX:-clang++-21}"
PROTOC="${PROTOC:-protoc}"
PROTOBUF_INCLUDE_DIR="${PROTOBUF_INCLUDE_DIR:-/usr/include}"
PROTOBUF_LIB_DIR="${PROTOBUF_LIB_DIR:-/usr/lib/x86_64-linux-gnu}"
PROTOBUF_LIBS="${PROTOBUF_LIBS:--l:libprotobuf.so.32}"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/flang-dumper-binary-fields-enumset.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT
export LD_LIBRARY_PATH="$LLVM_LIB_DIR:$PROTOBUF_LIB_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

mkdir -p "$build_dir/protocol"
"$PROTOC" --proto_path="$repo_root/protocol" --cpp_out="$build_dir/protocol" \
  "$repo_root/protocol/ast_stream.proto"

read -r -a protobuf_libs <<< "$PROTOBUF_LIBS"
"$CXX" -std=c++17 -Wall -Wextra -Werror -pedantic \
  -I"$repo_root" -I"$build_dir" \
  -isystem "$FLANG_INCLUDE_DIR" -isystem "$PROTOBUF_INCLUDE_DIR" \
  "$repo_root/protocol/framing.cpp" \
  "$repo_root/protocol/graph_ids.cpp" \
  "$repo_root/protocol/ast_writer.cpp" \
  "$repo_root/protocol/binary_context.cpp" \
  "$build_dir/protocol/ast_stream.pb.cc" \
  "$script_dir/binary_fields_enumset_test.cpp" \
  -L"$LLVM_LIB_DIR" -lLLVM -L"$PROTOBUF_LIB_DIR" "${protobuf_libs[@]}" \
  -Wl,-rpath,"$LLVM_LIB_DIR" -Wl,-rpath,"$PROTOBUF_LIB_DIR" \
  -o "$build_dir/binary_fields_enumset_test"

"$build_dir/binary_fields_enumset_test"
