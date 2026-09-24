from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_generated.py"
SPEC = importlib.util.spec_from_file_location("check_generated", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class CheckGeneratedTest(unittest.TestCase):
    def test_runs_expected_commands_from_repo_root(self):
        results = [SimpleNamespace(returncode=0, stdout="", stderr="")] * 5
        with patch.object(CHECK.subprocess, "run", side_effect=results) as run:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = CHECK.main()

        self.assertEqual(status, 0)
        self.assertEqual(run.call_count, 5)
        expected_commands = [
            [sys.executable, "generator/generate_kind_header.py", "--check"],
            [sys.executable, "generator/generate_visitor_registrations.py", "--check"],
            [sys.executable, "generator/check_registered_coverage.py"],
            [sys.executable, "-m", "unittest", "discover", "-s", "tests/generator"],
            [sys.executable, "-m", "unittest", "discover", "-s", "tests/baseline"],
        ]
        self.assertEqual(
            [call.args[0] for call in run.call_args_list], expected_commands
        )
        for call in run.call_args_list:
            self.assertEqual(call.kwargs["cwd"], REPO_ROOT)
            self.assertTrue(call.kwargs["capture_output"])
            self.assertTrue(call.kwargs["text"])
        self.assertIn("does not prove binary integration", stdout.getvalue())

    def test_reports_nonzero_status_and_runs_remaining_checks(self):
        results = [
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=7, stdout="generator diagnostic", stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
        ]
        with patch.object(CHECK.subprocess, "run", side_effect=results) as run:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = CHECK.main()

        self.assertEqual(status, 1)
        self.assertEqual(run.call_count, 5)
        output = stdout.getvalue()
        self.assertIn("[FAIL] Visitor registrations freshness (exit 7)", output)
        self.assertIn("generator diagnostic", output)
        self.assertIn("Generated checks failed: 1/5", output)


if __name__ == "__main__":
    unittest.main()
