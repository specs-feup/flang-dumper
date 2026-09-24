#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
FLANG_INCLUDE_DIR="${FLANG_INCLUDE_DIR:-/tmp/flang22-libflang.woWtRQ/extracted/usr/lib/llvm-22/include}"
CXX="${CXX:-clang++-21}"
PROTOC="${PROTOC:-protoc}"
PROTOBUF_INCLUDE_DIR="${PROTOBUF_INCLUDE_DIR:-/usr/include}"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/flang-dumper-binary-fields-compile.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT

"$PROTOC" --proto_path="$repo_root" --cpp_out="$build_dir" \
  "$repo_root/protocol/ast_stream.proto"

"$CXX" -std=c++17 -fsyntax-only \
  -I"$repo_root" \
  -I"$build_dir" \
  -I"$FLANG_INCLUDE_DIR" \
  -I"$PROTOBUF_INCLUDE_DIR" \
  "$script_dir/binary_fields_compile_test.cpp"
