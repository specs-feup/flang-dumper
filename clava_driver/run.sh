#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash clava_driver/run.sh \
  --clava <Clava-JS/code/index.ts> \
  --query-module <Lara-JS/api/weaver/Query.ts> \
  --header <C++ header> \
  --header-root <include and source root> \
  --metadata <reviewed generator metadata.json> \
  --output-dir <generated output directory> \
  --protoc <protoc executable> \
  [--python <python3 executable>]

The driver aspect runs inside Clava's classic CLI process. It imports
generator/analyze.js against that process's AST, invokes generator/generate.py
with the resulting model, then runs protoc. The CLAVA path is the Clava 4
JavaScript entry file; this runner starts it with node.
EOF
}

die() {
  printf 'clava driver error: %s\n' "$1" >&2
  exit 2
}

clava_entry=
query_module=
header=
header_root=
metadata=
output_dir=
protoc_path=
python_command=python3

while (($#)); do
  case "$1" in
    -h|--help) usage; exit 0 ;;
  esac
  if (($# < 2)); then
    usage >&2
    die "missing value after $1"
  fi
  case "$1" in
    --clava) clava_entry=$2 ;;
    --query-module) query_module=$2 ;;
    --header) header=$2 ;;
    --header-root) header_root=$2 ;;
    --metadata) metadata=$2 ;;
    --output-dir) output_dir=$2 ;;
    --protoc) protoc_path=$2 ;;
    --python) python_command=$2 ;;
    *) usage >&2; die "unknown argument $1" ;;
  esac
  shift 2
done

for pair in \
  "--clava:$clava_entry" \
  "--query-module:$query_module" \
  "--header:$header" \
  "--header-root:$header_root" \
  "--metadata:$metadata" \
  "--output-dir:$output_dir" \
  "--protoc:$protoc_path"; do
  value=${pair#*:}
  [[ -n "$value" ]] || die "required option ${pair%%:*} was not provided"
done

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
driver_file="$repo_root/clava_driver/driver.mjs"
clava_entry=$(realpath -e -- "$clava_entry") || die "Clava entry does not exist"
query_module=$(realpath -e -- "$query_module") || die "Query module does not exist"
header=$(realpath -e -- "$header") || die "header does not exist"
header_root=$(realpath -e -- "$header_root") || die "header root does not exist"
metadata=$(realpath -e -- "$metadata") || die "metadata does not exist"
protoc_path=$(realpath -e -- "$protoc_path") || die "protoc does not exist"

[[ -f "$clava_entry" ]] || die "Clava entry is not a file"
[[ -f "$query_module" ]] || die "Query module is not a file"
[[ -f "$header" ]] || die "header is not a file"
[[ -d "$header_root" ]] || die "header root is not a directory"
[[ -f "$metadata" ]] || die "metadata is not a file"
[[ -f "$protoc_path" && -x "$protoc_path" ]] || die "protoc is not an executable file"
case "$header" in
  "$header_root"/*) ;;
  *) die "header must be beneath header root" ;;
esac
command -v "$python_command" >/dev/null 2>&1 || die "Python command is not executable: $python_command"

mkdir -p -- "$output_dir"
output_dir=$(realpath -e -- "$output_dir") || die "cannot resolve output directory"
header_parent=$(dirname "$header")
model_path="$output_dir/declarations.json"

export FLANG_DRIVER_REPO_ROOT="$repo_root"
export FLANG_DRIVER_CLAVA_ENTRY="$clava_entry"
export FLANG_DRIVER_METADATA="$metadata"
export FLANG_DRIVER_OUTPUT_DIR="$output_dir"
export FLANG_DRIVER_PROTOC="$protoc_path"
export FLANG_DRIVER_PYTHON="$python_command"
export FLANG_DRIVER_MODEL="$model_path"
export FLANG_GENERATOR_HEADER="$header"
export FLANG_GENERATOR_HEADER_ROOT="$header_root"
export FLANG_GENERATOR_MODEL_OUT="$model_path"
export FLANG_GENERATOR_QUERY_MODULE="$query_module"

node "$clava_entry" classic "$driver_file" \
  -p "$header_parent" \
  -std c++20 \
  -fs "-I$header_root -I$header_parent" \
  -ncg
