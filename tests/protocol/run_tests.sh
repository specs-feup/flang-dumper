#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/flang-dumper-protocol-test.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT

PROTOC="${PROTOC:-protoc}"
CXX="${CXX:-g++}"
PROTOBUF_INCLUDE_DIR="${PROTOBUF_INCLUDE_DIR:-/usr/include}"
PROTOBUF_LIB_DIR="${PROTOBUF_LIB_DIR:-/usr/lib}"
PROTOBUF_LIBS="${PROTOBUF_LIBS:--lprotobuf}"

export LD_LIBRARY_PATH="$PROTOBUF_LIB_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

"$PROTOC" --version
"$PROTOC" --proto_path="$script_dir" --cpp_out="$build_dir" \
  "$script_dir/framing_test.proto"

# PROTOBUF_LIBS accepts ordinary linker arguments, for example
# "-lprotobuf -pthread" when the local protobuf build requires both.
read -r -a protobuf_libs <<< "$PROTOBUF_LIBS"
"$CXX" -std=c++17 -Wall -Wextra -Werror -pedantic \
  -I"$repo_root" -I"$PROTOBUF_INCLUDE_DIR" -I"$build_dir" \
  "$repo_root/protocol/framing.cpp" \
  "$build_dir/framing_test.pb.cc" \
  "$script_dir/framing_test.cpp" \
  -L"$PROTOBUF_LIB_DIR" "${protobuf_libs[@]}" \
  -Wl,-rpath,"$PROTOBUF_LIB_DIR" \
  -o "$build_dir/framing_test"

"$build_dir/framing_test"
