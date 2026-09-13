"""Hermetic `openspec` CLI fakes for watcher/boundary tests.

The fake answers the exact argv vectors the lifecycle uses, deriving
queue answers from the fixture's own `tasks.md` files so tests exercise
the real JSON parsing and boundary decisions without spawning Node.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


class FakeCompletedProcess:
    """Minimal `subprocess.CompletedProcess` surface used by the boundary."""

    def __init__(self, returncode: int, stdout: str, stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def task_counts(tasks_path: Path) -> tuple[int, int]:
    """`(completed, total)` checkbox counts mirroring `openspec list`."""
    try:
        text = tasks_path.read_text(encoding="utf-8")
    except OSError:
        return 0, 0
    total = 0
    completed = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ]"):
            total += 1
        elif stripped.startswith("- [x]") or stripped.startswith("- [X]"):
            total += 1
            completed += 1
    return completed, total


def make_runner(
    root: Path | str,
    *,
    spec_ids: tuple[str, ...] = (),
    validate_ok: bool = True,
    validate_output: str = "",
    missing_binary: bool = False,
    force_timeout: bool = False,
    malformed_list: bool = False,
) -> object:
    """Build a fake `subprocess.run` for OpenSpec evidence commands."""

    def run(argv: object, **kwargs: object) -> FakeCompletedProcess:
        args = list(argv)  # type: ignore[arg-type]
        if missing_binary:
            raise FileNotFoundError("No such file or directory: 'openspec'")
        if force_timeout:
            raise subprocess.TimeoutExpired(args, 30)
        cwd = Path(str(kwargs.get("cwd") or root))
        changes_base = cwd / "openspec" / "changes"
        if args[:2] == ["openspec", "list"] and "--specs" in args:
            payload = {
                "specs": [{"id": spec_id} for spec_id in spec_ids],
                "root": {"path": str(cwd), "source": "nearest"},
            }
            return FakeCompletedProcess(0, json.dumps(payload))
        if args[:2] == ["openspec", "list"]:
            if malformed_list:
                return FakeCompletedProcess(0, "{not json")
            changes = []
            if changes_base.is_dir():
                for entry in sorted(changes_base.iterdir(), key=lambda e: e.name):
                    if not entry.is_dir() or entry.name in ("archive",):
                        continue
                    if entry.name.startswith("."):
                        continue
                    completed, total = task_counts(entry / "tasks.md")
                    changes.append(
                        {
                            "name": entry.name,
                            "completedTasks": completed,
                            "totalTasks": total,
                            "status": (
                                "complete"
                                if total and completed == total
                                else "in-progress"
                            ),
                        }
                    )
            payload = {
                "changes": changes,
                "root": {"path": str(cwd), "source": "nearest"},
            }
            return FakeCompletedProcess(0, json.dumps(payload))
        if args[:2] == ["openspec", "status"]:
            name = args[args.index("--change") + 1]
            target = changes_base / str(name)
            if not target.is_dir():
                payload = {
                    "status": [
                        {
                            "severity": "error",
                            "code": "change_error",
                            "message": f"Change '{name}' not found.",
                        }
                    ]
                }
                return FakeCompletedProcess(0, json.dumps(payload))
            completed, total = task_counts(target / "tasks.md")
            payload = {
                "changeName": name,
                "isComplete": bool(total) and completed == total,
                "root": {"path": str(cwd), "source": "nearest"},
            }
            return FakeCompletedProcess(0, json.dumps(payload))
        if args[:2] == ["openspec", "validate"]:
            if validate_ok:
                return FakeCompletedProcess(
                    0, validate_output or "Totals: 1 passed, 0 failed"
                )
            return FakeCompletedProcess(
                1, validate_output or "Totals: 0 passed, 1 failed"
            )
        raise AssertionError(f"unexpected openspec argv in tests: {args}")

    return run
