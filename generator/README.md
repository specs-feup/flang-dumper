# Clava declaration generator probe

This slice checks that Clava can inventory declarations in a project-owned C++
header and that an explicit manifest can produce stable protobuf and C++ files.
It does not cover Flang declarations or define the production dumper protocol.

The default fixture includes a tuple-shaped record whose source names map to
`real` and `imaginary`, a presence/value wrapper, and an expression enum whose
source values are explicitly remapped by metadata. The analyzer records each
declaration and member's qualified name/type and source location. Unknown
declarations, members, member types, enum values, and duplicate wire numbers
fail generation.

Run from this checkout with the Clava 4.0 workspace used for the prototype:

```sh
python3 generator/generate.py \
  --header generator/fixtures/parse_tree_fixture.hpp \
  --header-root generator \
  --metadata generator/metadata.json \
  --output-dir /tmp/flang-generator-output \
  --clava-command 'node /path/to/clava/Clava-JS/code/index.ts classic' \
  --query-module /path/to/lara-framework/Lara-JS/api/weaver/Query.ts
```

`--header-root` controls normalized source paths and the root include search
path. The queried header must be beneath it. `--clava-command` is a command
prefix; the script appends the analyzer and Clava classic CLI arguments.
`--query-module` points to Clava's Lara `Query.ts` joinpoint API module.

The output directory contains canonical `declarations.json`,
`flang_ast.proto`, and `producer.fragment.cpp`. Each generated file carries a
digest of the inventory and metadata. The fragment assumes `protoc` has
generated `flang_ast.pb.h` from the probe schema. It demonstrates scalar,
optional scalar, nested message, and manually mapped enum handling; it has no
stream framing, node identity, visitor registry, or Flang coverage.

The Python generator can be checked without Clava by passing a saved inventory
with `--model path/to/declarations.json`; it rejects an inventory whose header
digest no longer matches the header on disk. The standard-library regression
checks are run with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/generator -v
```
