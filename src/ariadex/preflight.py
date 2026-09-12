"""Release evidence preflight: identify the local toolchain.

Diagnostic only: reports executable paths, versions, and invocation modes
for Python, the installed package, pip-audit, build, provider CLIs, and
tmux. Absent tools are marked MISSING and never labelled passed. Always
exits zero; the report is the artifact, callers decide what it means.
"""

from __future__ import annotations

import argparse
import dataclasses
import platform
import shutil
import subprocess
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path

PROBE_TIMEOUT_S = 10


@dataclasses.dataclass
class ToolStatus:
    """One row of the preflight report."""

    name: str
    present: bool
    path: str = ""
    version: str = ""
    detail: str = ""


def _run_version(argv: list[str]) -> str:
    """Best-effort `<tool> --version` first line; `""` on any failure."""
    try:
        proc = subprocess.run(  # noqa: S603
            argv,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    out = (proc.stdout or proc.stderr or "").strip().splitlines()
    return out[0].strip() if out else ""


def probe_python() -> ToolStatus:
    """Report the interpreter running this preflight."""
    return ToolStatus(
        name="python",
        present=True,
        path=sys.executable,
        version=platform.python_version(),
        detail="interpreter under test",
    )


def probe_package() -> ToolStatus:
    """Report the installed ariadex distribution, if any."""
    try:
        version = importlib_metadata.version("ariadex")
    except importlib_metadata.PackageNotFoundError:
        return ToolStatus(
            name="ariadex-package",
            present=False,
            detail="no installed ariadex distribution; source checkout only",
        )
    try:
        dist = importlib_metadata.distribution("ariadex")
        location = str(dist.locate_file("") or "")
    except Exception:
        location = ""
    return ToolStatus(
        name="ariadex-package",
        present=True,
        path=location,
        version=version,
        detail="installed distribution",
    )


def probe_cli_tool(name: str, hint: str) -> ToolStatus:
    """Report a PATH-resolved CLI and its `--version` first line."""
    path = shutil.which(name)
    if path is None:
        return ToolStatus(name=name, present=False, detail=hint)
    return ToolStatus(
        name=name,
        present=True,
        path=path,
        version=_run_version([path, "--version"]),
        detail="provider CLI on PATH",
    )


def probe_dist_tool(dist_name: str, cli_name: str, hint: str) -> ToolStatus:
    """Report a Python-packaged tool (pip-audit, build) for this interpreter."""
    try:
        version = importlib_metadata.version(dist_name)
    except importlib_metadata.PackageNotFoundError:
        return ToolStatus(name=cli_name, present=False, detail=hint)
    exe = shutil.which(cli_name) or ""
    return ToolStatus(
        name=cli_name,
        present=True,
        path=exe,
        version=version,
        detail=f"distribution {dist_name} installed for this interpreter",
    )


def probe_tmux(tmux_bin: str | None = None) -> ToolStatus:
    """Report the tmux binary evidence would use: explicit path or PATH."""
    if tmux_bin:
        candidate = Path(tmux_bin).expanduser()
        resolved = str(candidate.resolve()) if candidate.exists() else tmux_bin
        if not candidate.is_file():
            return ToolStatus(
                name="tmux",
                present=False,
                detail=f"explicit --tmux-bin not found: {tmux_bin}",
            )
        return ToolStatus(
            name="tmux",
            present=True,
            path=resolved,
            version=_run_version([str(candidate), "-V"]),
            detail="explicit user-supplied binary; no install or removal",
        )
    path = shutil.which("tmux")
    if path is None:
        return ToolStatus(
            name="tmux",
            present=False,
            detail="no tmux on PATH; supply --tmux-bin PATH or use --local-tmux",
        )
    return ToolStatus(
        name="tmux",
        present=True,
        path=path,
        version=_run_version([path, "-V"]),
        detail="system tmux on PATH",
    )


def collect(tmux_bin: str | None = None) -> list[ToolStatus]:
    """Probe every toolchain row in report order."""
    return [
        probe_python(),
        probe_package(),
        probe_dist_tool(
            "pip-audit",
            "pip-audit",
            "pip-audit not installed; security evidence cannot be claimed",
        ),
        probe_dist_tool(
            "build",
            "build",
            "build backend not installed; use cached wheels or install build",
        ),
        probe_cli_tool(
            "opencode",
            "opencode not on PATH; opencode-lifecycle evidence will skip",
        ),
        probe_cli_tool(
            "codex", "codex not on PATH; codex-lifecycle evidence will skip"
        ),
        probe_tmux(tmux_bin),
    ]


def format_report(statuses: list[ToolStatus]) -> str:
    """Render one line per tool; MISSING rows never read as passing."""
    lines = ["preflight toolchain report:"]
    for status in statuses:
        if status.present:
            rendered = f"  {status.name}: present {status.path or '(no path)'}"
            if status.version:
                rendered += f" ({status.version})"
            if status.detail:
                rendered += f" — {status.detail}"
        else:
            rendered = f"  {status.name}: MISSING — {status.detail}"
        lines.append(rendered)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point shared by the CLI: print the report, always exit zero."""
    parser = argparse.ArgumentParser(prog="ariadex preflight")
    parser.add_argument(
        "--tmux-bin",
        default=None,
        help="explicit tmux binary to report (same value evidence would use)",
    )
    args = parser.parse_args(argv)
    print(format_report(collect(args.tmux_bin)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
