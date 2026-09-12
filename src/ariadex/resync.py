"""Resynchronization after manual intervention.

Returning to AUTO rereads the handoff, git status, git diff summary,
current spec, and unresolved queue, then recomputes the next action from
that evidence. Manual changes are evidence only: resync never marks work
complete, and configured verification still gates completion.
"""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

from . import handoff as handoff_mod
from .config import Config
from .runner import (
    ACTION_IDLE,
    ACTION_STOP,
    inspect_repository,
    select_next_action,
)

MAX_DIFF_CHARS = 4000


@dataclasses.dataclass
class ResyncReport:
    git_available: bool
    changed_files: list
    diff_stat: str
    specs_observed: list
    next_action: str
    notes: list


def _git_capture(project_dir: Path, args: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_dir), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def resync(
    project_dir: Path, config: Config
) -> tuple[handoff_mod.Handoff, ResyncReport]:
    """Reconcile durable state. Raises HandoffError on unreadable handoff."""
    handoff = handoff_mod.read_handoff(project_dir / config.handoff_file)
    notes: list[str] = []

    status_out = _git_capture(project_dir, ["status", "--porcelain"])
    changed_files: list[str] = []
    if status_out is None:
        git_available = False
        notes.append("git unavailable: resync used handoff and spec state only")
    else:
        git_available = True
        for line in status_out.splitlines():
            name = line[3:].strip().strip('"')
            if name:
                changed_files.append(name)
        if changed_files:
            notes.append(
                f"{len(changed_files)} uncommitted change(s) treated as "
                "evidence; verification still required"
            )

    diff_stat = ""
    if git_available:
        diff_out = _git_capture(project_dir, ["diff", "--stat", "--", "."])
        if diff_out:
            diff_stat = diff_out[:MAX_DIFF_CHARS]

    repo = inspect_repository(project_dir, config.spec_dir)
    if repo.missing_spec_dir:
        notes.append(f"spec directory `{config.spec_dir}` is missing")

    previous_action = handoff.next_action
    kind, target = select_next_action(handoff, repo, retry_limit=config.retry_limit)
    next_action = (
        "none — idle" if kind in (ACTION_IDLE, ACTION_STOP) else f"{kind} {target}"
    )
    handoff.next_action = next_action
    if previous_action != next_action:
        notes.append(
            f"next action recomputed: `{previous_action or '(none)'}` "
            f"-> `{next_action}`"
        )
    opens = handoff_mod.open_items(handoff)
    if opens and not changed_files and git_available:
        notes.append(
            f"{len(opens)} OPEN issue(s) remain actionable; "
            "a clean tree does not mark work complete"
        )
    handoff_mod.write_handoff(project_dir / config.handoff_file, handoff)
    return handoff, ResyncReport(
        git_available=git_available,
        changed_files=changed_files,
        diff_stat=diff_stat,
        specs_observed=repo.specs,
        next_action=next_action,
        notes=notes,
    )
