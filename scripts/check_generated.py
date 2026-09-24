#!/usr/bin/env python3
"""Run the local generated-artifact and source-fidelity checks.

This gate checks generated source freshness, registration coverage, and the
Python generator/baseline tests. It does not prove binary integration. Native
fixtures and model regeneration remain separate manual gates.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def checks() -> tuple[tuple[str, list[str]], ...]:
    """Return the checks in the order used by local and CI runs."""
    python = sys.executable
    return (
        (
            "Kind header freshness",
            [python, "generator/generate_kind_header.py", "--check"],
        ),
        (
            "Visitor registrations freshness",
            [python, "generator/generate_visitor_registrations.py", "--check"],
        ),
        (
            "Binary enum catalog freshness",
            [python, "generator/generate_enum_catalogs.py", "--check"],
        ),
        (
            "Registered coverage",
            [python, "generator/check_registered_coverage.py"],
        ),
        (
            "Generator unit tests",
            [python, "-m", "unittest", "discover", "-s", "tests/generator"],
        ),
        (
            "Baseline unit tests",
            [python, "-m", "unittest", "discover", "-s", "tests/baseline"],
        ),
    )


def main() -> int:
    failures = 0
    steps = checks()
    print(
        "Scope: generation and Python tests only; this does not prove binary integration. "
        "Native fixtures and model regeneration remain separate manual gates."
    )

    for label, command in steps:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            print(f"[PASS] {label}")
            continue

        failures += 1
        print(f"[FAIL] {label} (exit {result.returncode})")
        for output in (result.stdout, result.stderr):
            if output:
                print(output.rstrip())

    if failures:
        print(f"Generated checks failed: {failures}/{len(steps)}")
        return 1

    print(f"Generated checks passed: {len(steps)}/{len(steps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
