#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/flang-dumper-graph-ids-test.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT

CXX="${CXX:-g++}"
"$CXX" -std=c++17 -Wall -Wextra -Werror -pedantic \
  -I"$repo_root" \
  "$repo_root/protocol/graph_ids.cpp" \
  "$script_dir/graph_ids_test.cpp" \
  -o "$build_dir/graph_ids_test"

"$build_dir/graph_ids_test"
