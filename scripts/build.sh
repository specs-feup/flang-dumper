#!/bin/sh

ROOT_DIR="$(dirname "$0")/.."

cd "$ROOT_DIR" || exit 1
cmake -B build
cd "$ROOT_DIR/build" || exit 1
make -j 4
mkdir -p "/tmp/metafor_$USER"
cp ./DumpASTPlugin.so "/tmp/metafor_$USER/DumpASTPlugin.so"