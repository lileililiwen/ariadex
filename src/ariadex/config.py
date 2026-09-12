"""Project configuration: defaults, YAML loading, and validation.

Owns only configuration parsing. Adapters, terminal I/O, scheduling,
and verification belong to later changes.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml

from .providers import supported_providers

CONFIG_REL_PATH = Path(".ariadex") / "config.yaml"

RESET_MODES = ("soft", "hard", "auto")
CONTEXT_STRATEGIES = ("per-spec", "per-task", "token-threshold", "manual", "never")
BLOCKER_POLICIES = ("stop-on-blocker", "record-and-continue")

# Legacy values from earlier defaults, coerced with a warning.
LEGACY_CONTEXT_STRATEGIES = {"fresh-session": "per-spec"}
LEGACY_BLOCKER_POLICIES = {"record-and-stop": "stop-on-blocker"}

# Providers with an implemented adapter. Other values load successfully so
# that `ariadex run` can report them as unsupported instead of claiming
# progress. Single source of truth lives in providers.ADAPTERS.
SUPPORTED_PROVIDERS = supported_providers()
SUPPORTED_TERMINAL_DRIVERS = ("tmux",)


@dataclasses.dataclass
class Config:
    agent_provider: str = "opencode"
    terminal_driver: str = "tmux"
    context_strategy: str = "per-spec"
    reset_mode: str = "auto"
    spec_dir: str = "openspec/changes"
    handoff_file: str = "HANDOFF.md"
    verification_commands: list = dataclasses.field(default_factory=list)
    retry_limit: int = 2
    blocker_policy: str = "stop-on-blocker"
    log_retention_days: int = 30
    log_max_bytes: int = 10485760
    metrics_max_bytes: int = 5242880
    notifications_enabled: bool = False
    notification_command: list = dataclasses.field(default_factory=list)
    notification_webhook: str = ""
    notification_rate_limit: int = 5
    notification_window_seconds: int = 3600

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
# per-spec is the MVP default; manual and never never reset automatically.
context_strategy: per-spec
# Fresh-session reset strength for a completed spec: soft, hard, or auto.
reset_mode: auto
# Directory containing the active OpenSpec changes.
spec_dir: openspec/changes
# Durable handoff path: current spec, completed work, unresolved issues,
# blockers, pending decisions, next action, and next spec.
handoff_file: HANDOFF.md
# Shell commands that must pass before work is claimed complete.
verification_commands: []
# Maximum bounded retries for a failed operation. Must be >= 0.
retry_limit: 2
# How blockers are recorded: stop-on-blocker persists the blocker and
# stops new scheduling; record-and-continue persists it and continues.
blocker_policy: stop-on-blocker
# Local telemetry bounds: run logs under .ariadex/runs/ and metrics.jsonl.
# log_retention_days removes telemetry older than N days (0 keeps everything).
# log_max_bytes caps total run-log bytes; metrics_max_bytes caps the metrics
# file (0 disables that cap). Pruning never touches handoff history.
log_retention_days: 30
log_max_bytes: 10485760
metrics_max_bytes: 5242880
# Opt-in attention signals for blockers, verification failures, stale
# sessions, and verified completion. Disabled by default: stdout and local
# files stay authoritative. When enabled, redacted payloads go to the
# configured command (argv, payload JSON on stdin) and/or webhook URL;
# failures are recorded locally and never change scheduling. Rate limiting
# caps deliveries per attention key per window (0 delivers nothing).
notifications_enabled: false
notification_command: []
notification_webhook: ""
notification_rate_limit: 5
notification_window_seconds: 3600
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
    context_strategy = get("context_strategy", base.context_strategy)
    if context_strategy in LEGACY_CONTEXT_STRATEGIES:
        coerced = LEGACY_CONTEXT_STRATEGIES[context_strategy]
        print(
            f"warning: context_strategy `{context_strategy}` in {source} "
            f"is legacy; using `{coerced}`"
        )
        context_strategy = coerced
    if context_strategy not in CONTEXT_STRATEGIES:
        raise ConfigError(
            f"invalid context_strategy `{context_strategy}` in {source}: "
            f"expected one of {', '.join(CONTEXT_STRATEGIES)}"
        )
    blocker_policy = get("blocker_policy", base.blocker_policy)
    if blocker_policy in LEGACY_BLOCKER_POLICIES:
        coerced = LEGACY_BLOCKER_POLICIES[blocker_policy]
        print(
            f"warning: blocker_policy `{blocker_policy}` in {source} "
            f"is legacy; using `{coerced}`"
        )
        blocker_policy = coerced
    if blocker_policy not in BLOCKER_POLICIES:
        raise ConfigError(
            f"invalid blocker_policy `{blocker_policy}` in {source}: "
            f"expected one of {', '.join(BLOCKER_POLICIES)}"
        )
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
    for name in ("log_retention_days", "log_max_bytes", "metrics_max_bytes"):
        value = get(name, getattr(base, name))
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"invalid {name} in {source}: expected an integer >= 0")
        if value < 0:
            raise ConfigError(f"invalid {name} in {source}: expected an integer >= 0")
    notifications_enabled = get("notifications_enabled", base.notifications_enabled)
    if not isinstance(notifications_enabled, bool):
        raise ConfigError(
            f"invalid notifications_enabled in {source}: expected true or false"
        )
    notification_command = get("notification_command", base.notification_command)
    if not isinstance(notification_command, list) or not all(
        isinstance(item, str) for item in notification_command
    ):
        raise ConfigError(
            f"invalid notification_command in {source}: expected a list of strings"
        )
    notification_webhook = get("notification_webhook", base.notification_webhook)
    if not isinstance(notification_webhook, str):
        raise ConfigError(
            f"invalid notification_webhook in {source}: expected a URL string"
        )
    if notification_webhook and not notification_webhook.startswith(
        ("http://", "https://")
    ):
        raise ConfigError(
            f"invalid notification_webhook in {source}: "
            "expected an http(s) URL or an empty string"
        )
    for name in ("notification_rate_limit", "notification_window_seconds"):
        value = get(name, getattr(base, name))
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"invalid {name} in {source}: expected an integer >= 0")
        if value < 0:
            raise ConfigError(f"invalid {name} in {source}: expected an integer >= 0")
    return Config(
        agent_provider=raw.get("agent_provider", base.agent_provider),
        terminal_driver=raw.get("terminal_driver", base.terminal_driver),
        context_strategy=context_strategy,
        reset_mode=reset_mode,
        spec_dir=raw.get("spec_dir", base.spec_dir),
        handoff_file=raw.get("handoff_file", base.handoff_file),
        verification_commands=list(verification_commands),
        retry_limit=retry_limit,
        blocker_policy=blocker_policy,
        log_retention_days=get("log_retention_days", base.log_retention_days),
        log_max_bytes=get("log_max_bytes", base.log_max_bytes),
        metrics_max_bytes=get("metrics_max_bytes", base.metrics_max_bytes),
        notifications_enabled=notifications_enabled,
        notification_command=list(notification_command),
        notification_webhook=notification_webhook,
        notification_rate_limit=get(
            "notification_rate_limit", base.notification_rate_limit
        ),
        notification_window_seconds=get(
            "notification_window_seconds", base.notification_window_seconds
        ),
    )
