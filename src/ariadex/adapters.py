"""Provider-neutral agent lifecycle contract and capability model.

`AgentAdapter` owns provider command construction and lifecycle mapping:
start, send, interrupt, new session, output capture, idle detection, and
terminate. It never embeds terminal transport details (those belong to
`TerminalDriver`) and never calls an LLM API.
"""

from __future__ import annotations

import abc
import dataclasses
import enum
from pathlib import Path

from . import terminal as terminal_mod


@dataclasses.dataclass(frozen=True)
class Capabilities:
    """Inspectable adapter capabilities consumed by the runner."""

    interactive: bool = True
    soft_reset: bool = False
    hard_reset: bool = True
    token_usage: bool = False
    structured_output: bool = False
    interrupt: bool = True
    manual_takeover: bool = True
    model_switch: bool = False


class InputSurface(enum.StrEnum):
    """Provider-neutral current input surface classification."""

    EMPTY = "empty"
    DRAFT = "draft"
    BUSY = "busy"
    APPROVAL = "approval"
    UNKNOWN = "unknown"


class AdapterError(Exception):
    """Base class for typed adapter failures."""


class UnsupportedOperation(AdapterError):
    """The adapter explicitly does not support the requested operation."""


class StartupError(AdapterError):
    """Provider startup failed."""


class TransportError(AdapterError):
    """Input delivery to a running provider failed."""


class CaptureError(AdapterError):
    """Output capture from a running provider failed."""


class TerminationError(AdapterError):
    """Provider termination failed."""


def select_reset(reset_mode: str, capabilities: Capabilities) -> str:
    """Choose `soft` or `hard` reset from declared capabilities.

    `auto` selects the strongest supported operation, preferring soft reset
    when available. Raises UnsupportedOperation when the requested strength
    is not declared.
    """
    if reset_mode == "soft":
        if not capabilities.soft_reset:
            raise UnsupportedOperation("adapter lacks `soft_reset` capability")
        return "soft"
    if reset_mode == "hard":
        if not capabilities.hard_reset:
            raise UnsupportedOperation("adapter lacks `hard_reset` capability")
        return "hard"
    if reset_mode == "auto":
        if capabilities.soft_reset:
            return "soft"
        if capabilities.hard_reset:
            return "hard"
        raise UnsupportedOperation(
            "adapter declares neither `soft_reset` nor `hard_reset`"
        )
    raise AdapterError(
        f"invalid reset mode `{reset_mode}`: expected soft, hard, or auto"
    )


class AgentAdapter(abc.ABC):
    """One lifecycle contract implemented per Coding CLI provider."""

    provider_name: str = "unknown"
    launch_command: tuple[str, ...] = ()
    new_session_input: str | None = None
    #: Recognized recoverable terminal-error markers for this provider.
    #: A surface containing one of these markers is a recoverable
    #: conversation boundary only when the same capture also contains a
    #: verified input-ready marker; otherwise it stays a generic error.
    recoverable_error_markers: tuple[str, ...] = ()
    #: Provider-owned permission-response keystroke, sent only after a
    #: parsed request is approved by the permission policy. None means the
    #: provider surface is not understood: approvals always wait for a
    #: human and the watcher never sends input for them.
    permission_approve_input: str | None = None
    #: Provider-owned permission-selector key sequence (ordered terminal
    #: key names such as `"Enter"`), sent only after a parsed request is
    #: approved and the live surface is a choice selector. None means the
    #: provider has no selector surface: approvals use the text keystroke.
    permission_approve_keys: tuple[str, ...] | None = None
    #: Provider-owned CLI option that selects the model for a fresh start
    #: (for example `"--model"` or `"-m"`). None means the provider has no
    #: verified model-selection flag and `switch_model` stays unsupported.
    model_option: str | None = None
    #: Provider-owned legacy terminal markers used by the adapter when no
    #: richer provider status channel is available.
    ready_markers: tuple[str, ...] = ()

    def __init__(
        self,
        driver: terminal_mod.TerminalDriver,
        session_name: str,
        workdir: Path | str,
    ) -> None:
        self.driver = driver
        self.session_name = session_name
        self.workdir = workdir
        #: Model selected via `switch_model`; applied to subsequent starts.
        self.model_override: str | None = None

    @property
    @abc.abstractmethod
    def capabilities(self) -> Capabilities:
        """Declared capabilities; the runner must consult these."""

    def start(self) -> str:
        """Create or connect the session and launch the provider.

        Returns `created` or `connected`. Wraps driver failures so callers
        only handle AdapterError.
        """
        try:
            return self.driver.create_or_connect(
                self.session_name,
                self.workdir,
                self.launch_command_for_provider(),
            )
        except terminal_mod.TerminalError as exc:
            raise StartupError(f"{self.provider_name} startup failed: {exc}") from exc

    def launch_command_for_provider(self) -> list[str]:
        command = list(self.launch_command)
        if self.model_override is not None and self.model_option is not None:
            command.extend([self.model_option, self.model_override])
        return command

    def switch_model(self, target: str) -> None:
        """Restart the provider session under a different model.

        Applies `target` to subsequent starts via the provider-owned
        `model_option` flag, then restarts the owned session so the new
        model takes effect immediately. Raises UnsupportedOperation when
        the adapter declares no `model_switch` capability or verified
        flag; transport/termination/startup failures propagate as typed
        AdapterError and must fail closed.
        """
        if not self.capabilities.model_switch or self.model_option is None:
            raise UnsupportedOperation(
                f"{self.provider_name} has no automatic model-switch "
                "operation; switch the model manually"
            )
        if not target.strip():
            raise AdapterError("model-switch target must not be empty")
        self.model_override = target.strip()
        self.terminate()
        self.start()

    def send(self, text: str) -> None:
        try:
            self.driver.send_input(self.session_name, text)
        except terminal_mod.TmuxNotAvailable as exc:
            raise TransportError(str(exc)) from exc
        except terminal_mod.SessionMissing as exc:
            raise TransportError(str(exc)) from exc
        except terminal_mod.TerminalError as exc:
            raise TransportError(
                f"failed to deliver input to {self.provider_name}: {exc}"
            ) from exc

    def send_keys(self, keys: list[str] | tuple[str, ...]) -> None:
        """Deliver named keys to the session (selector confirmations only)."""
        try:
            self.driver.send_keys(self.session_name, list(keys))
        except terminal_mod.TmuxNotAvailable as exc:
            raise TransportError(str(exc)) from exc
        except terminal_mod.SessionMissing as exc:
            raise TransportError(str(exc)) from exc
        except terminal_mod.TerminalError as exc:
            raise TransportError(
                f"failed to deliver keys to {self.provider_name}: {exc}"
            ) from exc

    def interrupt(self) -> None:
        if not self.capabilities.interrupt:
            raise UnsupportedOperation(
                f"{self.provider_name} lacks `interrupt` capability"
            )
        try:
            self.driver.interrupt(self.session_name)
        except terminal_mod.TerminalError as exc:
            raise TransportError(
                f"failed to interrupt {self.provider_name}: {exc}"
            ) from exc

    def new_session(self) -> None:
        """Soft reset via the provider's new-session input.

        Reports the missing capability so the runner can fall back to hard
        reset (terminate and restart) instead of assuming `/new` works.
        """
        if not self.capabilities.soft_reset or self.new_session_input is None:
            raise UnsupportedOperation(
                f"{self.provider_name} lacks `soft_reset` capability; "
                "use hard reset (terminate and restart)"
            )
        try:
            self.driver.send_input(self.session_name, self.new_session_input)
        except terminal_mod.TerminalError as exc:
            raise TransportError(
                f"failed to reset {self.provider_name} session: {exc}"
            ) from exc

    @property
    def auto_continuation_available(self) -> bool:
        """Whether this adapter can open a fresh conversation automatically."""
        if self.capabilities.soft_reset and self.new_session_input is not None:
            return True
        return bool(self.capabilities.hard_reset)

    def new_conversation(self) -> None:
        """Open a fresh conversation automatically (provider-safe).

        Prefers the in-session new-session input when the adapter declares
        `soft_reset`; otherwise performs a provider-safe terminate/restart
        of the same session via the declared `launch_command` when the
        adapter declares `hard_reset`. Raises UnsupportedOperation when
        neither path is available so the caller fails closed instead of
        claiming continuation. Transport/termination/startup failures
        propagate as typed AdapterError and must also fail closed.
        """
        if self.capabilities.soft_reset and self.new_session_input is not None:
            self.new_session()
            return
        if self.capabilities.hard_reset:
            self.terminate()
            self.start()
            return
        raise UnsupportedOperation(
            f"{self.provider_name} has no automatic new-conversation "
            "operation; open a new conversation manually"
        )

    def capture_output(self) -> str:
        """Return raw pane output verbatim for the logger.

        Never interprets provider text as completion.
        """
        try:
            return self.driver.capture(self.session_name)
        except terminal_mod.TerminalError as exc:
            raise CaptureError(
                f"failed to capture {self.provider_name} output: {exc}"
            ) from exc

    def is_input_ready(self, capture: str) -> bool:
        """Return whether this provider exposes an input-ready surface.

        This is adapter state recognition, never interpretation of the
        model's answer. Providers with a machine-readable status channel may
        override this method; terminal-only providers may use their own
        stable UI surface.
        """
        return self.input_surface(capture) is InputSurface.EMPTY

    def input_surface(self, capture: str) -> InputSurface:
        """Classify the provider-owned composer without provider branching."""
        lowered = "\n".join((capture or "").splitlines()[-16:]).lower()
        if bool(self.ready_markers) and any(
            marker.lower() in lowered for marker in self.ready_markers
        ):
            return InputSurface.EMPTY
        return InputSurface.UNKNOWN

    def provider_state(self) -> str | None:
        """Return provider lifecycle state when a machine status API exists."""
        return None

    @property
    def provider_state_required(self) -> bool:
        return False

    def recognize_permission(self, capture_tail: str):
        """Parse one permission request from a provider pane tail.

        Adapter-owned recognition: returns a ParsedRequest with the
        canonical file operation and single unambiguous path, or None
        when the surface is unknown or ambiguous. Never raises for
        provider text; unparsable surfaces stay waiting for a human.
        """
        from . import permissions as permissions_mod

        try:
            return permissions_mod.parse_permission_request(capture_tail)
        except Exception:
            return None

    def recognize_selector(self, capture_tail: str) -> bool:
        """True when the live approval surface is a choice selector.

        Choice selectors (Allow once / Allow always / Reject style) need
        the adapter-owned key sequence instead of the text keystroke.
        The base implementation reports no selector; providers with a
        verified selector surface override it. Never raises.
        """
        return False

    def is_idle(self) -> bool:
        """Conservative default: never claim idle without evidence."""
        return False

    def get_usage(self) -> dict | None:
        """Provider token/cost usage, or None when not exposed.

        Metrics must record `usage: unavailable` in that case and never
        invent an estimate.
        """
        return None

    def terminate(self) -> None:
        try:
            self.driver.terminate(self.session_name)
        except terminal_mod.TerminalError as exc:
            raise TerminationError(
                f"failed to terminate {self.provider_name}: {exc}"
            ) from exc
