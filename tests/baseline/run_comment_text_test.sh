#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
build_dir="$(mktemp -d "${TMPDIR:-/tmp}/flang-dumper-comment-test.XXXXXX")"
trap 'rm -rf "$build_dir"' EXIT

CXX="${CXX:-c++}"
FLANG_INCLUDE_DIR="${FLANG_INCLUDE_DIR:-/tmp/flang22-libflang.woWtRQ/extracted/usr/lib/llvm-22/include}"

if [[ ! -d "$FLANG_INCLUDE_DIR/flang/Parser" ]]; then
  echo "Flang headers not found under $FLANG_INCLUDE_DIR; set FLANG_INCLUDE_DIR" >&2
  exit 2
fi

"$CXX" -std=c++17 -Wall -Wextra -Werror -pedantic \
  -ffunction-sections -fdata-sections \
  -I"$repo_root/src" -I"$FLANG_INCLUDE_DIR" \
  "$repo_root/src/comments.cpp" \
  "$script_dir/comment_text_test.cpp" \
  -Wl,--gc-sections \
  -o "$build_dir/comment_text_test"

"$build_dir/comment_text_test"
