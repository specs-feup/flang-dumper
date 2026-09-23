# Flang AST dumper generation plan

## Goal and ownership

Clava runs one pinned generation command. It analyzes the Flang 22 C++ parse-tree declarations, combines them with project-owned serialization metadata, writes a protobuf schema and C++ visitor/producer sources, and invokes `protoc`. The Flang headers define C++ structure; the metadata defines wire semantics. The generator never assigns protobuf numbers from discovery order.

The checked-in metadata owns stable node kinds, field tags, names, access expressions, and exceptions. Generated files carry an input digest and are reproducible. The runtime has one binary output path after the consumer migrates; the current JSON dumper remains available only as a migration oracle until then.

## Work sequence

1. **Inventory and baseline.** Extract every `DUMP_NODE`, `DUMP_NODE_MANUAL`, and `DUMP_ENUM` registration. Record the current JSON graph for fixtures covering wrappers, tuples, variants, lists, optionals, enum values, comments, and source text. Normalize pointer-derived IDs before comparison. The known downstream reader is Metafor's `FortranParser`: `FortranNativeParser` streams plugin stdout into `FortranJsonParser`. Its dynamic attribute keys, wrapper chains, and first-record root selection are part of the migration contract.
2. **Header analysis.** Pin the Flang release and compiler flags. Use Clava to discover declarations in `flang/Parser/parse-tree.h` and supporting headers. Produce a normalized model with fully qualified C++ names, members, member types, enum constants, and source locations. Reject missing, ambiguous, or unsupported declarations; never silently skip them.
3. **Serialization metadata.** Add a reviewed manifest keyed by fully qualified C++ type. It records stable wire numbers, field names, member or tuple access paths, cardinality, variant alternatives, source/comment rules, and custom adapter names. Import existing manual handlers into explicit entries. Keep custom C++ adapters small and separately named.
4. **Generation.** From the model and manifest, emit deterministic `.proto`, C++ producers, visitor registration, and `protoc` outputs. Use a framed stream with version metadata, bounded record lengths, explicit presence and variant arms, and translation-unit-local numeric node IDs. Encode node kind separately. Preserve legacy attribute key names and scalar/list distinctions. Reserve retired field and kind numbers.
5. **Build and consumer.** Wire generation into a clean CMake build with pinned Clava, Flang, and protobuf tools, or check in generated output plus a CI freshness check if tool availability makes that preferable. Migrate Metafor's `FortranNativeParser` stream to a record-at-a-time protobuf reader that feeds the existing `FortranJsonResult`/`FlangData` graph construction path. It must retain raw attributes until postprocessing finishes because references can point forward. For a first migration, map numeric wire IDs to deterministic synthetic strings ending in `-<kind>` so existing `getKind()` and `isIdInteger()` behavior remains valid; remove those text assumptions only in a separately tested reader refactor. Remove JSON runtime output only after that migration passes.
6. **Validation and cutover.** Require complete registration coverage and normalized graph equivalence, including identity, order, source, comments, null versus absent values, and enum meaning. Test truncated/invalid records, deterministic regeneration, multiple files, and upgrade behavior. Measure raw bytes, compressed bytes, runtime, and peak memory on representative Fortran workloads. Remove the text runtime path only after the consumer and these gates pass.

## First implementation slice

The first slice must prove the Clava header-analysis entry point and generator interface with a tiny fixture header, plus a machine-readable inventory of current handlers and a normalized baseline comparison tool. It should cover one ordinary tuple/wrapper and one manual semantic case. A prototype is not the cutover: it must not replace the current visitor until it covers all registrations and the consumer is integrated.

The current slice lives in `generator/`, `scripts/inventory_dump_handlers.py`, and `tests/baseline/`. Run `python3 scripts/inventory_dump_handlers.py -o /tmp/flang-handlers.json` to capture the registration inventory. Run `python3 tests/baseline/compare_graphs.py expected.json actual.json` to compare two dumps while normalizing pointer IDs. The fixture generator and its checks are described in `generator/README.md`.

## Acceptance criteria

- A clean generation run needs no hand edits to generated files and is byte-for-byte reproducible.
- Each registered node and enum is either generated or has a named, tested exception; unknown declarations fail generation.
- Protobuf field and kind numbers are stable across regeneration and additions.
- The decoded graph matches the normalized baseline on the fixture set.
- The real downstream reader consumes the binary stream; no production text fallback remains after cutover.
- Build, corpus, and performance evidence is reported separately, with missing tools or unrun gates stated plainly.
