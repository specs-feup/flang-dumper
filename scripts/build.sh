#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="${ROOT_DIR}/build"
COPY_PLUGIN=1
CMAKE_ARGS=()

usage() {
  cat <<EOF
Usage: $0 [--no-copy|-n] [--help|-h] [-- <cmake args>]

Builds the Flang AST dumper plugin. By default the resulting
DumpASTPlugin.so is copied to /tmp/metafor_\${USER}/.

Options:
  -n, --no-copy   Do not copy DumpASTPlugin.so to /tmp/metafor_\${USER}.
  -h, --help      Show this help message.

Any arguments after -- are passed to the CMake configure step, e.g.:
  $0 -- -DLLVM_DIR=/opt/llvm/lib/cmake/llvm
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -n|--no-copy)
      COPY_PLUGIN=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      CMAKE_ARGS=("$@")
      break
      ;;
    *)
      CMAKE_ARGS+=("$1")
      ;;
  esac
  shift
done

cd "${ROOT_DIR}"

cmake -B "${BUILD_DIR}" "${CMAKE_ARGS[@]}"
cmake --build "${BUILD_DIR}" --parallel

if [ "${COPY_PLUGIN}" -eq 1 ]; then
  DEST_DIR="/tmp/metafor_${USER}"
  mkdir -p "${DEST_DIR}"
  cp "${BUILD_DIR}/DumpASTPlugin.so" "${DEST_DIR}/DumpASTPlugin.so"
  echo "Copied DumpASTPlugin.so to ${DEST_DIR}/"
fi
