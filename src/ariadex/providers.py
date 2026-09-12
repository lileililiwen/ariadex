"""OpenCode and Codex adapters over the terminal driver.

Capability notes (declared, pending live-session verification because no
tmux server is available in this environment yet):
- OpenCode runs its attachable TUI by default (`opencode [project]`) and
  accepts `/new` as its new-session input, so `soft_reset` is declared.
- Codex runs its interactive CLI by default with no verified in-session
  new-session key, so `soft_reset` is NOT declared and the runner must use
  hard reset (terminate and restart) for it.
- Neither adapter can read provider token usage from the terminal pane, so
  `token_usage` is false and metrics must record `usage: unavailable`.
"""

from __future__ import annotations

from pathlib import Path

from .adapters import AgentAdapter, Capabilities, UnsupportedOperation
from .terminal import TerminalDriver

PROVIDER_OPENCODE = "opencode"
PROVIDER_CODEX = "codex"


class OpenCodeAdapter(AgentAdapter):
    provider_name = PROVIDER_OPENCODE
    launch_command = ("opencode",)
    new_session_input = "/new"

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
