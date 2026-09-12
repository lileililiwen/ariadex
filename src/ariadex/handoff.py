"""Durable cross-session handoff and unresolved-issue lifecycle.

The handoff file (default `HANDOFF.md`) is Markdown with a
versioned YAML front-matter block, so it stays human-readable while the
runner parses session id, current spec, status, completed work, unresolved
items, next action, and next spec without conversation history.

Unresolved items use OPEN, RESOLVED, DEFERRED, or BLOCKED. Deferred items
require a target spec and reason; status changes append history and items
are never deleted, so nothing disappears silently.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml

HANDOFF_VERSION = 1
FRONT_MATTER_DELIMITER = "---"

ITEM_STATUSES = ("OPEN", "RESOLVED", "DEFERRED", "BLOCKED")
PRIORITIES = ("high", "medium", "low")
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
HANDOFF_STATUSES = ("idle", "in-progress", "blocked", "complete")


class HandoffError(Exception):
    """The handoff file is malformed and cannot be trusted."""


@dataclasses.dataclass
class UnresolvedItem:
    id: str
    type: str
    description: str
    priority: str = "medium"
    status: str = "OPEN"
    target_spec: str | None = None
    reason: str | None = None
    history: list = dataclasses.field(default_factory=list)
    attempts: int = 0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class CompletedItem:
    id: str
    summary: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Handoff:
    version: int = HANDOFF_VERSION
    session_id: str = ""
    status: str = "idle"
    current_spec: str | None = None
    current_spec_file: str | None = None
    completed: list = dataclasses.field(default_factory=list)
    unresolved: list = dataclasses.field(default_factory=list)
    next_action: str | None = None
    next_spec: str | None = None
    updated_at: str = ""
    body: str | None = None


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_item_id() -> str:
    return f"u-{uuid.uuid4().hex[:8]}"


def empty_handoff(session_id: str = "") -> Handoff:
    return Handoff(session_id=session_id, updated_at=now_iso())


def _require_enum(value, allowed: tuple, what: str) -> None:
    if value not in allowed:
        raise HandoffError(
            f"invalid {what} `{value}`: expected one of {', '.join(allowed)}"
        )


def _validate_item(raw: dict) -> UnresolvedItem:
    if not isinstance(raw, dict):
        raise HandoffError("invalid unresolved item: object required")
    for field in ("id", "type", "description"):
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            raise HandoffError(
                f"invalid unresolved item: non-empty `{field}` is required"
            )
    priority = raw.get("priority", "medium")
    _require_enum(priority, PRIORITIES, "priority")
    status = raw.get("status", "OPEN")
    _require_enum(status, ITEM_STATUSES, "item status")
    target_spec = raw.get("target_spec")
    reason = raw.get("reason")
    if status == "DEFERRED" and not (target_spec and reason):
        raise HandoffError(
            f"invalid deferred item `{raw.get('id')}`: "
            "`target_spec` and `reason` are required"
        )
    history = raw.get("history", [])
    if not isinstance(history, list):
        raise HandoffError(f"invalid history for item `{raw.get('id')}`: list required")
    attempts = raw.get("attempts", 0)
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        raise HandoffError(
            f"invalid attempts for item `{raw.get('id')}`: integer >= 0 required"
        )
    return UnresolvedItem(
        id=raw["id"],
        type=raw["type"],
        description=raw["description"],
        priority=priority,
        status=status,
        target_spec=target_spec,
        reason=reason,
        history=history,
        attempts=attempts,
    )


def _split_front_matter(text: str) -> tuple[dict | None, str]:
    """Return (front matter mapping or None, markdown body)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        return None, text
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONT_MATTER_DELIMITER:
            raw = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            try:
                data = yaml.safe_load(raw)
            except yaml.YAMLError as exc:
                raise HandoffError(f"malformed handoff front matter: {exc}") from exc
            if data is None:
                return {}, body
            if not isinstance(data, dict):
                raise HandoffError("malformed handoff front matter: mapping required")
            return data, body
    raise HandoffError("malformed handoff: unclosed front-matter block")


def read_handoff(path: Path) -> Handoff:
    """Read the handoff file.

    A missing file yields an empty handoff. A file without front matter is
    adopted (existing body preserved, schema defaults applied). Malformed
    front matter or schema violations raise HandoffError instead of
    silently discarding work.
    """
    if not path.is_file():
        return empty_handoff()
    text = path.read_text(encoding="utf-8")
    data, body = _split_front_matter(text)
    handoff = empty_handoff()
    handoff.body = body
    if data is None:
        return handoff
    version = data.get("version", HANDOFF_VERSION)
    if version != HANDOFF_VERSION:
        raise HandoffError(
            f"unsupported handoff version `{version}`: expected {HANDOFF_VERSION}"
        )
    status = data.get("status", "idle")
    _require_enum(status, HANDOFF_STATUSES, "handoff status")
    completed = []
    for raw in data.get("completed", []):
        if not isinstance(raw, dict) or not raw.get("id") or not raw.get("summary"):
            raise HandoffError(
                "invalid completed item: `id` and `summary` are required"
            )
        completed.append(CompletedItem(id=raw["id"], summary=raw["summary"]))
    unresolved = [_validate_item(raw) for raw in data.get("unresolved", [])]
    ids = [item.id for item in unresolved]
    if len(set(ids)) != len(ids):
        raise HandoffError("invalid handoff: duplicate unresolved item ids")
    handoff.version = HANDOFF_VERSION
    handoff.session_id = data.get("session_id", "") or ""
    handoff.status = status
    handoff.current_spec = data.get("current_spec")
    handoff.current_spec_file = data.get("current_spec_file")
    handoff.completed = completed
    handoff.unresolved = unresolved
    handoff.next_action = data.get("next_action")
    handoff.next_spec = data.get("next_spec")
    handoff.updated_at = data.get("updated_at", "") or now_iso()
    return handoff


def render_body(handoff: Handoff) -> str:
    lines = ["# Ariadex handoff", ""]
    lines.append(f"Status: {handoff.status}")
    lines.append(f"Current spec: {handoff.current_spec or '(none)'}")
    lines.append(f"Next spec: {handoff.next_spec or '(none)'}")
    lines.append(f"Next action: {handoff.next_action or '(none)'}")
    lines.append("")
    lines.append("## Completed")
    lines.append("")
    if handoff.completed:
        for item in handoff.completed:
            lines.append(f"- {item.id}: {item.summary}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Unresolved")
    lines.append("")
    if handoff.unresolved:
        for item in handoff.unresolved:
            lines.append(
                f"- {item.id} [{item.status}/{item.priority}] "
                f"({item.type}): {item.description}"
            )
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


def write_handoff(path: Path, handoff: Handoff) -> Handoff:
    """Persist the handoff atomically (temp file + rename)."""
    handoff.updated_at = now_iso()
    front = {
        "ariadex_handoff_version": HANDOFF_VERSION,
        "version": handoff.version,
        "session_id": handoff.session_id,
        "status": handoff.status,
        "current_spec": handoff.current_spec,
        "current_spec_file": handoff.current_spec_file,
        "completed": [item.to_dict() for item in handoff.completed],
        "unresolved": [item.to_dict() for item in handoff.unresolved],
        "next_action": handoff.next_action,
        "next_spec": handoff.next_spec,
        "updated_at": handoff.updated_at,
    }
    body = handoff.body if handoff.body is not None else render_body(handoff)
    text = (
        f"{FRONT_MATTER_DELIMITER}\n"
        f"{yaml.safe_dump(front, sort_keys=False)}"
        f"{FRONT_MATTER_DELIMITER}\n{body}"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".handoff.", suffix=".tmp"
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
    return handoff


def add_item(
    handoff: Handoff,
    type: str,
    description: str,
    priority: str = "medium",
    item_id: str | None = None,
) -> UnresolvedItem:
    if not type.strip() or not description.strip():
        raise HandoffError(
            "unresolved item requires non-empty `type` and `description`"
        )
    _require_enum(priority, PRIORITIES, "priority")
    item_id = item_id or new_item_id()
    if any(item.id == item_id for item in handoff.unresolved):
        raise HandoffError(f"duplicate unresolved item id `{item_id}`")
    item = UnresolvedItem(
        id=item_id, type=type, description=description, priority=priority
    )
    handoff.unresolved.append(item)
    return item


def get_item(handoff: Handoff, item_id: str) -> UnresolvedItem:
    for item in handoff.unresolved:
        if item.id == item_id:
            return item
    raise HandoffError(f"unknown unresolved item `{item_id}`")


def set_item_status(
    handoff: Handoff,
    item_id: str,
    status: str,
    target_spec: str | None = None,
    reason: str | None = None,
    note: str = "",
) -> UnresolvedItem:
    """Change an item's status, retaining history. Never deletes the item."""
    _require_enum(status, ITEM_STATUSES, "item status")
    if status == "DEFERRED" and not (target_spec and reason):
        raise HandoffError(
            f"deferring item `{item_id}` requires `target_spec` and `reason`"
        )
    item = get_item(handoff, item_id)
    item.history.append(
        {
            "from": item.status,
            "to": status,
            "at": now_iso(),
            "note": note,
        }
    )
    item.status = status
    if target_spec is not None:
        item.target_spec = target_spec
    if reason is not None:
        item.reason = reason
    return item


def open_items(handoff: Handoff) -> list[UnresolvedItem]:
    """OPEN items, highest priority first, stable in insertion order."""
    opens = [item for item in handoff.unresolved if item.status == "OPEN"]
    opens.sort(key=lambda item: PRIORITY_RANK[item.priority])
    return opens


def count_unresolved(handoff: Handoff) -> int:
    return sum(1 for item in handoff.unresolved if item.status != "RESOLVED")
