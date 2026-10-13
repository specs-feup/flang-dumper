#!/usr/bin/env python3
"""Benchmark Flang JSON and framed-protobuf AST producers on a parity-gated corpus.

The protobuf consumer stage is the repository's Python test decoder. It is
measured as its own process and is not a measurement of Metafor's Java reader.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = REPOSITORY_ROOT / "tests" / "baseline"
PROTO_FILE = REPOSITORY_ROOT / "protocol" / "ast_stream.proto"
sys.path.insert(0, str(BASELINE_DIR))

from compare_graphs import compare_graphs  # noqa: E402
from compare_native_corpus import _command, _discover_sources, _load_json_graph, _run  # noqa: E402
from decode_ast_stream import _json_text, decode_stream  # noqa: E402


GZIP_MTIME = 0
GZIP_LEVEL = 9
DECODER_CODE = r"""
import sys
from pathlib import Path
from ast_stream_pb2 import StreamRecord
from decode_ast_stream import _json_text, decode_stream

graph = decode_stream(Path(sys.argv[1]).read_bytes(), StreamRecord)
sys.stdout.write(_json_text(graph) + "\n")
"""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _gzip_size(data: bytes, *, compresslevel: int = GZIP_LEVEL) -> int:
    return len(gzip.compress(data, compresslevel=compresslevel, mtime=GZIP_MTIME))


def _text(data: bytes, limit: int = 1200) -> str:
    rendered = data.decode("utf-8", errors="replace").strip()
    if len(rendered) > limit:
        return rendered[:limit] + "..."
    return rendered


def _run_timed(
    command: list[str],
    *,
    time_executable: str,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run one command under GNU time; retain subprocess and wrapper durations."""
    with tempfile.TemporaryDirectory(prefix="native-protocol-time-") as temporary:
        time_file = Path(temporary) / "time.txt"
        timed_command = [
            time_executable,
            "-f",
            "%e\t%M\t%x",
            "-o",
            str(time_file),
            "--",
            *command,
        ]
        start = time.perf_counter()
        try:
            completed = subprocess.run(
                timed_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                env=env,
            )
        except OSError as error:
            return {
                "command": command,
                "returncode": None,
                "launcher_error": str(error),
                "wall_seconds": time.perf_counter() - start,
                "stderr": "",
                "raw_stdout_bytes": 0,
                "gzip_stdout_bytes": _gzip_size(b""),
                "_stdout": b"",
            }
        wall_seconds = time.perf_counter() - start
        timing: dict[str, Any] = {}
        if time_file.exists():
            timing_lines = time_file.read_text(encoding="utf-8").splitlines()
            parts = next(
                (line.split("\t") for line in reversed(timing_lines) if "\t" in line),
                [],
            )
            if len(parts) == 3:
                try:
                    timing = {
                        "gnu_time_elapsed_seconds": float(parts[0]),
                        "peak_rss_kib": int(parts[1]),
                        "timed_command_exit_code": int(parts[2]),
                    }
                except ValueError:
                    timing = {"timing_parse_error": "GNU time output was not numeric"}

        result: dict[str, Any] = {
            "command": command,
            "returncode": completed.returncode,
            "wall_seconds": wall_seconds,
            "raw_stdout_bytes": len(completed.stdout),
            "gzip_stdout_bytes": _gzip_size(completed.stdout),
            "stderr": _text(completed.stderr),
            "_stdout": completed.stdout,
        }
        result.update(timing)
        return result


def _prepare_decoder(protoc: Path, output_dir: Path, env: dict[str, str]) -> type:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(protoc),
        f"--proto_path={PROTO_FILE.parent}",
        f"--python_out={output_dir}",
        str(PROTO_FILE),
    ]
    result = subprocess.run(command, capture_output=True, check=False, env=env)
    if result.returncode != 0:
        details = _text(result.stderr) or _text(result.stdout)
        raise RuntimeError(f"protoc failed with status {result.returncode}: {details}")
    generated_file = output_dir / "ast_stream_pb2.py"
    spec = importlib.util.spec_from_file_location("_native_benchmark_ast_stream_pb2", generated_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load generated protobuf module {generated_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.StreamRecord


def _source_description(source: Path, fixture_root: Path) -> dict[str, str | int]:
    try:
        label = source.relative_to(fixture_root).as_posix()
    except ValueError:
        label = source.name
    return {
        "label": label,
        "path": str(source),
        "sha256": _sha256_file(source),
        "source_bytes": source.stat().st_size,
    }


def _synthetic_source(statement_count: int) -> bytes:
    lines = [
        "program synthetic_protocol_benchmark",
        "  implicit none",
        "  integer :: value",
        "  value = 0",
    ]
    lines.extend(f"  value = value + {index % 97 + 1}" for index in range(statement_count))
    lines.append("end program synthetic_protocol_benchmark")
    return ("\n".join(lines) + "\n").encode("ascii")


def _git_provenance(root: Path) -> dict[str, Any]:
    def git(*arguments: str) -> str | None:
        try:
            completed = subprocess.run(
                ["git", "-C", str(root), *arguments],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout.strip()

    tracked = git("ls-files", "-z")
    tree_digest = hashlib.sha256()
    file_count = 0
    if tracked is not None:
        for relative in tracked.split("\0"):
            if not relative:
                continue
            path = root / relative
            if not path.is_file():
                continue
            file_count += 1
            digest = _sha256_file(path)
            tree_digest.update(relative.encode("utf-8", errors="surrogateescape"))
            tree_digest.update(b"\0")
            tree_digest.update(digest.encode("ascii"))
            tree_digest.update(b"\n")
    dirty = git("status", "--porcelain=v1", "--untracked-files=no")
    return {
        "path": str(root),
        "head": git("rev-parse", "HEAD"),
        "git_tree": git("rev-parse", "HEAD^{tree}"),
        "tracked_worktree_dirty": None if dirty is None else bool(dirty),
        "tracked_file_count_hashed": file_count,
        "tracked_worktree_content_sha256": tree_digest.hexdigest() if tracked is not None else None,
    }


def _version(command: list[str], env: dict[str, str]) -> dict[str, Any]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
    except OSError as error:
        return {"command": command, "error": str(error)}
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _elf_compiler_markers(path: Path) -> dict[str, Any]:
    readelf = shutil.which("readelf")
    if not readelf:
        return {"error": "readelf is unavailable"}
    try:
        result = subprocess.run(
            [readelf, "-p", ".comment", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        return {"error": str(error)}
    if result.returncode != 0:
        return {"error": result.stderr.strip() or f"readelf exited {result.returncode}"}
    markers = []
    for line in result.stdout.splitlines():
        marker = line.partition("]")[2].strip()
        if marker and marker not in markers:
            markers.append(marker)
    return {"markers": markers}


def _preflight_source(
    source: Path,
    *,
    fixture_root: Path,
    flang: Path,
    json_plugin: Path,
    protobuf_plugin: Path,
    record_class: type,
) -> dict[str, Any]:
    description = _source_description(source, fixture_root)
    label = description["label"]
    json_result = _run(_command(flang, json_plugin, "dump-ast", source))
    if isinstance(json_result, OSError):
        return {**description, "status": "baseline_failure", "detail": f"could not run JSON producer: {json_result}"}
    if json_result.returncode != 0:
        return {
            **description,
            "status": "baseline_failure",
            "detail": f"JSON producer exited {json_result.returncode}: {_text(json_result.stderr)}",
        }
    try:
        baseline = _load_json_graph(json_result.stdout, str(label))
    except ValueError as error:
        return {**description, "status": "baseline_failure", "detail": str(error)}

    binary_result = _run(_command(flang, protobuf_plugin, "dump-ast-protobuf", source))
    if isinstance(binary_result, OSError):
        return {**description, "status": "protobuf_failure", "detail": f"could not run protobuf producer: {binary_result}"}
    if binary_result.returncode != 0:
        return {
            **description,
            "status": "protobuf_failure",
            "detail": f"protobuf producer exited {binary_result.returncode}: {_text(binary_result.stderr)}",
        }
    try:
        binary_graph = decode_stream(binary_result.stdout, record_class)
        equal = compare_graphs(baseline, binary_graph)
    except Exception as error:  # parity gate should report malformed streams as native failures
        return {**description, "status": "protobuf_failure", "detail": f"protobuf decode failed: {error}"}
    if not equal:
        return {**description, "status": "mismatch", "detail": "decoded protobuf graph differs from JSON graph"}
    return {**description, "status": "matched"}


def _summary(samples: list[dict[str, Any]], field: str) -> int | float | None:
    values = [sample[field] for sample in samples if isinstance(sample.get(field), (int, float))]
    return statistics.median(values) if values else None


def _summarize_measurements(records: list[dict[str, Any]], repeats: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        if not record.get("warmup"):
            grouped.setdefault((record["workload"], record["stage"]), []).append(record)
    summary = []
    fields = (
        "wall_seconds",
        "gnu_time_elapsed_seconds",
        "peak_rss_kib",
        "raw_stdout_bytes",
        "gzip_stdout_bytes",
    )
    for (workload, stage), samples in sorted(grouped.items()):
        row: dict[str, Any] = {"workload": workload, "stage": stage, "measured_repeats": len(samples)}
        for field in fields:
            row[f"median_{field}"] = _summary(samples, field)
        if len(samples) != repeats:
            row["repeat_count_warning"] = f"expected {repeats}, observed {len(samples)}"
        summary.append(row)
    return summary


def run_benchmark(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    flang = args.flang.resolve()
    json_plugin = args.json_plugin.resolve()
    protobuf_plugin = args.protobuf_plugin.resolve()
    protoc = args.protoc.resolve()
    fixture_root = args.fixture_root.resolve()
    time_executable = shutil.which("time") or "/usr/bin/time"
    if not Path(time_executable).is_file():
        raise RuntimeError("GNU /usr/bin/time is required to record per-process peak RSS")

    for description, path in (
        ("Flang", flang),
        ("JSON plugin", json_plugin),
        ("protobuf plugin", protobuf_plugin),
        ("protoc", protoc),
    ):
        if not path.is_file():
            raise RuntimeError(f"{description} does not exist: {path}")
    if not fixture_root.is_dir():
        raise RuntimeError(f"fixture root does not exist: {fixture_root}")
    for value, name in ((args.warmups, "warmups"), (args.repeats, "repeats")):
        if value < (0 if name == "warmups" else 1):
            raise RuntimeError(f"{name} must be {'at least 0' if name == 'warmups' else 'at least 1'}")
    if args.synthetic_statements < 0:
        raise RuntimeError("synthetic statement count must be at least 0")

    env = os.environ.copy()
    sources = _discover_sources([fixture_root])
    small_source = (fixture_root / args.small_source).resolve()
    large_source = (fixture_root / args.large_source).resolve()
    for label, source in (("small", small_source), ("large", large_source)):
        if not source.is_file() or source.suffix != ".f90":
            raise RuntimeError(f"{label} source must be an existing .f90 file: {source}")
        if source not in sources:
            sources.append(source)
    sources = sorted(set(sources), key=lambda path: path.as_posix())

    started = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {
        "schema_version": 1,
        "started_utc": started,
        "configuration": {
            "warmups": args.warmups,
            "repeats": args.repeats,
            "gzip_mtime": GZIP_MTIME,
            "gzip_compresslevel": GZIP_LEVEL,
            "timing_tool": time_executable,
            "small_source": args.small_source.as_posix(),
            "large_source": args.large_source.as_posix(),
            "synthetic_assignment_statements": args.synthetic_statements,
        },
        "measurement_method": {
            "producer_wall_time": "GNU time %e for each direct producer process plus parent perf_counter wall time for the timed invocation",
            "peak_rss": "GNU time %M KiB for each directly timed process",
            "stdout_size": "captured stdout byte length; gzip size computed after process exit at fixed mtime 0 and level 9",
            "decoder_scope": "separate Python test-decoder process; excludes Java Metafor and does not represent Java end-to-end memory",
        },
        "provenance": {
            "producer_checkout": _git_provenance(REPOSITORY_ROOT),
            "fixture_checkout": _git_provenance(fixture_root),
            "artifacts": {
                "flang": {"path": str(flang), "sha256": _sha256_file(flang)},
                "json_plugin": {"path": str(json_plugin), "sha256": _sha256_file(json_plugin)},
                "protobuf_plugin": {"path": str(protobuf_plugin), "sha256": _sha256_file(protobuf_plugin)},
                "protoc": {"path": str(protoc), "sha256": _sha256_file(protoc)},
                "plugin_compilation_objects": {},
            },
            "source_files": {
                "benchmark_harness": {
                    "path": str(Path(__file__).resolve()),
                    "sha256": _sha256_file(Path(__file__).resolve()),
                },
                "protocol_schema": {"path": str(PROTO_FILE), "sha256": _sha256_file(PROTO_FILE)},
                "python_test_decoder": {
                    "path": str(BASELINE_DIR / "decode_ast_stream.py"),
                    "sha256": _sha256_file(BASELINE_DIR / "decode_ast_stream.py"),
                },
                "graph_comparator": {
                    "path": str(BASELINE_DIR / "compare_graphs.py"),
                    "sha256": _sha256_file(BASELINE_DIR / "compare_graphs.py"),
                },
                "corpus_preflight": {
                    "path": str(BASELINE_DIR / "compare_native_corpus.py"),
                    "sha256": _sha256_file(BASELINE_DIR / "compare_native_corpus.py"),
                },
            },
            "runtime": {
                "platform": platform.platform(),
                "python": sys.version,
                "flang_version": _version([str(flang), "--version"], env),
                "protoc_version": _version([str(protoc), "--version"], env),
                "gnu_time_version": _version([time_executable, "--version"], env),
            },
        },
    }
    for artifact_name, plugin, object_name in (
        ("json", json_plugin, "json-plugin.o"),
        ("protobuf", protobuf_plugin, "binary-plugin.o"),
    ):
        object_path = plugin.parent / object_name
        if object_path.is_file():
            report["provenance"]["artifacts"]["plugin_compilation_objects"][artifact_name] = {
                "path": str(object_path),
                "sha256": _sha256_file(object_path),
                "elf_comment_compiler_markers": _elf_compiler_markers(object_path),
            }

    with tempfile.TemporaryDirectory(prefix="native-protocol-benchmark-") as temporary:
        temporary_path = Path(temporary)
        generated_dir = temporary_path / "decoder"
        try:
            record_class = _prepare_decoder(protoc, generated_dir, env)
        except (OSError, RuntimeError) as error:
            report["setup_failure"] = str(error)
            return report, 1
        report["provenance"]["source_files"]["generated_python_protobuf_module"] = {
            "path": str(generated_dir / "ast_stream_pb2.py"),
            "sha256": _sha256_file(generated_dir / "ast_stream_pb2.py"),
        }

        corpus_outcomes = [
            _preflight_source(
                source,
                fixture_root=fixture_root,
                flang=flang,
                json_plugin=json_plugin,
                protobuf_plugin=protobuf_plugin,
                record_class=record_class,
            )
            for source in sources
        ]
        counts = {
            status: sum(outcome["status"] == status for outcome in corpus_outcomes)
            for status in ("matched", "baseline_failure", "protobuf_failure", "mismatch")
        }
        report["parity_preflight"] = {
            "total": len(corpus_outcomes),
            **counts,
            "outcomes": corpus_outcomes,
            "benchmark_gate": "pass" if counts["protobuf_failure"] == 0 and counts["mismatch"] == 0 else "fail",
            "baseline_failures_do_not_count_as_protobuf_mismatches": True,
        }
        if counts["protobuf_failure"] or counts["mismatch"]:
            report["status"] = "parity_gate_failed"
            report["measurements"] = []
            report["medians"] = []
            report["finished_utc"] = datetime.now(timezone.utc).isoformat()
            return report, 1

        synthetic_path: Path | None = None
        if args.synthetic_statements:
            synthetic_path = temporary_path / f"synthetic-assignment-{args.synthetic_statements}.f90"
            synthetic_path.write_bytes(_synthetic_source(args.synthetic_statements))
            synthetic_preflight = _preflight_source(
                synthetic_path,
                fixture_root=fixture_root,
                flang=flang,
                json_plugin=json_plugin,
                protobuf_plugin=protobuf_plugin,
                record_class=record_class,
            )
            synthetic_preflight["label"] = f"synthetic/assignment-chain-{args.synthetic_statements}"
            synthetic_preflight["path"] = "generated:synthetic-assignment-source"
            report["parity_preflight"]["synthetic"] = synthetic_preflight
            if synthetic_preflight["status"] != "matched":
                report["status"] = "parity_gate_failed"
                report["measurements"] = []
                report["medians"] = []
                report["finished_utc"] = datetime.now(timezone.utc).isoformat()
                return report, 1

        outcome_by_path = {Path(outcome["path"]): outcome["status"] for outcome in corpus_outcomes}
        workloads: list[tuple[str, Path]] = []
        for label, source in (("small", small_source), ("large", large_source)):
            workloads.append((label, source))
        if synthetic_path is not None:
            workloads.append((f"synthetic/assignment-chain-{args.synthetic_statements}", synthetic_path))

        measurements: list[dict[str, Any]] = []
        measurement_failures = 0
        pythonpath_parts = [str(generated_dir), str(BASELINE_DIR)]
        if env.get("PYTHONPATH"):
            pythonpath_parts.append(env["PYTHONPATH"])
        decoder_env = dict(env)
        decoder_env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
        for workload, source in workloads:
            description = _source_description(source, fixture_root)
            if workload.startswith("synthetic/"):
                description["label"] = workload
                description["path"] = "generated:synthetic-assignment-source"
            if source in outcome_by_path and outcome_by_path[source] != "matched":
                # A JSON baseline failure is not silently used as a workload.
                report.setdefault("skipped_workloads", []).append(
                    {"workload": workload, "reason": outcome_by_path[source]}
                )
                continue
            for iteration in range(args.warmups + args.repeats):
                warmup = iteration < args.warmups
                sample_index = iteration if warmup else iteration - args.warmups
                for stage, plugin, action in (
                    ("json_producer", json_plugin, "dump-ast"),
                    ("protobuf_producer", protobuf_plugin, "dump-ast-protobuf"),
                ):
                    result = _run_timed(
                        _command(flang, plugin, action, source),
                        time_executable=time_executable,
                        env=env,
                    )
                    stdout = result.pop("_stdout", b"")
                    record = {
                        "workload": workload,
                        "stage": stage,
                        "iteration": iteration,
                        "warmup": warmup,
                        "sample_index": sample_index,
                        "source": description,
                        **result,
                    }
                    measurements.append(record)
                    if result.get("returncode") != 0 or result.get("launcher_error"):
                        measurement_failures += 1
                        record["failure"] = "producer subprocess did not complete successfully"
                        continue
                    if stage == "protobuf_producer":
                        stream_path = temporary_path / f"{len(measurements)}.astpb"
                        stream_path.write_bytes(stdout)
                        decoder_result = _run_timed(
                            [
                                sys.executable,
                                "-c",
                                DECODER_CODE,
                                str(stream_path),
                            ],
                            time_executable=time_executable,
                            env=decoder_env,
                        )
                        decoder_result.pop("_stdout", None)
                        decoder_record = {
                            "workload": workload,
                            "stage": "python_test_decoder",
                            "iteration": iteration,
                            "warmup": warmup,
                            "sample_index": sample_index,
                            "source": description,
                            "input_stream_bytes": stream_path.stat().st_size,
                            **decoder_result,
                        }
                        measurements.append(decoder_record)
                        if decoder_result.get("returncode") != 0 or decoder_result.get("launcher_error"):
                            measurement_failures += 1
                            decoder_record["failure"] = "Python test-decoder subprocess did not complete successfully"

        report["measurements"] = measurements
        report["medians"] = _summarize_measurements(measurements, args.repeats)
        report["measurement_failures"] = measurement_failures
        report["status"] = "complete" if measurement_failures == 0 else "measurement_failed"
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        return report, 0 if measurement_failures == 0 else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flang", required=True, type=Path)
    parser.add_argument("--json-plugin", required=True, type=Path)
    parser.add_argument("--protobuf-plugin", required=True, type=Path)
    parser.add_argument("--protoc", required=True, type=Path)
    parser.add_argument("--fixture-root", required=True, type=Path, help="Metafor resources-test root")
    parser.add_argument("--small-source", type=Path, default=Path("fortran/parser/hello.f90"))
    parser.add_argument("--large-source", type=Path, default=Path("fortran/parser/polybench/3mm.f90"))
    parser.add_argument("--synthetic-statements", type=int, default=512, help="0 disables the synthetic workload")
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, default=Path("docs/protocol-benchmark-report.json"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        report, status = run_benchmark(args)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"benchmark setup failed: {error}", file=sys.stderr)
        return 2
    output = args.output if args.output.is_absolute() else REPOSITORY_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    parity = report.get("parity_preflight", {})
    print(
        "parity: "
        f"total={parity.get('total', 0)} matched={parity.get('matched', 0)} "
        f"baseline_failure={parity.get('baseline_failure', 0)} "
        f"protobuf_failure={parity.get('protobuf_failure', 0)} mismatch={parity.get('mismatch', 0)}"
    )
    print(f"status: {report.get('status', 'setup_failed')}")
    print(f"report: {output}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
