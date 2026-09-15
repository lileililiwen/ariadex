"""OpenCode, Codex, and CodeBuddy adapters over the terminal driver.

Capability notes (verified live by `ariadex evidence --only
opencode-lifecycle,codex-lifecycle`: real startup, `/help` probe,
interrupt, reset, termination, and restart in isolated tmux sessions):
- OpenCode runs its attachable TUI by default (`opencode [project]`) and
  accepts `/new` as its new-session input, so `soft_reset` is declared and
  automatic continuation uses that in-session operation.
- Codex runs its interactive CLI by default with no in-session
  new-session key, so `soft_reset` is NOT declared; automatic continuation
  uses the provider-safe hard reset (terminate and restart the same tmux
  session via the declared `codex` launch command).
- CodeBuddy shares the adapter boundary (`codebuddy` CLI) with the same
  conservative contract: no in-session new-session key is assumed, so
  `soft_reset` is NOT declared; automatic continuation uses the
  provider-safe hard reset (terminate and restart the same tmux session
  via the declared `codebuddy` launch command). Its ready markers are
  declared, not live-verified; the robot supervisor treats unknown
  surfaces as working, never as finished.
- No adapter can read provider token usage from the terminal pane, so
  `token_usage` is false and metrics must record `usage: unavailable`.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import diagnostics as diagnostics_mod
from . import provider_runtime
from .adapters import (
    AgentAdapter,
    Capabilities,
    InputSurface,
    StartupError,
    UnsupportedOperation,
)
from .terminal import TerminalDriver, TmuxDriver

PROVIDER_OPENCODE = "opencode"
PROVIDER_CODEX = "codex"
PROVIDER_CODEBUDDY = "codebuddy"


# Recoverable transport failures: the provider stops the current response
# but leaves its input surface usable. Quota, authentication, approval, and
# generic error markers never appear here; classification gives those
# precedence and requires a verified input-ready marker in the same capture.
RECOVERABLE_TERMINAL_ERROR_MARKERS: tuple[str, ...] = (
    "stream interrupted",
    "response interrupted",
    "connection reset",
    "connection error",
    "network error",
    "request timeout",
    "request timed out",
    "timed out",
    "deadline exceeded",
    "internal server error",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "server overloaded",
    "overloaded",
    "try again",
)


class OpenCodeAdapter(AgentAdapter):
    provider_name = PROVIDER_OPENCODE
    launch_command = ("opencode",)
    new_session_input = "/new"
    recoverable_error_markers = RECOVERABLE_TERMINAL_ERROR_MARKERS
    # Standard TUI confirm keystroke; sent only after a parsed request is
    # approved by the permission policy, never for unknown surfaces.
    permission_approve_input = "y"
    # Directory-access prompts render as a choice selector (Allow once /
    # Allow always / Reject with `select` + `enter` hints). Confirming with
    # Enter answers the focused choice (the single-grant option), never
    # types into the session; sent only after a parsed request is approved.
    permission_approve_keys = ("Enter",)
    # Verified `opencode --help`: `-m, --model provider/model`.
    model_option = "-m"
    ready_markers = ("Ask anything", "tab agents")

    def recognize_selector(self, capture_tail: str) -> bool:
        """True for the Allow once / Allow always / Reject choice surface."""
        try:
            lowered = "\n".join((capture_tail or "").splitlines()[-16:]).lower()
        except Exception:
            return False
        return "allow once" in lowered and "allow always" in lowered

    def input_surface(self, capture: str) -> InputSurface:
        """Recognize OpenCode's current composer, independent of answer text.

        OpenCode's TUI 1.18.x no longer renders the old ``Ask anything``
        prompt. Its idle composer is rendered as a blank ``┃`` line followed
        by the provider footer. This deliberately requires both UI-owned
        structures and never examines the assistant's response prose.
        The composer status bar (``┃ <model info>`` directly above the
        ``╹`` bottom border) is window chrome, not user draft text, and is
        excluded from draft detection so an idle composer is not mistaken
        for a human-held draft.
        """
        lines = [line.rstrip() for line in (capture or "").splitlines()[-16:]]
        has_composer = any(line.strip() == "┃" for line in lines)
        has_footer = any(
            line.strip().startswith("▣") and "Build" in line for line in lines
        )
        border_idx = max(
            (idx for idx, line in enumerate(lines) if line.strip().startswith("╹")),
            default=None,
        )
        has_draft = any(
            line.strip().startswith("┃")
            and line.strip() != "┃"
            and not self._is_status_bar(lines, idx, border_idx, has_footer)
            for idx, line in enumerate(lines)
        )
        if has_draft:
            return InputSurface.DRAFT
        if has_composer and has_footer:
            return InputSurface.EMPTY
        return super().input_surface(capture)

    @staticmethod
    def _is_status_bar(
        lines: list[str], idx: int, border_idx: int | None, has_footer: bool
    ) -> bool:
        """True for the composer status bar, never for user draft text.

        The status bar is the ``┃``-prefixed line directly above the
        composer bottom border carrying ``·``-separated model info while
        the provider footer is visible. A genuine draft sits above the
        status line, so position plus shape plus footer context keep a
        real draft from ever being excluded.
        """
        if border_idx is None or not has_footer:
            return False
        if idx != border_idx - 1:
            return False
        stripped = lines[idx].strip()
        return stripped.startswith("┃") and stripped != "┃" and "·" in stripped

    @property
    def api_port(self) -> int:
        digest = hashlib.sha256(str(Path(self.workdir).resolve()).encode()).digest()
        return 43000 + int.from_bytes(digest[:2], "big") % 1000

    @property
    def provider_state_required(self) -> bool:
        return isinstance(self.driver, TmuxDriver)

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"

    def start(self) -> str:
        """Start normally, or attach when the OpenCode backend survived UI loss."""
        project_dir = Path(self.workdir)
        record = provider_runtime.read_record(project_dir)
        recovered_process = provider_runtime.find_process(self.api_port, project_dir)
        endpoint = f"{self.endpoint}/session/status"
        reusable = provider_runtime.is_reusable(project_dir, record)
        if reusable:
            command = [*self.launch_command, "attach", self.endpoint]
            reused = True
        else:
            endpoint_responsive = provider_runtime.endpoint_is_responsive(endpoint)
            if recovered_process is not None and endpoint_responsive:
                if record is None:
                    record = self._runtime_record(recovered_process)
                    provider_runtime.write_record(project_dir, record)
                command = [*self.launch_command, "attach", self.endpoint]
                reused = True
            elif record is not None:
                provider_runtime.terminate_owned(project_dir, record)
                provider_runtime.clear_record(project_dir)
                command = self.launch_command_for_provider()
                reused = False
            elif endpoint_responsive:
                raise StartupError(
                    f"{self.provider_name} startup refused: ownership conflict "
                    f"at {endpoint}"
                )
            else:
                command = self.launch_command_for_provider()
                reused = False
        try:
            diagnostics_mod.record_operation(
                project_dir,
                "provider-start",
                phase="before",
                provider=self.provider_name,
                session=self.session_name,
                details={"command": " ".join(command), "reused": reused},
            )
            result = self.driver.create_or_connect(
                self.session_name, self.workdir, command
            )
        except Exception as exc:
            diagnostics_mod.record_operation(
                project_dir,
                "provider-start",
                phase="after",
                result="failed",
                provider=self.provider_name,
                session=self.session_name,
                details={"error": str(exc)},
            )
            raise StartupError(f"{self.provider_name} startup failed: {exc}") from exc
        diagnostics_mod.record_operation(
            project_dir,
            "provider-start",
            phase="after",
            result="succeeded",
            provider=self.provider_name,
            session=self.session_name,
            details={"result": result, "reused": reused},
        )
        if isinstance(self.driver, TmuxDriver) and not reused:
            process = provider_runtime.find_process(self.api_port, project_dir)
            if process is None:
                pid = self.driver.session_pid(self.session_name)
                if pid is not None:
                    with contextlib.suppress(OSError, ValueError):
                        process = provider_runtime.process_identity(pid)
            if process is not None:
                provider_runtime.write_record(
                    project_dir, self._runtime_record(process)
                )
        return result

    def _runtime_record(
        self, process: tuple[int, int]
    ) -> provider_runtime.ProviderRuntimeRecord:
        return provider_runtime.ProviderRuntimeRecord(
            provider=self.provider_name,
            project=str(Path(self.workdir).resolve()),
            session_id=self.session_name.removeprefix("ariadex-"),
            tmux_session=self.session_name,
            endpoint=f"{self.endpoint}/session/status",
            port=self.api_port,
            pid=process[0],
            process_start_ticks=process[1],
            generation=uuid.uuid4().hex,
        )

    def terminate(self) -> None:
        project_dir = Path(self.workdir)
        record = provider_runtime.read_record(project_dir)
        details = {
            "pid": record.pid if record else None,
            "process_start_ticks": record.process_start_ticks if record else None,
            "generation": record.generation if record else "",
        }
        diagnostics_mod.record_operation(
            project_dir,
            "provider-terminate",
            phase="before",
            provider=self.provider_name,
            session=self.session_name,
            details=details,
        )
        try:
            super().terminate()
        except Exception as exc:
            diagnostics_mod.record_operation(
                project_dir,
                "provider-terminate",
                phase="after",
                result="failed",
                provider=self.provider_name,
                session=self.session_name,
                details={**details, "error": str(exc)},
            )
            raise
        if record is not None:
            owned_result = provider_runtime.terminate_owned(project_dir, record)
            provider_runtime.clear_record(project_dir)
            details["owned_process_signal_result"] = owned_result
        diagnostics_mod.record_operation(
            project_dir,
            "provider-terminate",
            phase="after",
            result="succeeded",
            provider=self.provider_name,
            session=self.session_name,
            details=details,
        )

    def launch_command_for_provider(self) -> list[str]:
        return [
            *super().launch_command_for_provider(),
            "--port",
            str(self.api_port),
        ]

    def provider_state(self) -> str | None:
        """Read OpenCode session state without inspecting pane text."""
        if not isinstance(self.driver, TmuxDriver):
            return None
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{self.api_port}/session/status",
                timeout=0.75,
            ) as response:
                payload = json.load(response)
        except (OSError, ValueError, urllib.error.URLError):
            return None
        if not isinstance(payload, dict):
            return None
        statuses = []
        for raw in payload.values():
            if not isinstance(raw, dict):
                continue
            value = str(raw.get("type", raw.get("status", ""))).lower()
            if value in {"busy", "active", "working"}:
                statuses.append("active")
            elif value in {"retry", "waiting"}:
                statuses.append("retry")
            elif value == "error":
                statuses.append("error")
            elif value == "idle":
                statuses.append("idle")
        if not statuses:
            return "idle"
        if "error" in statuses:
            return "error"
        if "retry" in statuses:
            return "retry"
        if "active" in statuses:
            return "active"
        return "idle"

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
            model_switch=True,
        )


class CodexAdapter(AgentAdapter):
    provider_name = PROVIDER_CODEX
    launch_command = ("codex",)
    new_session_input = None
    recoverable_error_markers = RECOVERABLE_TERMINAL_ERROR_MARKERS
    # Standard TUI confirm keystroke; sent only after a parsed request is
    # approved by the permission policy, never for unknown surfaces.
    permission_approve_input = "y"
    # Verified `codex --help`: `-m, --model <MODEL>`.
    model_option = "-m"
    ready_markers = ("OpenAI Codex", "Ask Codex to do anything")

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            interactive=True,
            soft_reset=False,
            hard_reset=True,
            token_usage=False,
            structured_output=False,
            interrupt=True,
            manual_takeover=True,
            model_switch=True,
        )


class CodeBuddyAdapter(AgentAdapter):
    provider_name = PROVIDER_CODEBUDDY
    launch_command = ("codebuddy",)
    new_session_input = None
    recoverable_error_markers = RECOVERABLE_TERMINAL_ERROR_MARKERS
    # Standard TUI confirm keystroke; sent only after a parsed request is
    # approved by the permission policy, never for unknown surfaces.
    permission_approve_input = "y"
    # Verified `codebuddy --help`: `--model <model>` (model ID).
    model_option = "--model"
    ready_markers = ("CodeBuddy", "codebuddy")

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(
            interactive=True,
            soft_reset=False,
            hard_reset=True,
            token_usage=False,
            structured_output=False,
            interrupt=True,
            manual_takeover=True,
            model_switch=True,
        )


ADAPTERS: dict[str, type[AgentAdapter]] = {
    PROVIDER_OPENCODE: OpenCodeAdapter,
    PROVIDER_CODEX: CodexAdapter,
    PROVIDER_CODEBUDDY: CodeBuddyAdapter,
}


def supported_providers() -> tuple[str, ...]:
    return tuple(ADAPTERS)


def get_adapter(
    provider: str,
    driver: TerminalDriver,
    session_name: str,
    workdir: Path | str,
) -> AgentAdapter:
    """Build the adapter for `provider` or report it as unsupported."""
    try:
        adapter_cls = ADAPTERS[provider]
    except KeyError:
        raise UnsupportedOperation(
            f"unsupported agent provider `{provider}`; "
            f"MVP supports: {', '.join(supported_providers())}"
        ) from None
    return adapter_cls(driver, session_name, workdir)
