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

import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path

from .adapters import AgentAdapter, Capabilities, UnsupportedOperation
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
    ready_markers = ("Ask anything", "tab agents")

    def is_input_ready(self, capture: str) -> bool:
        """Recognize OpenCode's current composer, independent of answer text.

        OpenCode's TUI 1.18.x no longer renders the old ``Ask anything``
        prompt. Its idle composer is rendered as a blank ``┃`` line followed
        by the provider footer. This deliberately requires both UI-owned
        structures and never examines the assistant's response prose.
        """
        lines = [line.rstrip() for line in (capture or "").splitlines()[-16:]]
        has_composer = any(line.strip() == "┃" for line in lines)
        has_footer = any(
            line.strip().startswith("▣") and "Build" in line for line in lines
        )
        return (has_composer and has_footer) or super().is_input_ready(capture)

    @property
    def api_port(self) -> int:
        digest = hashlib.sha256(str(Path(self.workdir).resolve()).encode()).digest()
        return 43000 + int.from_bytes(digest[:2], "big") % 1000

    @property
    def provider_state_required(self) -> bool:
        return isinstance(self.driver, TmuxDriver)

    def launch_command_for_provider(self) -> list[str]:
        return [*self.launch_command, "--port", str(self.api_port)]

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
        )


class CodexAdapter(AgentAdapter):
    provider_name = PROVIDER_CODEX
    launch_command = ("codex",)
    new_session_input = None
    recoverable_error_markers = RECOVERABLE_TERMINAL_ERROR_MARKERS
    # Standard TUI confirm keystroke; sent only after a parsed request is
    # approved by the permission policy, never for unknown surfaces.
    permission_approve_input = "y"
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
        )


class CodeBuddyAdapter(AgentAdapter):
    provider_name = PROVIDER_CODEBUDDY
    launch_command = ("codebuddy",)
    new_session_input = None
    recoverable_error_markers = RECOVERABLE_TERMINAL_ERROR_MARKERS
    # Standard TUI confirm keystroke; sent only after a parsed request is
    # approved by the permission policy, never for unknown surfaces.
    permission_approve_input = "y"
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
