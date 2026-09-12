#!/usr/bin/env python3
"""Per-module coverage floors for safety-critical modules.

Reads `coverage report` output and fails when any listed module drops
below its floor. Floors sit below the measured 2026-09-12 baseline so
normal refactors pass; a regression in a safety-critical module fails
the gate with the module and missing lines named. Never lowers the
global `fail_under` threshold in pyproject.toml.

Usage: coverage run -m unittest discover -s tests && python3 scripts/check_coverage.py
"""

from __future__ import annotations

import re
import subprocess
import sys

# Module suffix -> minimum percent. Measured baselines in comments.
FLOORS: dict[str, int] = {
    "ariadex/terminal.py": 95,  # measured 100
    "ariadex/tmux_setup.py": 90,  # measured 97
    "ariadex/concurrency.py": 82,  # measured 85
    "ariadex/operator.py": 82,  # measured 85
    "ariadex/live_evidence.py": 80,  # measured 84
    "ariadex/runner.py": 82,  # measured 86
    "ariadex/cli.py": 78,  # measured 81
}

ROW = re.compile(r"^(?P<name>\S+)\s+\d+\s+\d+.*?(?P<pct>\d+)%\s*(?P<missing>.*)$")


def main() -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "coverage", "report"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(f"error: `coverage report` failed:\n{proc.stderr.strip()}")
        return 1
    rows: dict[str, tuple[int, str]] = {}
    for line in proc.stdout.splitlines():
        match = ROW.match(line.strip())
        if match:
            rows[match.group("name")] = (
                int(match.group("pct")),
                match.group("missing").strip(),
            )
    failures = []
    for suffix, floor in FLOORS.items():
        hit = next((n for n in rows if n.endswith(suffix)), None)
        if hit is None:
            failures.append(f"{suffix}: missing from coverage report")
            continue
        pct, missing = rows[hit]
        status = "ok" if pct >= floor else "FAIL"
        print(f"{hit}: {pct}% (floor {floor}%) {status}")
        if pct < floor:
            failures.append(f"{hit}: {pct}% below floor {floor}%; missing: {missing}")
    if failures:
        print("coverage floors FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"coverage floors passed ({len(FLOORS)} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
