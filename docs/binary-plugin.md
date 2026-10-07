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

## Live corpus comparison

Compare both native actions on a directory of Fortran sources:

```sh
python3 tests/baseline/compare_native_corpus.py \
  --flang "$(command -v flang-new)" \
  --json-plugin build/DumpASTPlugin.so \
  --binary-plugin build/DumpASTProtobufPlugin.so \
  --protoc "$(command -v protoc)" \
  /path/to/FortranParser/resources-test
```

The checker discovers `.f90` files recursively and excludes `.expected.f90`
outputs. It compares live decoded graphs with pointer IDs normalized, preserving
duplicate attributes, node order, references, comments, and enum catalogs.
Its summary separates JSON baseline failures from protobuf failures and graph
mismatches. A successful exit requires at least one valid baseline and no
protobuf failures or mismatches. Baseline failures remain excluded from parity
coverage and must be reviewed separately.

## OpenMP graph corrections

`OmpDirectiveSpecification::Flags` now carries its member names as a scalar
string under Flang's effective field key. Previously the JSON producer emitted
a reference to a node that did not exist, and the protobuf producer rejected
that reference. Empty sets produce an empty string.

The empty `OmpClause::SeqCst` marker now has an emitted node with appended kind
ID 865. Existing kind IDs remain stable. The deprecated-flush regression checks
a nonempty `DeprecatedSyntax` Flags value and that every SeqCst reference resolves.

Validation on the Metafor corpus matched all 52 valid JSON baselines; one
REAL(16) input failed in Flang for the selected target. Metafor's separate
experimental reader also passed 48 native AST and generated-Fortran comparisons.
These checks do not establish production cutover, full declaration coverage,
or performance and memory improvements.
