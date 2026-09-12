"""Unified prerequisite coordination for managed startup.

One readiness path for runtime, provider, tmux, and desktop/Tkinter widget
prerequisites, checked in dependency order before any daemon, tmux-session,
provider, or widget work begins. The coordinator reuses the existing tmux
setup, companion/Tkinter checks, runtime checks, and development-setup
boundaries while applying one policy:

- Already-present prerequisites continue silently with no output or mutation.
- Missing tmux is prepared automatically through the fixed package-manager
  path (interactive managed starts allow a foreground sudo password prompt;
  anything else keeps the fail-fast passwordless behavior).
- Missing Tkinter follows the existing confirmed-dependency path and is
  verified after installation.
- Provider applications are user-owned and never installed; `uv` and other
  development tools stay owned by `ariadex dev setup` and are never required
  or installed here.

Every prerequisite reports a typed result (`present`, `installed`,
`unsupported`, `declined`, or `blocked`); readiness is claimed only after a
post-install probe succeeds. Successful results carry no package-manager
argv, session names, executable paths, or polling details; failures name the
affected prerequisite plus a manual recovery instruction. The sudo password
is never captured, persisted, or printed: interactive installs inherit the
user's terminal so sudo prompts there directly.
"""

from __future__ import annotations

import dataclasses
import shutil
import sys

from . import providers as providers_mod

#: Smallest supported interpreter for managed startup.
MIN_PYTHON = (3, 11)

#: States a single prerequisite can report. Only `present` and `installed`
#: count as ready; the rest stop managed startup with a recovery instruction.
RESULT_STATES = ("present", "installed", "unsupported", "declined", "blocked")
READY_STATES = ("present", "installed")

#: Guided manual installs for user-owned provider applications. Ariadex never
#: downloads or installs these; their absence is a prerequisite failure.
PROVIDER_INSTALL_GUIDANCE = {
    "opencode": "install the `opencode` CLI on PATH "
    "(see the OpenCode project documentation)",
    "codex": "install the `codex` CLI on PATH "
    "(see the OpenAI Codex project documentation)",
    "codebuddy": "install the `codebuddy` CLI on PATH "
    "(see the CodeBuddy project documentation)",
}


@dataclasses.dataclass
class PrerequisiteResult:
    """Typed outcome for one prerequisite."""

    name: str  # runtime | provider | tmux | widget
    state: str  # one of RESULT_STATES
    detail: str  # short human line; never argv, paths, or secrets
    recovery: str = ""  # manual command or guidance when not ready

    @property
    def ready(self) -> bool:
        return self.state in READY_STATES

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class CoordinatorReport:
    """Ordered prerequisite results plus the overall readiness verdict."""

    results: list[PrerequisiteResult]
    ready: bool

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "results": [result.to_dict() for result in self.results],
        }


def check_runtime(
    *,
    version_info=None,
    yaml_available: bool | None = None,
) -> PrerequisiteResult:
    """Verify the running interpreter and the PyYAML runtime dependency."""
    version = version_info if version_info is not None else sys.version_info
    if yaml_available is None:
        try:
            import yaml  # noqa: F401

            yaml_available = True
        except ImportError:
            yaml_available = False
    if tuple(version[:2]) < MIN_PYTHON or not yaml_available:
        return PrerequisiteResult(
            name="runtime",
            state="blocked",
            detail="managed startup requires Python 3.11+ with PyYAML",
            recovery="run a supported Python with PyYAML installed "
            "(`pip install pyyaml`), then rerun `ariadex start`",
        )
    return PrerequisiteResult(name="runtime", state="present", detail="runtime ready")


def check_provider(provider: str, *, which=None) -> PrerequisiteResult:
    """Verify the configured provider CLI exists. Never installs anything."""
    resolve = which or shutil.which
    if provider not in providers_mod.ADAPTERS:
        return PrerequisiteResult(
            name="provider",
            state="blocked",
            detail=f"unsupported agent provider `{provider}`; "
            f"supports: {', '.join(providers_mod.supported_providers())}",
            recovery="set `agent_provider` in `.ariadex/config.yaml` "
            "to a supported provider (or rerun `ariadex init`)",
        )
    executable = providers_mod.ADAPTERS[provider].launch_command[0]
    if resolve(executable) is None:
        return PrerequisiteResult(
            name="provider",
            state="blocked",
            detail=f"provider `{provider}` is not installed",
            recovery=PROVIDER_INSTALL_GUIDANCE[provider],
        )
    return PrerequisiteResult(name="provider", state="present", detail="provider ready")


def check_tmux(
    *,
    allow_install: bool = True,
    interactive: bool = False,
    find=None,
    detect_manager=None,
    ensure=None,
) -> PrerequisiteResult:
    """Verify tmux, preparing it through the fixed install path when needed.

    Missing tmux with installation disabled is `declined`; no supported
    package manager is `unsupported`; a failed install or failed
    post-install probe is `blocked`. Details name the package and the manual
    recovery command, never the internal install argv.
    """
    from . import tmux_setup as tmux_setup_mod

    find_tmux = find or tmux_setup_mod.find_tmux
    if find_tmux() is not None:
        return PrerequisiteResult(name="tmux", state="present", detail="tmux ready")
    manager = (
        detect_manager()
        if detect_manager is not None
        else tmux_setup_mod.detect_manager()
    )
    hint = tmux_setup_mod.manual_hint(manager)
    if not allow_install:
        return PrerequisiteResult(
            name="tmux",
            state="declined",
            detail="tmux is not installed and automatic preparation is disabled",
            recovery=f"install tmux manually with `{hint}`, then rerun",
        )
    if manager is None:
        return PrerequisiteResult(
            name="tmux",
            state="unsupported",
            detail="tmux is not installed and no supported package manager "
            "was detected",
            recovery=f"install tmux manually with `{hint}`, then rerun",
        )
    run_ensure = ensure or tmux_setup_mod.ensure_tmux
    try:
        run_ensure(interactive_sudo=interactive)
    except tmux_setup_mod.TmuxSetupError:
        return PrerequisiteResult(
            name="tmux",
            state="blocked",
            detail="tmux preparation failed and tmux is still unavailable",
            recovery=f"install the `tmux` package manually with `{hint}`, "
            "then rerun `ariadex start`",
        )
    if find_tmux() is None:
        return PrerequisiteResult(
            name="tmux",
            state="blocked",
            detail="tmux preparation reported success but tmux is still unavailable",
            recovery=f"install the `tmux` package manually with `{hint}`, "
            "then rerun `ariadex start`",
        )
    return PrerequisiteResult(name="tmux", state="installed", detail="tmux ready")


def check_widget(
    *,
    allow_install: bool = True,
    confirmed: bool = False,
    interactive: bool = False,
    prerequisites=None,
    prepare=None,
) -> PrerequisiteResult:
    """Verify desktop/Tkinter widget readiness, preparing Tkinter when asked.

    Unsupported desktops report `unsupported` (terminal controls remain the
    fallback). Missing Tkinter with installation disabled or unconfirmed is
    `declined`; a failed install or failed post-install verification is
    `blocked`. The result never claims a widget that cannot open.
    """
    from . import companion as companion_mod
    from . import deploy as deploy_mod

    if prerequisites is not None:
        current = prerequisites()
    else:
        current = deploy_mod.companion_prerequisites()
    desktop = current.get("desktop")
    session = getattr(desktop, "session", "?")
    supported = bool(getattr(desktop, "supported", False))
    if not supported:
        return PrerequisiteResult(
            name="widget",
            state="unsupported",
            detail=f"widget unavailable on `{session}`; terminal controls apply",
            recovery="use `ariadex pause` and `ariadex resume` "
            "instead of the floating widget",
        )
    display_ready = current.get("display_available")
    if display_ready is None:
        # Keep injected prerequisite fixtures backwards-compatible; the live
        # deploy probe always supplies this field.
        display_ready = True
    if not display_ready:
        return PrerequisiteResult(
            name="widget",
            state="unsupported",
            detail="widget unavailable: cannot connect to the desktop display",
            recovery="use terminal controls or repair the X11 display session, "
            "then rerun `ariadex start`",
        )
    probe = companion_mod.tkinter_available
    if current.get("tkinter_available"):
        return PrerequisiteResult(name="widget", state="present", detail="widget ready")
    if not allow_install or not confirmed:
        from . import tmux_setup as tmux_setup_mod

        hint = deploy_mod.tkinter_manual_hint(tmux_setup_mod.detect_manager())
        return PrerequisiteResult(
            name="widget",
            state="declined",
            detail="Tkinter is not installed and OS preparation is not confirmed",
            recovery=f"install it manually with `{hint}` or rerun with "
            "explicit confirmation, then rerun `ariadex start`",
        )
    run_prepare = prepare or deploy_mod.ensure_companion_dependencies
    outcome = run_prepare(
        allow_install=True, confirmed=True, interactive_sudo=interactive
    )
    if outcome.state == "installed" and probe():
        return PrerequisiteResult(
            name="widget", state="installed", detail="widget ready"
        )
    hint = deploy_mod.tkinter_manual_hint(None)
    return PrerequisiteResult(
        name="widget",
        state="blocked",
        detail=f"widget preparation failed: {outcome.detail}",
        recovery=f"install it manually with `{hint}`, then rerun `ariadex start`",
    )


def coordinate(
    provider: str,
    *,
    allow_install: bool = True,
    confirmed: bool = False,
    interactive: bool = False,
    require_widget: bool = False,
    version_info=None,
    yaml_available: bool | None = None,
    which=None,
    find_tmux=None,
    detect_manager=None,
    ensure_tmux=None,
    widget_prerequisites=None,
    prepare_widget=None,
) -> CoordinatorReport:
    """Run the readiness path in dependency order, stopping at first failure.

    Runtime, provider, tmux, then widget. Later prerequisites are never
    prepared after an earlier failure, so a failed run leaves no partial
    installation behind. Performs no daemon, tmux-session, provider, or
    widget startup itself. The widget gates overall readiness only when
    `require_widget` is true; otherwise its outcome is reported while
    managed execution may continue with terminal controls.
    """
    results: list[PrerequisiteResult] = []
    runtime = check_runtime(version_info=version_info, yaml_available=yaml_available)
    results.append(runtime)
    if not runtime.ready:
        return CoordinatorReport(results=results, ready=False)
    provider_result = check_provider(provider, which=which)
    results.append(provider_result)
    if not provider_result.ready:
        return CoordinatorReport(results=results, ready=False)
    tmux = check_tmux(
        allow_install=allow_install,
        interactive=interactive,
        find=find_tmux,
        detect_manager=detect_manager,
        ensure=ensure_tmux,
    )
    results.append(tmux)
    if not tmux.ready:
        return CoordinatorReport(results=results, ready=False)
    widget = check_widget(
        allow_install=allow_install,
        confirmed=confirmed,
        interactive=interactive,
        prerequisites=widget_prerequisites,
        prepare=prepare_widget,
    )
    results.append(widget)
    ready = widget.ready or not require_widget
    return CoordinatorReport(results=results, ready=ready)


def format_report(report: CoordinatorReport) -> str:
    """Render one line per prerequisite; successes stay terse and internal."""
    lines = ["prerequisites:"]
    for result in report.results:
        if result.ready:
            lines.append(f"  {result.name}: {result.detail}")
        else:
            lines.append(f"  {result.name}: {result.state} — {result.detail}")
            if result.recovery:
                lines.append(f"    recovery: {result.recovery}")
    lines.append(f"ready: {'yes' if report.ready else 'no'}")
    return "\n".join(lines)
