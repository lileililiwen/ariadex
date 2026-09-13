"""OpenSpec-authoritative current-spec lifecycle evidence.

The managed watcher must tie every provider conversation to the OpenSpec
change it works on. This module is the only place that executes the
``openspec`` CLI for lifecycle decisions:

- Commands run with an argument array (no shell), a bounded timeout, and
  truncated output. Missing binaries, timeouts, non-zero exits, and
  malformed JSON become a typed ``EvidenceBlocked`` with the exact
  operator-readable reason, never a completion claim.
- ``openspec list --json`` is the authoritative active queue (including
  per-change task progress). A resolved ``root.source`` other than
  ``nearest`` means the project directory is not inside an OpenSpec
  repository; callers fall back to the legacy internal discovery instead
  of blocking non-OpenSpec projects.
- Before any first, continuation, or confirmation prompt is sent, the
  selected change is recorded atomically as a versioned conversation
  record under ``.ariadex/`` and ``HANDOFF.current_spec`` /
  ``current_spec_file`` are synchronized without touching completed or
  unresolved history. Crash recovery reads the record and never infers
  a target from a stale ``next_action``.
- After task completion, archival is proven by active-list absence plus
  an archived change directory with the recorded name suffix, canonical
  spec presence, and strict spec validation. Anything contradictory or
  unavailable blocks with the exact reason and sends no prompt.

Standard library only; command execution is injectable for tests.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import handoff as handoff_mod
from .logging import redact

#: Durable conversation identity, scoped to one project.
CONVERSATION_FILENAME = "conversation.json"
CONVERSATION_VERSION = 1

#: Prompt roles that require a recorded conversation target first.
CONVERSATION_ROLES = ("first", "continuation", "confirmation")

#: Bounded OpenSpec execution (seconds) so a hung CLI cannot stall a cycle.
COMMAND_TIMEOUT_S = 30.0

#: Truncation bound for captured CLI output (bytes of text).
MAX_OUTPUT_CHARS = 32_000

#: Archive storage checked for recorded-name suffix proof.
ARCHIVE_DIRNAME = "archive"

#: Repository marker resolved upward like the CLI `nearest` root.
ROOT_MARKER = "openspec"

#: Upward search bound for the repository marker.
ROOT_SEARCH_LIMIT = 32


class EvidenceBlocked(Exception):
    """OpenSpec evidence is unavailable or contradictory (fail-closed)."""


class NotOpenSpecRoot(Exception):
    """The project directory is not inside an OpenSpec repository."""


class ConversationError(Exception):
    """The durable conversation record is malformed and untrusted."""


@dataclasses.dataclass
class ChangeProgress:
    """Authoritative per-change task progress from `openspec list`."""

    name: str = ""
    completed: int = 0
    total: int = 0

    @property
    def open_tasks(self) -> int:
        """Unchecked tasks (never negative on validated payloads)."""
        return max(self.total - self.completed, 0)


@dataclasses.dataclass
class ChangeList:
    """Authoritative active queue (sorted names, progress by name)."""

    order: list[str] = dataclasses.field(default_factory=list)
    entries: dict[str, ChangeProgress] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ChangeStatus:
    """`openspec status` outcome for one recorded change."""

    found: bool = False
    is_complete: bool = False


@dataclasses.dataclass
class ConversationRecord:
    """Durable identity of the conversation a prompt was sent into."""

    version: int = CONVERSATION_VERSION
    conversation_id: str = ""
    role: str = ""
    current_spec: str = ""
    spec_path: str = ""
    started_at: str = ""
    queue: list[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def now_iso() -> str:
    """Current UTC time in seconds-precision ISO format."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_conversation_id() -> str:
    """Fresh conversation identity (never reused across prompts)."""
    return f"c-{uuid.uuid4().hex[:12]}"


def conversation_path(project_dir: Path) -> Path:
    """Project-scoped durable record location (never leaves `.ariadex/`)."""
    return project_dir / ".ariadex" / CONVERSATION_FILENAME


def find_openspec_root(start: Path) -> Path | None:
    """Nearest ancestor (or self) containing the `openspec/` marker.

    Mirrors the CLI `nearest` resolution without spawning a process so
    non-OpenSpec projects fall back to internal discovery cheaply. A
    found marker still defers to CLI JSON as the authority.
    """
    try:
        current = start.resolve()
    except OSError:
        return None
    for _ in range(ROOT_SEARCH_LIMIT):
        try:
            if (current / ROOT_MARKER).is_dir():
                return current
        except OSError:
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None


def require_root(project_dir: Path) -> None:
    """Raise ``NotOpenSpecRoot`` when no repository marker resolves."""
    if find_openspec_root(project_dir) is None:
        raise NotOpenSpecRoot(
            "project directory is not inside an OpenSpec repository; "
            "using internal discovery"
        )


def _truncate(text: str) -> str:
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + "…[truncated]"
    return text


def run_openspec(
    project_dir: Path,
    args: list[str],
    timeout: float = COMMAND_TIMEOUT_S,
    runner: Callable[..., Any] | None = None,
) -> str:
    """Run one `openspec` command and return its stdout text.

    Execution uses an argument array (no shell) with a bounded timeout.
    Raises ``EvidenceBlocked`` for a missing binary, timeout, transport
    failure, or non-zero exit (with bounded redacted diagnostics), and
    ``NotOpenSpecRoot`` when the CLI reports no resolvable repository.
    """
    argv = ["openspec", *args]
    invoke = runner if runner is not None else subprocess.run
    try:
        proc = invoke(
            argv,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise EvidenceBlocked(
            "openspec CLI not available on PATH; "
            "install it to use OpenSpec-backed scheduling "
            f"(`npm install -g @fission-ai/openspec`): {exc}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise EvidenceBlocked(
            f"openspec command timed out after {timeout:g}s "
            f"(`{' '.join(argv)}`); no completion claimed"
        ) from exc
    except OSError as exc:
        raise EvidenceBlocked(
            f"openspec command failed to execute "
            f"(`{' '.join(argv)}`): {exc}; no completion claimed"
        ) from exc
    stdout = _truncate(proc.stdout or "")
    stderr = _truncate(proc.stderr or "")
    if proc.returncode != 0:
        detail = redact(stderr or stdout or "unknown openspec error")
        lowered = detail.lower()
        if "filesystem.access" in lowered or "notfound" in lowered:
            raise NotOpenSpecRoot(
                "project directory is not inside an OpenSpec repository; "
                "using internal discovery"
            )
        raise EvidenceBlocked(
            f"openspec command failed (exit {proc.returncode}, "
            f"`{' '.join(argv)}`): {detail}; no completion claimed"
        )
    return stdout


def _payload(stdout: str, command: str) -> dict[str, Any]:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise EvidenceBlocked(
            f"openspec `{command}` returned malformed JSON: {exc}; "
            "no completion claimed"
        ) from exc
    if not isinstance(data, dict):
        raise EvidenceBlocked(
            f"openspec `{command}` returned a non-object payload; no completion claimed"
        )
    return data


def _check_root_source(data: dict[str, Any]) -> None:
    root = data.get("root", {})
    source = root.get("source") if isinstance(root, dict) else None
    if source is not None and source != "nearest":
        raise NotOpenSpecRoot(
            "project directory is not inside an OpenSpec repository; "
            "using internal discovery"
        )


def _validated_progress(raw: Any, command: str) -> ChangeProgress:
    if not isinstance(raw, dict):
        raise EvidenceBlocked(
            f"openspec `{command}` returned a malformed change entry; "
            "no completion claimed"
        )
    name = raw.get("name")
    completed = raw.get("completedTasks", 0)
    total = raw.get("totalTasks", 0)
    if not isinstance(name, str) or not name.strip():
        raise EvidenceBlocked(
            f"openspec `{command}` returned a change without a name; "
            "no completion claimed"
        )
    for value, label in ((completed, "completedTasks"), (total, "totalTasks")):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise EvidenceBlocked(
                f"openspec `{command}` returned invalid `{label}` "
                f"for change `{name.strip()}`; no completion claimed"
            )
    if completed > total:
        raise EvidenceBlocked(
            f"openspec `{command}` is contradictory for change "
            f"`{name.strip()}` ({completed} completed of {total} tasks); "
            "no completion claimed"
        )
    return ChangeProgress(name=name.strip(), completed=completed, total=total)


def query_changes(
    project_dir: Path,
    timeout: float = COMMAND_TIMEOUT_S,
    runner: Callable[..., Any] | None = None,
) -> ChangeList:
    """Authoritative active queue from `openspec list --json`.

    Raises ``EvidenceBlocked`` on any unavailable or malformed evidence
    and ``NotOpenSpecRoot`` outside an OpenSpec repository.
    """
    require_root(project_dir)
    stdout = run_openspec(
        project_dir, ["list", "--json"], timeout=timeout, runner=runner
    )
    data = _payload(stdout, "list --json")
    _check_root_source(data)
    raw_changes = data.get("changes", [])
    if not isinstance(raw_changes, list):
        raise EvidenceBlocked(
            "openspec `list --json` returned a malformed `changes` list; "
            "no completion claimed"
        )
    entries: dict[str, ChangeProgress] = {}
    for raw in raw_changes:
        progress = _validated_progress(raw, "list --json")
        entries[progress.name] = progress
    return ChangeList(order=sorted(entries), entries=entries)


def query_change_status(
    project_dir: Path,
    name: str,
    timeout: float = COMMAND_TIMEOUT_S,
    runner: Callable[..., Any] | None = None,
) -> ChangeStatus:
    """Probe one recorded change with `openspec status --change --json`.

    A CLI-reported "not found" error means the recorded name is absent
    (renamed, deleted, or archived), which the caller distinguishes via
    the archive proof; it is not itself completion. Raises
    ``EvidenceBlocked`` on unavailable or malformed evidence.
    """
    require_root(project_dir)
    stdout = run_openspec(
        project_dir,
        ["status", "--change", name, "--json"],
        timeout=timeout,
        runner=runner,
    )
    data = _payload(stdout, "status --json")
    status_items = data.get("status", [])
    error_messages: list[str] = []
    if isinstance(status_items, list):
        for item in status_items:
            if not isinstance(item, dict):
                continue
            if item.get("severity") != "error":
                continue
            message = str(item.get("message", ""))
            if "not found" in message.lower():
                return ChangeStatus(found=False, is_complete=False)
            error_messages.append(message or "unknown status error")
    if error_messages:
        detail = redact("; ".join(error_messages)[:2000])
        raise EvidenceBlocked(
            f"openspec `status --json` refused change `{name}`: {detail}; "
            "no completion claimed"
        )
    if data.get("changeName", name) != name:
        raise EvidenceBlocked(
            f"openspec `status --json` answered for a different change "
            f"than `{name}`; no completion claimed"
        )
    is_complete = data.get("isComplete", False)
    if isinstance(is_complete, bool):
        return ChangeStatus(found=True, is_complete=is_complete)
    raise EvidenceBlocked(
        f"openspec `status --json` returned malformed `isComplete` "
        f"for change `{name}`; no completion claimed"
    )


def query_spec_ids(
    project_dir: Path,
    timeout: float = COMMAND_TIMEOUT_S,
    runner: Callable[..., Any] | None = None,
) -> set[str]:
    """Canonical spec ids from `openspec list --specs --json`."""
    require_root(project_dir)
    stdout = run_openspec(
        project_dir, ["list", "--specs", "--json"], timeout=timeout, runner=runner
    )
    data = _payload(stdout, "list --specs --json")
    raw_specs = data.get("specs", [])
    if not isinstance(raw_specs, list):
        raise EvidenceBlocked(
            "openspec `list --specs --json` returned a malformed `specs` "
            "list; no completion claimed"
        )
    ids: set[str] = set()
    for raw in raw_specs:
        if not isinstance(raw, dict) or not raw.get("id"):
            raise EvidenceBlocked(
                "openspec `list --specs --json` returned a spec without "
                "an id; no completion claimed"
            )
        candidate = raw["id"]
        if not isinstance(candidate, str) or not candidate.strip():
            raise EvidenceBlocked(
                "openspec `list --specs --json` returned a spec without "
                "an id; no completion claimed"
            )
        ids.add(candidate.strip())
    return ids


def check_specs_valid(
    project_dir: Path,
    timeout: float = COMMAND_TIMEOUT_S,
    runner: Callable[..., Any] | None = None,
) -> None:
    """Strict canonical validation must exit zero before archival counts.

    Raises ``EvidenceBlocked`` with bounded output when validation fails;
    a non-zero exit is never archival evidence.
    """
    require_root(project_dir)
    try:
        run_openspec(
            project_dir,
            ["validate", "--specs", "--strict", "--no-interactive"],
            timeout=timeout,
            runner=runner,
        )
    except EvidenceBlocked as exc:
        raise EvidenceBlocked(f"strict spec validation did not pass: {exc}") from exc


def _delta_spec_ids(change_root: Path) -> list[str]:
    """Delta spec ids declared under `<change>/specs/*/spec.md` (sorted)."""
    specs_dir = change_root / "specs"
    if not specs_dir.is_dir():
        return []
    try:
        entries = sorted(specs_dir.iterdir(), key=lambda entry: entry.name)
    except OSError:
        return []
    return sorted(
        entry.name
        for entry in entries
        if entry.is_dir() and (entry / "spec.md").is_file()
    )


def find_archive_entry(spec_dir: Path, recorded: str) -> Path | None:
    """Archived directory carrying the recorded name (exact or `-suffix`)."""
    archive = spec_dir / ARCHIVE_DIRNAME
    if not archive.is_dir():
        return None
    try:
        entries = sorted(archive.iterdir(), key=lambda entry: entry.name)
    except OSError:
        return None
    for entry in entries:
        if not entry.is_dir():
            continue
        if entry.name == recorded or entry.name.endswith(f"-{recorded}"):
            return entry
    return None


def check_archive_proof(
    project_dir: Path,
    spec_dir: str,
    recorded: str,
    spec_ids: set[str],
) -> str:
    """Prove a recorded change is truly archived (or raise ``EvidenceBlocked``).

    Evidence is the conjunction of an archived change directory with the
    recorded name suffix and every delta spec id present in the canonical
    spec list. Changes without delta specs (infrastructure skips) prove
    archival through the archive directory alone. Returns the
    operator-readable evidence detail.
    """
    base = project_dir / spec_dir
    entry = find_archive_entry(base, recorded)
    if entry is None:
        raise EvidenceBlocked(
            f"recorded change `{recorded}` is absent from the active list "
            "and has no archived record; it may have been renamed or "
            "deleted — verify the change directory before continuing"
        )
    deltas = _delta_spec_ids(entry)
    missing = sorted(spec_id for spec_id in deltas if spec_id not in spec_ids)
    if missing:
        names = ", ".join(f"`{spec_id}`" for spec_id in missing)
        raise EvidenceBlocked(
            f"recorded change `{recorded}` is archived as `{entry.name}` "
            f"but canonical spec {names} is missing; "
            "no completion claimed"
        )
    if deltas:
        names = ", ".join(f"`{spec_id}`" for spec_id in deltas)
        return (
            f"recorded change `{recorded}` archived as `{entry.name}`; "
            f"canonical spec {names} present"
        )
    return (
        f"recorded change `{recorded}` archived as `{entry.name}` "
        "(no delta specs to verify)"
    )


def validate_record(raw: Any) -> ConversationRecord:
    """Strictly validate one decoded conversation record."""
    if not isinstance(raw, dict):
        raise ConversationError("conversation record must be a JSON object")
    version = raw.get("version", CONVERSATION_VERSION)
    if version != CONVERSATION_VERSION:
        raise ConversationError(
            f"unsupported conversation version `{version}`: "
            f"expected {CONVERSATION_VERSION}"
        )
    conversation_id = raw.get("conversation_id", "")
    role = raw.get("role", "")
    current_spec = raw.get("current_spec", "")
    spec_path = raw.get("spec_path", "")
    started_at = raw.get("started_at", "")
    queue = raw.get("queue", [])
    for field, value in (
        ("conversation_id", conversation_id),
        ("role", role),
        ("current_spec", current_spec),
        ("spec_path", spec_path),
        ("started_at", started_at),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ConversationError(f"conversation record has an invalid `{field}`")
    if role not in CONVERSATION_ROLES:
        raise ConversationError(f"conversation record has unknown role `{role}`")
    if not isinstance(queue, list) or any(not isinstance(name, str) for name in queue):
        raise ConversationError("conversation record has an invalid `queue`")
    return ConversationRecord(
        version=CONVERSATION_VERSION,
        conversation_id=conversation_id,
        role=role,
        current_spec=current_spec,
        spec_path=spec_path,
        started_at=started_at,
        queue=list(queue),
    )


def read_conversation(project_dir: Path) -> ConversationRecord | None:
    """Return the recorded conversation, or None when none was recorded.

    Raises ``ConversationError`` when the record exists but is malformed;
    callers surface that as a blocked boundary, never a silent fallback.
    """
    path = conversation_path(project_dir)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConversationError(
            f"conversation record is malformed JSON: {exc}"
        ) from exc
    except OSError as exc:
        raise ConversationError(f"conversation record is unreadable: {exc}") from exc
    return validate_record(raw)


def write_record_atomically(path: Path, record: ConversationRecord) -> None:
    """Persist one conversation record atomically (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".conversation.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def record_conversation(
    project_dir: Path,
    role: str,
    current_spec: str,
    spec_dir: str,
    queue: list[str],
    handoff_file: str = "HANDOFF.md",
) -> ConversationRecord:
    """Record the conversation target before any provider input is sent.

    Atomically persists a fresh versioned record (a new conversation id
    per prompt) and synchronizes ``HANDOFF.current_spec`` and
    ``current_spec_file`` without touching completed or unresolved
    history. Raises ``ConversationError`` for an invalid role or an
    empty target and ``handoff.HandoffError`` for an untrusted handoff.
    """
    if role not in CONVERSATION_ROLES:
        raise ConversationError(
            f"unknown conversation role `{role}`: "
            f"expected one of {', '.join(CONVERSATION_ROLES)}"
        )
    target = current_spec.strip()
    if not target:
        raise ConversationError("conversation target must not be empty")
    record = ConversationRecord(
        conversation_id=new_conversation_id(),
        role=role,
        current_spec=target,
        spec_path=f"{spec_dir}/{target}",
        started_at=now_iso(),
        queue=list(queue),
    )
    write_record_atomically(conversation_path(project_dir), record)
    handoff_path = project_dir / handoff_file
    handoff = handoff_mod.read_handoff(handoff_path)
    handoff.current_spec = target
    handoff.current_spec_file = f"{spec_dir}/{target}"
    handoff_mod.write_handoff(handoff_path, handoff)
    return record
