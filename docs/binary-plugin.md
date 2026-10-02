# Experimental protobuf plugin

The protobuf dumper is an experimental second Flang plugin. The existing JSON
plugin remains the default. This target does not include a consumer or claim a
production cutover.

## Build

Enable the target with:

```sh
cmake -S . -B build -DFLANG_DUMPER_BUILD_PROTOBUF_PLUGIN=ON
cmake --build build --target DumpASTProtobufPlugin
```

The build requires the repository's Flang/LLVM 22 toolchain and a protobuf
development package with `protoc`. CMake's `FindProtobuf` must provide the
`protobuf::protoc` and `protobuf::libprotobuf` imported targets. CMake runs
`protoc` on `protocol/ast_stream.proto`, using the repository root as the proto
path, and writes `protocol/ast_stream.pb.cc` and `.h` under the build
directory. The option defaults to `OFF`, so a normal build does not require
protobuf.

## Run

Pass a Fortran source file to Flang's frontend and redirect stdout to a binary
file:

```sh
flang-new -fc1 -fopenmp \
  -load build/DumpASTProtobufPlugin.so \
  -plugin dump-ast-protobuf input.f90 > output.astpb
```

Use the plugin module's platform-specific filename if it does not end in
`.so`. The output is a framed protobuf stream. Open files that consume it in
binary mode.

## Native fixture check

Run the focused native fixture check with:

```sh
python3 tests/baseline/check_binary_native_fixtures.py \
  --flang "$(command -v flang-new)" \
  --plugin build/DumpASTProtobufPlugin.so \
  --protoc "$(command -v protoc)"
```

Passing native fixtures covers only the selected inputs. A consumer still
needs to read this stream and preserve the existing AST graph contract.
Broader Flang declaration coverage, malformed
stream handling, and deterministic generation also need review. Before any
cutover, compare representative workloads and report output size, runtime,
and peak memory. JSON remains the migration oracle until those gates and the
consumer integration pass.
