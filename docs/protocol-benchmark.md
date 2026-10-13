# Native AST protocol benchmark

`scripts/benchmark_native_protocol.py` measures the native Flang JSON and framed-protobuf producers with the same Flang executable, fixture sources, and host environment. It runs JSON-to-protobuf graph parity over the complete `.f90` fixture corpus before collecting measurements. A JSON baseline compiler failure is listed separately and does not count as a protobuf mismatch; a protobuf failure or graph mismatch blocks all timing runs.

The timed producer process is one invocation of Flang with one plugin. GNU `/usr/bin/time` records elapsed child time (`%e`) and that process's peak resident set (`%M`, KiB). The harness also records the parent-observed `perf_counter` duration for the timed invocation. Each stdout is captured, its raw byte length is recorded, and its gzip byte length is computed after the process exits with compression level 9 and `mtime=0`.

The consumer stage is explicitly named `python_test_decoder`. It runs `tests/baseline/decode_ast_stream.py`'s graph decoder in a separate Python process for each protobuf output. Generated Python protobuf bindings are prepared before timing. This stage includes Python startup, imports, reading and decoding the stream, and writing the decoded graph to stdout. It is a test adapter measurement; it is not a measurement of Metafor's Java reader or Java end-to-end memory.

## Reproduce the recorded run

From the Flang dumper checkout, with the exact module artifacts, Flang executable, protoc, and Metafor fixture checkout used for the report:

```bash
export LD_LIBRARY_PATH=/tmp/flang22-libflang.woWtRQ/extracted/usr/lib/x86_64-linux-gnu:/tmp/flang22-libflang.woWtRQ/extracted/usr/lib/llvm-22/lib:/tmp/flang-protoc-probe/root/usr/lib/x86_64-linux-gnu

python3 scripts/benchmark_native_protocol.py \
  --flang /tmp/flang22-libflang.woWtRQ/extracted/usr/lib/llvm-22/bin/flang-22 \
  --json-plugin /tmp/flang22-libflang.woWtRQ/seqcst-fix/DumpASTPlugin.seqcst.so \
  --protobuf-plugin /tmp/flang22-libflang.woWtRQ/seqcst-fix/DumpASTProtobufPlugin.seqcst.so \
  --protoc /tmp/flang-protoc-probe/root/usr/bin/protoc \
  --fixture-root /home/lmsousa/.t3/worktrees/metafor/flang-protobuf-reader/FortranParser/resources-test \
  --warmups 1 \
  --repeats 5 \
  --synthetic-statements 512 \
  --output docs/protocol-benchmark-report.json
```

The default measured fixtures are `fortran/parser/hello.f90` and `fortran/parser/polybench/3mm.f90`. The third workload is generated deterministically: a small Fortran program with 512 integer assignment statements. Its report label starts with `synthetic/assignment-chain-512`; its source hash and generation count are recorded. It exercises a repeatable statement volume but does not establish coverage of all declarations or AST node kinds.

Warmup and measured iterations are recorded individually. Median rows in the JSON artifact exclude warmups and retain the observed repeat count. The report includes the exact Flang, plugin, protoc, schema, fixture, harness, and decoder hashes; tool versions; producer and fixture checkout HEAD/tree provenance; parity outcomes; full sample records; and medians. When matching object files sit beside the plugins, their hashes and ELF compiler markers are also recorded. Checkout provenance identifies the source snapshot associated with a run, while the plugin hashes identify the exact binaries; the checkout metadata alone does not prove how a binary was built.

Use `--warmups`, `--repeats`, `--small-source`, `--large-source`, and `--synthetic-statements` to change the workload. Set synthetic statements to `0` to omit that workload. Source paths are relative to `--fixture-root` unless absolute. Set `--output` to write a separate report.

## Reading results

Compare raw and gzip sizes as serialization sizes, producer wall time and peak RSS as per-process producer costs, and the Python decoder rows as a separate adapter cost. No fixed pass threshold is encoded. Results describe these fixtures, generated workload, binaries, toolchain, and machine only; they do not by themselves establish migration readiness, full declaration coverage, or whole-application memory behavior.

The checked-in report artifact is [protocol-benchmark-report.json](protocol-benchmark-report.json). Re-run the command above to refresh it for a new build or toolchain; compare reports only after checking that both plugin hashes, source provenance, and tool versions are the intended pair.
