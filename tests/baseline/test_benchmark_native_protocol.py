from __future__ import annotations

import gzip
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import benchmark_native_protocol as benchmark  # noqa: E402


class NativeProtocolBenchmarkTests(unittest.TestCase):
    def test_gzip_size_uses_repeatable_fixed_timestamp(self) -> None:
        payload = b"protocol benchmark payload\n" * 20
        first = gzip.compress(payload, compresslevel=9, mtime=0)
        second = gzip.compress(payload, compresslevel=9, mtime=0)

        self.assertEqual(first, second)
        self.assertEqual(benchmark._gzip_size(payload), len(first))
        self.assertEqual(gzip.decompress(first), payload)
        self.assertEqual(first[4:8], b"\0\0\0\0")

    @unittest.skipUnless(Path("/usr/bin/time").is_file(), "GNU /usr/bin/time is required")
    def test_timed_subprocess_records_output_duration_and_peak_rss(self) -> None:
        result = benchmark._run_timed(
            [sys.executable, "-c", "import sys; sys.stdout.write('payload')"],
            time_executable="/usr/bin/time",
        )

        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["timed_command_exit_code"], 0)
        self.assertGreaterEqual(result["wall_seconds"], 0)
        self.assertGreaterEqual(result["gnu_time_elapsed_seconds"], 0)
        self.assertGreater(result["peak_rss_kib"], 0)
        self.assertEqual(result["raw_stdout_bytes"], len(b"payload"))
        self.assertEqual(result["_stdout"], b"payload")

    @unittest.skipUnless(Path("/usr/bin/time").is_file(), "GNU /usr/bin/time is required")
    def test_timed_subprocess_preserves_nonzero_exit_and_stderr(self) -> None:
        result = benchmark._run_timed(
            [sys.executable, "-c", "import sys; print('failed', file=sys.stderr); sys.exit(7)"],
            time_executable="/usr/bin/time",
        )

        self.assertEqual(result["returncode"], 7)
        self.assertEqual(result["timed_command_exit_code"], 7)
        self.assertIn("failed", result["stderr"])

    def test_synthetic_workload_is_deterministic_and_counted(self) -> None:
        source = benchmark._synthetic_source(12)
        self.assertEqual(source, benchmark._synthetic_source(12))
        self.assertEqual(source.count(b"value = value +"), 12)
        self.assertIn(b"program synthetic_protocol_benchmark", source)
        self.assertTrue(source.endswith(b"end program synthetic_protocol_benchmark\n"))

    def test_json_baseline_failure_is_not_classified_as_native_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "REAL16.f90"
            source.write_text("program p\nend program p\n", encoding="utf-8")
            failed = subprocess.CompletedProcess([], 1, b"", b"unsupported REAL16")
            with patch.object(benchmark, "_run", return_value=failed) as run:
                result = benchmark._preflight_source(
                    source,
                    fixture_root=Path(temporary),
                    flang=Path("/flang"),
                    json_plugin=Path("/json.so"),
                    protobuf_plugin=Path("/protobuf.so"),
                    record_class=object,
                )

        self.assertEqual(result["status"], "baseline_failure")
        self.assertIn("unsupported REAL16", result["detail"])
        run.assert_called_once()

    def test_native_graph_mismatch_has_distinct_status(self) -> None:
        baseline_run = subprocess.CompletedProcess([], 0, b"json", b"")
        protobuf_run = subprocess.CompletedProcess([], 0, b"wire", b"")
        baseline_graph = object()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "input.f90"
            source.touch()
            with (
                patch.object(benchmark, "_run", side_effect=[baseline_run, protobuf_run]),
                patch.object(benchmark, "_load_json_graph", return_value=baseline_graph),
                patch.object(benchmark, "decode_stream", return_value=object()),
                patch.object(benchmark, "compare_graphs", return_value=False),
            ):
                result = benchmark._preflight_source(
                    source,
                    fixture_root=Path(temporary),
                    flang=Path("/flang"),
                    json_plugin=Path("/json.so"),
                    protobuf_plugin=Path("/protobuf.so"),
                    record_class=object,
                )

        self.assertEqual(result["status"], "mismatch")

    def test_medians_exclude_warmups_and_retain_repeat_count(self) -> None:
        rows = [
            {"workload": "small", "stage": "json_producer", "warmup": True, "wall_seconds": 100},
            {"workload": "small", "stage": "json_producer", "warmup": False, "wall_seconds": 2},
            {"workload": "small", "stage": "json_producer", "warmup": False, "wall_seconds": 4},
        ]
        summary = benchmark._summarize_measurements(rows, repeats=2)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["measured_repeats"], 2)
        self.assertEqual(summary[0]["median_wall_seconds"], 3)
        self.assertNotIn("repeat_count_warning", summary[0])


if __name__ == "__main__":
    unittest.main()
