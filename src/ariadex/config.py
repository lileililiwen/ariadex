"""Project configuration: defaults, YAML loading, and validation.

Owns only configuration parsing. Adapters, terminal I/O, scheduling,
and verification belong to later changes.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml

CONFIG_REL_PATH = Path(".ariadex") / "config.yaml"

RESET_MODES = ("soft", "hard", "auto")

# Providers with a planned MVP adapter. Other values load successfully so
# that `ariadex run` can report them as unsupported instead of claiming
# progress. (agent-adapters-and-tmux-driver implements the adapters.)
SUPPORTED_PROVIDERS = ("opencode", "codex")
SUPPORTED_TERMINAL_DRIVERS = ("tmux",)


@dataclasses.dataclass
class Config:
    agent_provider: str = "opencode"
    terminal_driver: str = "tmux"
    context_strategy: str = "fresh-session"
    reset_mode: str = "auto"
    spec_dir: str = "openspec/changes"
    handoff_file: str = ".ariadex/handoff.md"
    verification_commands: list = dataclasses.field(default_factory=list)
    retry_limit: int = 2
    blocker_policy: str = "record-and-stop"

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class ConfigError(Exception):
    """Raised when configuration is missing, unreadable, or invalid."""


def default_config_text() -> str:
    return """\
# Ariadex project configuration.
# Created by `ariadex init`. Unknown keys are reported as warnings and ignored.
# Invalid enum values, missing required paths, and negative retry limits
# fail before any execution run starts.

# Coding CLI provider. MVP adapters: opencode, codex.
# Other values load successfully; `ariadex run` reports them as unsupported.
agent_provider: opencode
# Terminal transport. MVP driver: tmux.
terminal_driver: tmux
# How a fresh session recovers context. Durable state lives in the
# repository, specs, and handoff file; conversation history is temporary.
context_strategy: fresh-session
# Fresh-session reset strength for a completed spec: soft, hard, or auto.
reset_mode: auto
# Directory containing the active OpenSpec changes.
spec_dir: openspec/changes
# Durable handoff path: current spec, completed work, unresolved issues,
# blockers, pending decisions, next action, and next spec.
handoff_file: .ariadex/handoff.md
# Shell commands that must pass before work is claimed complete.
verification_commands: []
# Maximum bounded retries for a failed operation. Must be >= 0.
retry_limit: 2
# How blockers are recorded: record-and-stop preserves unresolved work.
blocker_policy: record-and-stop
"""


def defaults() -> Config:
    return Config()


def config_path(project_dir: Path) -> Path:
    return project_dir / CONFIG_REL_PATH


def load(project_dir: Path) -> Config:
    """Load and validate configuration. Raises ConfigError on any problem."""
    path = config_path(project_dir)
    if not path.is_file():
        raise ConfigError(
            f"missing configuration at {CONFIG_REL_PATH}; run `ariadex init` first"
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {CONFIG_REL_PATH}: {exc}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(
            f"invalid configuration in {CONFIG_REL_PATH}: top-level mapping required"
        )
    return validate(raw, source=str(CONFIG_REL_PATH))


def validate(raw: dict, source: str = "configuration") -> Config:
    known = {field.name for field in dataclasses.fields(Config)}
    unknown = sorted(set(raw) - known)
    for key in unknown:
        print(f"warning: unknown configuration key `{key}` in {source}; ignoring")

    def get(name: str, default):
        value = raw.get(name, default)
        return value

    base = defaults()
    reset_mode = get("reset_mode", base.reset_mode)
    if reset_mode not in RESET_MODES:
        raise ConfigError(
            f"invalid reset_mode `{reset_mode}` in {source}: "
            f"expected one of {', '.join(RESET_MODES)}"
        )
    retry_limit = get("retry_limit", base.retry_limit)
    if isinstance(retry_limit, bool) or not isinstance(retry_limit, int):
        raise ConfigError(
            f"invalid retry_limit `{retry_limit}` in {source}: expected an integer >= 0"
        )
    if retry_limit < 0:
        raise ConfigError(
            f"invalid retry_limit `{retry_limit}` in {source}: expected an integer >= 0"
        )
    verification_commands = get("verification_commands", base.verification_commands)
    if not isinstance(verification_commands, list) or not all(
        isinstance(item, str) for item in verification_commands
    ):
        raise ConfigError(
            f"invalid verification_commands in {source}: expected a list of strings"
        )
    for name in (
        "agent_provider",
        "terminal_driver",
        "context_strategy",
        "spec_dir",
        "handoff_file",
        "blocker_policy",
    ):
        value = get(name, getattr(base, name))
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(
                f"invalid {name} in {source}: a non-empty path or name is required"
            )
    return Config(
        agent_provider=raw.get("agent_provider", base.agent_provider),
        terminal_driver=raw.get("terminal_driver", base.terminal_driver),
        context_strategy=raw.get("context_strategy", base.context_strategy),
        reset_mode=reset_mode,
        spec_dir=raw.get("spec_dir", base.spec_dir),
        handoff_file=raw.get("handoff_file", base.handoff_file),
        verification_commands=list(verification_commands),
        retry_limit=retry_limit,
        blocker_policy=raw.get("blocker_policy", base.blocker_policy),
    )
