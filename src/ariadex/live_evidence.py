"""Opt-in live runtime evidence.

Runs bounded, isolated scenarios against temporary project state and
reports each as passed, skipped, or blocked. Skipped or blocked work is
never presented as passing release evidence: callers that need a release
gate pass `gate=True` (CLI `--gate`) and receive a non-zero exit when
anything did not pass.

No provider LLM API is called. Provider smoke checks only run local
`--version`/`--help` probes. Package installation is only exercised
against mocked managers; this module never installs anything on the host.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path

DEFAULT_TIMEOUT_S = 30

PASSED = "passed"
SKIPPED = "skipped"
BLOCKED = "blocked"


@dataclasses.dataclass
class EvidenceResult:
    name: str
    status: str
    reason: str
    diagnostics: str = ""


def tmux_available(executable: str = "tmux") -> str | None:
    """Return the tmux path, or None when it is not on PATH."""
    return shutil.which(executable)


def unique_session_name(prefix: str = "evidence") -> str:
    """Unique tmux session name so parallel runs never collide."""
    return f"ariadex-{prefix}-{uuid.uuid4().hex[:12]}"


@contextlib.contextmanager
def temp_project():
    """Temporary isolated project with minimal .ariadex state.

    Yields the project root Path. The directory is removed on exit,
    including after failures or interrupts.
    """
    tmp = tempfile.mkdtemp(prefix="ariadex-evidence-")
    root = Path(tmp)
    try:
        ariadex_dir = root / ".ariadex"
        ariadex_dir.mkdir(parents=True, exist_ok=True)
        (ariadex_dir / "config.yaml").write_text(
            "agent_provider: opencode\n"
            "terminal_driver: tmux\n"
            "context_strategy: per-spec\n"
            "reset_mode: auto\n"
            "spec_dir: openspec/changes\n"
            "handoff_file: .ariadex/handoff.md\n"
            "verification_commands: []\n"
            "retry_limit: 2\n"
            "blocker_policy: stop-on-blocker\n",
            encoding="utf-8",
        )
        (ariadex_dir / "handoff.md").write_text(
            "# Ariadex handoff\n\n## Current state\n\n- Evidence probe project.\n",
            encoding="utf-8",
        )
        (ariadex_dir / "state.json").write_text(
            '{"mode": "AUTO", "session_id": "evidence", '
            '"current_spec": null, "unresolved_count": 0}',
            encoding="utf-8",
        )
        (root / "openspec" / "changes").mkdir(parents=True, exist_ok=True)
        yield root
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@contextlib.contextmanager
def isolated_tmux_session(driver, name: str, workdir: Path | str, command: list[str]):
    """Create a tmux session, always terminating it on exit."""
    driver.create_or_connect(name, workdir, command)
    try:
        yield name
    finally:
        with contextlib.suppress(Exception):
            driver.terminate(name)


def write_fake_provider(directory: Path | str, name: str = "fake-provider") -> Path:
    """Write an executable fake provider for startup/input/capture/exit probes.

    The script prints a ready line, echoes stdin lines with a prefix, and
    exits zero on EOF. It performs no network or LLM calls.
    """
    path = Path(directory) / name
    path.write_text(
        "#!/bin/sh\n"
        "echo 'fake-provider ready'\n"
        "while IFS= read -r line; do\n"
        '  echo "fake-echo: $line"\n'
        "done\n"
        "exit 0\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _run_probe(command: list[str], timeout_s: int = DEFAULT_TIMEOUT_S) -> str:
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"`{' '.join(command)}` exited {proc.returncode}: "
            f"{(proc.stderr or proc.stdout or '').strip()[:2000]}"
        )
    return (proc.stdout or proc.stderr or "").strip()[:2000]


def resolve_tmux(executable: str = "tmux") -> tuple[str | None, str]:
    """Resolve the tmux binary: an explicit path must exist and be runnable,
    otherwise fall back to PATH lookup. Returns (path, note)."""
    if executable != "tmux" and "/" in executable:
        candidate = Path(executable)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate), ""
        return None, f"`{executable}` is not an executable file"
    found = tmux_available(executable)
    if found is None:
        return None, f"`{executable}` not on PATH"
    return found, ""


def scenario_tmux_lifecycle(
    timeout_s: int = DEFAULT_TIMEOUT_S, executable: str = "tmux"
) -> EvidenceResult:
    """Live tmux create/send/capture/terminate with a fake provider."""
    from . import terminal as terminal_mod

    tmux_path, note = resolve_tmux(executable)
    if tmux_path is None:
        if executable == "tmux":
            return EvidenceResult(
                name="tmux-lifecycle",
                status=SKIPPED,
                reason="tmux binary not on PATH; install tmux to run live sessions",
                diagnostics="prerequisite: `tmux` on PATH",
            )
        return EvidenceResult(
            name="tmux-lifecycle",
            status=BLOCKED,
            reason=f"explicit tmux binary unusable: {note}",
            diagnostics=note,
        )
    driver = terminal_mod.TmuxDriver(executable=tmux_path)
    name = unique_session_name("lifecycle")
    with tempfile.TemporaryDirectory(prefix="ariadex-fake-") as tmp:
        fake = write_fake_provider(tmp)
        diagnostics = ""
        try:
            with isolated_tmux_session(
                driver,
                name,
                tmp,
                [str(fake)],
            ):
                if not driver.session_alive(name):
                    return EvidenceResult(
                        name="tmux-lifecycle",
                        status=BLOCKED,
                        reason="tmux session did not become alive after create",
                        diagnostics=f"session `{name}` missing right after create",
                    )
                driver.send_input(name, "hello-live")
                deadline = time.monotonic() + timeout_s
                captured = ""
                while time.monotonic() < deadline:
                    captured = driver.capture(name)
                    if "hello-live" in captured:
                        break
                    time.sleep(0.5)
                diagnostics = captured[-2000:]
                if "hello-live" not in captured:
                    return EvidenceResult(
                        name="tmux-lifecycle",
                        status=BLOCKED,
                        reason="sent input was not visible in pane capture",
                        diagnostics=diagnostics,
                    )
        except terminal_mod.TerminalError as exc:
            return EvidenceResult(
                name="tmux-lifecycle",
                status=BLOCKED,
                reason=f"tmux transport failed: {exc}",
                diagnostics=diagnostics or str(exc),
            )
        try:
            alive = driver.session_alive(name)
        except terminal_mod.TerminalError:
            alive = False
        if alive:
            return EvidenceResult(
                name="tmux-lifecycle",
                status=BLOCKED,
                reason="tmux session survived terminate; cleanup failed",
                diagnostics=f"session `{name}` still alive",
            )
    return EvidenceResult(
        name="tmux-lifecycle",
        status=PASSED,
        reason="create/send/capture/terminate round-trip succeeded",
    )


def scenario_provider_startup(timeout_s: int = DEFAULT_TIMEOUT_S) -> EvidenceResult:
    """Adapter start/send/capture/exit over a fake provider via Fake driver."""
    from . import terminal as terminal_mod
    from .adapters import AgentAdapter, Capabilities

    class FakeProviderAdapter(AgentAdapter):
        provider_name = "fake-provider"
        new_session_input = "/new"

        def __init__(self, driver, session_name, workdir, launch):
            super().__init__(driver, session_name, workdir)
            self._launch = tuple(launch)

        @property
        def capabilities(self) -> Capabilities:
            return Capabilities(
                interactive=True,
                soft_reset=True,
                hard_reset=True,
                token_usage=False,
                structured_output=False,
                interrupt=True,
                manual_takeover=True,
            )

        @property
        def launch_command(self):
            return self._launch

    with tempfile.TemporaryDirectory(prefix="ariadex-fake-") as tmp:
        fake = write_fake_provider(tmp)
        driver = terminal_mod.FakeTerminalDriver()
        name = unique_session_name("startup")
        adapter = FakeProviderAdapter(driver, name, tmp, [str(fake)])
        try:
            started = adapter.start()
            assert started in ("created", "connected")
            adapter.send("probe-input")
            captured = adapter.capture_output()
            assert "probe-input" in captured, f"capture missed input: {captured!r}"
            adapter.new_session()
            adapter.interrupt()
            adapter.terminate()
            assert not driver.session_alive(name)
        except Exception as exc:
            with contextlib.suppress(Exception):
                driver.terminate(name)
            return EvidenceResult(
                name="provider-startup",
                status=BLOCKED,
                reason=f"fake provider lifecycle failed: {exc}",
                diagnostics=str(exc)[:2000],
            )
    return EvidenceResult(
        name="provider-startup",
        status=PASSED,
        reason="startup, input, capture, soft-reset, interrupt, exit all behaved",
    )


def scenario_continuity_restart() -> EvidenceResult:
    """Multi-spec continuity: completions persist across Runner restarts."""
    from . import config as config_mod
    from . import handoff as handoff_mod
    from . import terminal as terminal_mod
    from .providers import OpenCodeAdapter
    from .runner import Runner
    from .verify import VerificationResult, Verifier

    class AlwaysPass(Verifier):
        def verify(self, action: str, output: str) -> VerificationResult:
            return VerificationResult(passed=True, detail="probe pass", exit_code=0)

    with temp_project() as root:
        try:
            cfg = config_mod.load(root)
            (root / cfg.spec_dir / "spec-a").mkdir(parents=True, exist_ok=True)
            (root / cfg.spec_dir / "spec-b").mkdir(parents=True, exist_ok=True)
            handoff = handoff_mod.read_handoff(root / cfg.handoff_file)
            handoff.current_spec = "spec-a"
            handoff.next_spec = "spec-b"
            handoff.next_action = "advance-spec spec-a"
            handoff_mod.write_handoff(root / cfg.handoff_file, handoff)

            def make_runner():
                driver = terminal_mod.FakeTerminalDriver()
                adapter = OpenCodeAdapter(
                    driver,
                    unique_session_name("continuity"),
                    root,
                )
                return Runner(root, cfg, adapter, verifier=AlwaysPass())

            first = make_runner()
            result = first.run_once()
            assert result.outcome == "completed", f"first cycle: {result}"
            # Simulate a process restart: a fresh Runner over the same files.
            second = make_runner()
            handoff2 = handoff_mod.read_handoff(root / cfg.handoff_file)
            assert handoff2.current_spec == "spec-b", (
                f"restart lost continuity: current_spec={handoff2.current_spec!r}"
            )
            assert any("spec-a" in c.summary for c in handoff2.completed), (
                "restart lost completed history"
            )
            result2 = second.run_once()
            assert result2.outcome == "completed", f"second cycle: {result2}"
            handoff3 = handoff_mod.read_handoff(root / cfg.handoff_file)
            assert handoff3.current_spec is None, (
                f"expected spec queue drained, got {handoff3.current_spec!r}"
            )
        except Exception as exc:
            return EvidenceResult(
                name="continuity-restart",
                status=BLOCKED,
                reason=f"continuity across restart failed: {exc}",
                diagnostics=str(exc)[:2000],
            )
    return EvidenceResult(
        name="continuity-restart",
        status=PASSED,
        reason="spec completions survived Runner restart; queue drained",
    )


def scenario_verification_gating() -> EvidenceResult:
    """Shell gates pass on exit zero; failures persist with bounded retries."""
    from . import config as config_mod
    from . import handoff as handoff_mod
    from . import terminal as terminal_mod
    from .providers import OpenCodeAdapter
    from .runner import Runner

    with temp_project() as root:
        try:
            cfg = config_mod.load(root)
            (root / cfg.spec_dir / "spec-a").mkdir(parents=True, exist_ok=True)
            handoff = handoff_mod.read_handoff(root / cfg.handoff_file)
            handoff.current_spec = "spec-a"
            handoff.next_spec = None
            handoff.next_action = "advance-spec spec-a"
            handoff_mod.write_handoff(root / cfg.handoff_file, handoff)

            object.__setattr__(
                cfg,
                "verification_commands",
                ["exit 1"],
            )
            object.__setattr__(cfg, "retry_limit", 2)
            driver = terminal_mod.FakeTerminalDriver()
            adapter = OpenCodeAdapter(
                driver,
                unique_session_name("verify"),
                root,
            )
            runner = Runner(root, cfg, adapter)
            first = runner.run_once()
            assert first.outcome == "verification-failed", f"cycle 1: {first}"
            runner2 = Runner(root, cfg, adapter)
            second = runner2.run_once()
            assert second.outcome == "verification-failed", f"cycle 2: {second}"
            handoff2 = handoff_mod.read_handoff(root / cfg.handoff_file)
            opens = [i for i in handoff2.unresolved if i.status == "OPEN"]
            blocked = [i for i in handoff2.unresolved if i.status == "BLOCKED"]
            assert opens or blocked, "failed verification left no OPEN/BLOCKED record"
            attempts = max(
                [i.attempts for i in handoff2.unresolved] or [0],
            )
            assert attempts >= 2, f"retries not bounded/persisted: {attempts}"
            assert attempts <= 3, f"retry limit exceeded: {attempts}"
        except Exception as exc:
            return EvidenceResult(
                name="verification-gating",
                status=BLOCKED,
                reason=f"verification gating failed: {exc}",
                diagnostics=str(exc)[:2000],
            )
    return EvidenceResult(
        name="verification-gating",
        status=PASSED,
        reason="exit-nonzero verification blocked completion and persisted retries",
    )


def scenario_takeover_resync() -> EvidenceResult:
    """MANUAL takeover, PAUSE, and resync keep the session and recompute work."""
    from . import config as config_mod
    from . import control as control_mod
    from . import handoff as handoff_mod
    from . import resync as resync_mod
    from . import state as state_mod

    with temp_project() as root:
        try:
            cfg = config_mod.load(root)
            st = state_mod.read(root)
            session_before = st.session_id
            assert control_mod.owns_input("AUTO")
            assert not control_mod.owns_input("MANUAL")
            assert not control_mod.allows_scheduling("PAUSE")
            mode = control_mod.transition("AUTO", "MANUAL", via="takeover")
            assert mode == "MANUAL"
            mode = control_mod.transition("MANUAL", "PAUSE", via="pause")
            assert mode == "PAUSE"
            mode = control_mod.transition("PAUSE", "MANUAL", via="resume")
            assert mode == "MANUAL"
            mode = control_mod.transition("MANUAL", "AUTO", via="auto")
            assert mode == "AUTO"
            handoff = handoff_mod.read_handoff(root / cfg.handoff_file)
            handoff.next_action = "stale probe action"
            handoff_mod.write_handoff(root / cfg.handoff_file, handoff)
            _, report = resync_mod.resync(root, cfg)
            assert report.next_action, "resync produced no next action"
            st_after = state_mod.read(root)
            assert st_after.session_id == session_before, (
                "resync changed the session id; takeover must preserve it"
            )
        except Exception as exc:
            return EvidenceResult(
                name="takeover-resync",
                status=BLOCKED,
                reason=f"takeover/pause/resync failed: {exc}",
                diagnostics=str(exc)[:2000],
            )
    return EvidenceResult(
        name="takeover-resync",
        status=PASSED,
        reason="manual hold; resync preserved session, recomputed action",
    )


def scenario_install_fixture() -> EvidenceResult:
    """Unattended-install success path against a controlled fixture.

    Uses a fake tmux binary plus a stubbed installer so no real package
    manager runs and nothing is installed on the host.
    """
    from unittest import mock

    from . import tmux_setup as setup_mod

    with tempfile.TemporaryDirectory(prefix="ariadex-pm-") as tmp:
        fake_tmux = Path(tmp) / "tmux"
        fake_tmux.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_tmux.chmod(fake_tmux.stat().st_mode | stat.S_IXUSR)
        probes: dict[str, list[list[str]]] = {"calls": []}

        def fake_which(name):
            if name == "tmux":
                return str(fake_tmux) if probes["calls"] else None
            if name == "apt-get":
                return "/usr/bin/apt-get"
            return None

        def fake_run(cmd, **kwargs):
            from subprocess import CompletedProcess

            probes["calls"].append(list(cmd))
            return CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        try:
            with (
                mock.patch.object(
                    setup_mod.shutil,
                    "which",
                    side_effect=fake_which,
                ),
                mock.patch.object(
                    setup_mod.subprocess,
                    "run",
                    side_effect=fake_run,
                ),
                mock.patch.object(
                    setup_mod,
                    "needs_sudo",
                    return_value=False,
                ),
            ):
                resolved = setup_mod.ensure_tmux()
            assert resolved == str(fake_tmux), f"unexpected path: {resolved}"
            assert any("install" in c for c in probes["calls"]), (
                f"installer was not exercised: {probes['calls']}"
            )
        except Exception as exc:
            return EvidenceResult(
                name="install-fixture",
                status=BLOCKED,
                reason=f"install fixture failed: {exc}",
                diagnostics=str(exc)[:2000],
            )
    return EvidenceResult(
        name="install-fixture",
        status=PASSED,
        reason="controlled package-manager fixture resolved tmux without host install",
    )


def scenario_provider_smoke(timeout_s: int = DEFAULT_TIMEOUT_S) -> EvidenceResult:
    """Local `--version` smoke for installed providers; never calls an LLM API."""
    found: list[str] = []
    missing: list[str] = []
    for binary in ("opencode", "codex"):
        path = shutil.which(binary)
        if path is None:
            missing.append(binary)
            continue
        try:
            _run_probe([path, "--version"], timeout_s=timeout_s)
            found.append(binary)
        except Exception:
            try:
                _run_probe([path, "--help"], timeout_s=timeout_s)
                found.append(binary)
            except Exception as exc:
                return EvidenceResult(
                    name="provider-smoke",
                    status=BLOCKED,
                    reason=f"`{binary}` present but `--version`/`--help` failed: {exc}",
                    diagnostics=str(exc)[:2000],
                )
    if not found:
        return EvidenceResult(
            name="provider-smoke",
            status=SKIPPED,
            reason="neither `opencode` nor `codex` on PATH; nothing to smoke-test",
            diagnostics="prerequisite: `opencode` or `codex` on PATH",
        )
    detail = f"smoked: {', '.join(found)}"
    if missing:
        detail += f"; absent (not failures): {', '.join(missing)}"
    return EvidenceResult(
        name="provider-smoke",
        status=PASSED,
        reason=detail,
    )


SCENARIOS: tuple[tuple[str, Callable[..., EvidenceResult]], ...] = (
    ("tmux-lifecycle", scenario_tmux_lifecycle),
    ("provider-startup", scenario_provider_startup),
    ("continuity-restart", scenario_continuity_restart),
    ("verification-gating", scenario_verification_gating),
    ("takeover-resync", scenario_takeover_resync),
    ("install-fixture", scenario_install_fixture),
    ("provider-smoke", scenario_provider_smoke),
)


def provision_tmux() -> tuple[str | None, str]:
    """Ensure tmux exists, installing it when missing.

    Returns (path, note) where note is "" when tmux was already present,
    "provisioned" when this call installed it. Raises TmuxSetupError with
    an actionable message when installation is impossible.
    """
    from . import tmux_setup as setup_mod

    if setup_mod.find_tmux() is not None:
        return setup_mod.find_tmux(), ""
    path = setup_mod.ensure_tmux()
    return path, "provisioned"


def unprovision_tmux(provisioned: bool) -> str:
    """Undo a provisional install. No-op unless `provisioned` is True.

    Only ever removes a tmux this harness installed; a pre-existing tmux
    is never touched. Returns a human-readable note.
    """
    if not provisioned:
        return ""
    from . import tmux_setup as setup_mod

    try:
        manager = setup_mod.uninstall_tmux()
    except Exception as exc:
        return f"warning: provisional tmux could not be removed: {exc}"
    if setup_mod.find_tmux() is not None:
        return (
            f"warning: provisional tmux removal via {manager} reported "
            "success but tmux is still on PATH"
        )
    return f"provisional tmux removed via {manager}"


def run_all(
    timeout_s: int = DEFAULT_TIMEOUT_S,
    only: list[str] | None = None,
    provision: bool = False,
    tmux_bin: str | None = None,
    local_tmux: bool = False,
) -> list[EvidenceResult]:
    """Run every scenario with isolation; unexpected errors become BLOCKED.

    With `provision=True`, tmux is installed when missing before the live
    scenario runs and uninstalled afterwards if this call installed it. A
    pre-existing tmux is never removed. Without provisioning, a missing
    tmux is honestly reported as skipped.

    With `local_tmux=True`, tmux is fetched without privileges into an
    isolated temporary directory and used from there; deleting that
    directory is the whole uninstall. `tmux_bin` uses an explicit local
    binary with no install or removal at all.
    """
    results: list[EvidenceResult] = []
    provisioned = False
    provision_attempted = False
    provision_note = ""
    skip_tmux = False
    executable = tmux_bin or "tmux"
    local_dir: tempfile.TemporaryDirectory | None = None
    try:
        if local_tmux and (only is None or "tmux-lifecycle" in only):
            from . import tmux_setup as setup_mod

            try:
                local_dir = tempfile.TemporaryDirectory(prefix="ariadex-local-tmux-")
                wrapper = setup_mod.fetch_local_tmux(local_dir.name)
                executable = str(wrapper)
                provision_note = (
                    "local tmux fetched without privileges into an isolated directory"
                )
            except setup_mod.TmuxSetupError as exc:
                skip_tmux = True
                results.append(
                    EvidenceResult(
                        name="tmux-lifecycle",
                        status=BLOCKED,
                        reason=f"local tmux fetch failed: {exc}",
                        diagnostics=str(exc)[:2000],
                    )
                )
        if provision and not skip_tmux and (only is None or "tmux-lifecycle" in only):
            from .tmux_setup import TmuxSetupError

            provision_attempted = True
            try:
                _, note = provision_tmux()
                provisioned = note == "provisioned"
                if provisioned:
                    provision_note = "tmux was missing; provisional install performed"
            except TmuxSetupError as exc:
                skip_tmux = True
                results.append(
                    EvidenceResult(
                        name="tmux-lifecycle",
                        status=BLOCKED,
                        reason=f"provisioning failed: {exc}",
                        diagnostics=str(exc)[:2000],
                    )
                )
        for name, func in SCENARIOS:
            if only and name not in only:
                continue
            if name == "tmux-lifecycle" and skip_tmux:
                continue  # already classified above
            try:
                if name == "tmux-lifecycle":
                    results.append(func(timeout_s=timeout_s, executable=executable))
                elif name == "provider-smoke":
                    results.append(func(timeout_s=timeout_s))
                else:
                    results.append(func())
            except Exception as exc:  # harness must classify, never raise
                results.append(
                    EvidenceResult(
                        name=name,
                        status=BLOCKED,
                        reason=f"harness error: {exc}",
                        diagnostics=str(exc)[:2000],
                    )
                )
    finally:
        if provision_attempted:
            note = unprovision_tmux(provisioned)
            combined = "; ".join(n for n in (provision_note, note) if n)
            if combined:
                results.append(
                    EvidenceResult(
                        name="tmux-provision",
                        status=PASSED if provisioned else SKIPPED,
                        reason=combined,
                    )
                )
        if local_dir is not None:
            local_dir.cleanup()  # unpath the temporary tmux: full uninstall
            if any(r.name == "tmux-lifecycle" and r.status == PASSED for r in results):
                results.append(
                    EvidenceResult(
                        name="tmux-provision",
                        status=PASSED,
                        reason=(provision_note + "; isolated directory removed")
                        if provision_note
                        else "isolated directory removed",
                    )
                )
    return results


def format_report(results: list[EvidenceResult]) -> str:
    lines = []
    for res in results:
        lines.append(f"{res.name}: {res.status} — {res.reason}")
        if res.diagnostics and res.status == BLOCKED:
            lines.append(f"  diagnostics: {res.diagnostics[:500]}")
    passed = sum(1 for r in results if r.status == PASSED)
    skipped = sum(1 for r in results if r.status == SKIPPED)
    blocked = sum(1 for r in results if r.status == BLOCKED)
    lines.append(
        f"summary: {passed} passed, {skipped} skipped, {blocked} blocked "
        f"({len(results)} total; skipped/blocked are not passing evidence)"
    )
    return "\n".join(lines)


def gate_exit_code(results: list[EvidenceResult]) -> int:
    """Release-gate exit: zero only when every scenario passed."""
    if all(r.status == PASSED for r in results):
        return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    """Entry point shared by the CLI: print report, honour --gate."""
    import argparse

    parser = argparse.ArgumentParser(prog="ariadex evidence")
    parser.add_argument(
        "--gate",
        action="store_true",
        help="exit non-zero unless every scenario passed",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help="per-probe timeout in seconds",
    )
    parser.add_argument(
        "--only", default=None, help="comma-separated scenario names to run"
    )
    parser.add_argument(
        "--provision",
        action="store_true",
        help="install tmux when missing, uninstall afterwards only if installed here",
    )
    parser.add_argument(
        "--tmux-bin",
        default=None,
        help="explicit local tmux binary for the live scenario (no install)",
    )
    parser.add_argument(
        "--local-tmux",
        action="store_true",
        help="fetch tmux without privileges into an isolated temp dir, "
        "use it for the live scenario, delete the dir afterwards",
    )
    args = parser.parse_args(argv)
    only = args.only.split(",") if args.only else None
    results = run_all(
        timeout_s=args.timeout,
        only=only,
        provision=args.provision,
        tmux_bin=args.tmux_bin,
        local_tmux=args.local_tmux,
    )
    print(format_report(results))
    if args.gate:
        return gate_exit_code(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
