#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash clava_driver/run.sh \
  --analyzer clava|clang|snapshot \
  --header-root <extracted/usr> \
  --include-dir <extracted/usr/lib/llvm-22/include> \
  --output-dir <generated output directory> \
  --protoc <protoc executable> \
  [--clava-entry <Clava-JS/code/index.ts> --query-module <Lara-JS/api/weaver/Query.ts>] \
  [--clang-command <compiler command>] [--inventory <saved model>] [--java]

The production command analyzes the pinned Flang 22 headers, checks the result
against generator/flang22-declarations.json and reviewed manifests, emits the
visitor/kind/enum artifacts and generic protocol schema, and invokes protoc.
Select exactly one analyzer; Clang is an explicit fallback. Snapshot mode
validates an existing model and all pinned source hashes without reparsing.
EOF
}

die() {
  printf 'production driver error: %s\n' "$1" >&2
  exit 2
}

analyzer=
header_root=
include_dir=
output_dir=
protoc_path=
clava_entry=
query_module=
clang_command=
inventory=
python_command=python3
generate_java=false

while (($#)); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --java) generate_java=true; shift; continue ;;
  esac
  if (($# < 2)); then
    usage >&2
    die "missing value after $1"
  fi
  case "$1" in
    --analyzer) analyzer=$2 ;;
    --header-root) header_root=$2 ;;
    --include-dir) include_dir=$2 ;;
    --output-dir) output_dir=$2 ;;
    --protoc) protoc_path=$2 ;;
    --clava-entry) clava_entry=$2 ;;
    --query-module) query_module=$2 ;;
    --clang-command) clang_command=$2 ;;
    --inventory) inventory=$2 ;;
    --python) python_command=$2 ;;
    *) usage >&2; die "unknown argument $1" ;;
  esac
  shift 2
done

for pair in \
  "--analyzer:$analyzer" \
  "--header-root:$header_root" \
  "--include-dir:$include_dir" \
  "--output-dir:$output_dir" \
  "--protoc:$protoc_path"; do
  value=${pair#*:}
  [[ -n "$value" ]] || die "required option ${pair%%:*} was not provided"
done

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
driver_args=("$python_command" "$repo_root/generator/generate_production.py"
  --analyzer "$analyzer"
  --header-root "$header_root"
  --include-dir "$include_dir"
  --output-dir "$output_dir"
  --protoc "$protoc_path")
[[ -n "$clang_command" ]] && driver_args+=(--clang-command "$clang_command")
[[ -n "$inventory" ]] && driver_args+=(--inventory "$inventory")
[[ -n "$clava_entry" ]] && driver_args+=(--clava-entry "$clava_entry")
[[ -n "$query_module" ]] && driver_args+=(--query-module "$query_module")
[[ "$generate_java" == true ]] && driver_args+=(--java)

command -v "$python_command" >/dev/null 2>&1 || die "Python command is not executable: $python_command"
exec "${driver_args[@]}"
