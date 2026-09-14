"""Comprehensive runtime diagnostics: versioned event stream and bundles.

The in-memory widget activity log is too small to explain lifecycle
decisions. This module persists a structured, bounded, redacted JSONL
diagnostic stream under ``.ariadex/diagnostics/`` recording every
important managed boundary: startup, current-spec selection, prompt
delivery, provider readiness/waits/quota/errors, OpenSpec evidence,
boundary decisions, verification, widget lifecycle, human controls,
errors, and shutdown.

Raw provider captures never enter the stream unbounded; an explicitly
bounded, redacted tail may be retained for an exit diagnosis. A failed diagnostic
write never changes scheduling: callers record best-effort and keep
their original lifecycle decision. Diagnostics are never a second
provider-input writer nor a second source of scheduling truth.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from . import logging as logging_mod

DIAGNOSTIC_SCHEMA_VERSION = 1
DIAGNOSTICS_DIRNAME = "diagnostics"
DIAGNOSTICS_FILENAME = "diagnostics.jsonl"

#: Lifecycle categories recorded by the stream (spec design event model).
CATEGORIES = (
    "startup",
    "selection",
    "prompt",
    "provider",
    "openspec",
    "boundary",
    "verification",
    "pause",
    "quota",
    "error",
    "widget",
    "shutdown",
)

#: Bound for any single free-text field before persistence.
MAX_FIELD_CHARS = 2000
#: Default retention/rotation bounds (telemetry only, never durable state).
RETENTION_DAYS = 30
MAX_BYTES = 5 * 1024 * 1024


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _bounded(text: str, limit: int = MAX_FIELD_CHARS) -> str:
    if len(text) > limit:
        return text[:limit] + f"... [truncated {len(text) - limit} chars]"
    return text


def _redacted_field(text: str) -> tuple[str, int]:
    cleaned, count = logging_mod.redact_with_report(text or "")
    return _bounded(cleaned), count


def diagnostics_path(project_dir: Path) -> Path:
    return project_dir / ".ariadex" / DIAGNOSTICS_DIRNAME / DIAGNOSTICS_FILENAME


def build_diagnostic(
    category: str,
    action: str,
    *,
    result: str = "",
    message: str = "",
    provider: str = "",
    session: str = "",
    phase: str = "",
    conversation_id: str = "",
    current_spec: str | None = None,
    open_tasks: int = 0,
    closed_tasks: int = 0,
    command_role: str = "",
    recovery: str = "",
    classification: str = "",
    active_queue: tuple[str, ...] | list[str] = (),
    evidence_source: str = "",
    decision: str = "",
    blocker: str = "",
    operation: str = "",
    next_action: str = "",
    requested_path: str = "",
    normalized_path: str = "",
    policy: str = "",
    details: dict[str, object] | None = None,
) -> dict:
    """Build one versioned, redacted diagnostic record with stable keys.

    The no-advance fields (`classification`, `active_queue`,
    `evidence_source`, `decision`, `blocker`, `operation`, `next_action`)
    explain every stop/no-advance path: what the provider surface was,
    which recorded spec and authoritative queue gated the boundary, what
    was decided, why, and what the operator should do next. The permission
    fields (`requested_path`, `normalized_path`, `policy`) carry the
    evaluated provider file request for allow/waiting/deny decisions. All
    free text is redacted and bounded before persistence; raw provider
    captures must never be passed in.
    """
    category = category if category in CATEGORIES else "error"
    clean_action, action_cuts = _redacted_field(action)
    clean_message, message_cuts = _redacted_field(message)
    clean_recovery, recovery_cuts = _redacted_field(recovery)
    clean_blocker, blocker_cuts = _redacted_field(blocker)
    clean_next, next_cuts = _redacted_field(next_action)
    clean_requested, requested_cuts = _redacted_field(requested_path)
    clean_normalized, normalized_cuts = _redacted_field(normalized_path)
    clean_policy, policy_cuts = _redacted_field(policy)
    queue = [str(name) for name in (active_queue or ())]
    safe_details: dict[str, object] = {}
    for key, value in (details or {}).items():
        name = str(key)
        if isinstance(value, str):
            cleaned, cuts = _redacted_field(value)
            safe_details[name] = cleaned
            action_cuts += cuts
        elif isinstance(value, (bool, int, float)) or value is None:
            safe_details[name] = value
        else:
            cleaned, cuts = _redacted_field(str(value))
            safe_details[name] = cleaned
            action_cuts += cuts
    return {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "at": now_iso(),
        "category": category,
        "action": clean_action,
        "result": result,
        "message": clean_message,
        "provider": provider,
        "session": session,
        "phase": phase,
        "conversation_id": conversation_id,
        "current_spec": current_spec,
        "open_tasks": open_tasks,
        "closed_tasks": closed_tasks,
        "command_role": command_role,
        "recovery": clean_recovery,
        "classification": classification,
        "active_queue": queue,
        "evidence_source": evidence_source,
        "decision": decision,
        "blocker": clean_blocker,
        "operation": operation,
        "next_action": clean_next,
        "requested_path": clean_requested,
        "normalized_path": clean_normalized,
        "policy": clean_policy,
        "details": safe_details,
        "redactions": action_cuts
        + message_cuts
        + recovery_cuts
        + blocker_cuts
        + next_cuts
        + requested_cuts
        + normalized_cuts
        + policy_cuts,
    }


def record_diagnostic(project_dir: Path, record: dict) -> None:
    """Append one record atomically. Raises OSError on I/O failure.

    Uses ``O_APPEND`` so concurrent writers never interleave or truncate
    each other's lines; callers must treat failure as observability-only
    and keep their lifecycle decision unchanged.
    """
    stream = diagnostics_path(project_dir)
    stream.parent.mkdir(parents=True, exist_ok=True)
    logging_mod.ensure_secure_permissions(stream.parent)
    payload = {"schema_version": DIAGNOSTIC_SCHEMA_VERSION, **record}
    line = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(str(stream), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        # os.fdopen took ownership of fd; it is closed by the context.
        raise
    logging_mod.ensure_secure_permissions(stream)


def try_record(project_dir: Path, record: dict) -> bool:
    """Best-effort record: True when persisted, False when unavailable.

    Never raises; a storage failure is reported to the caller, which
    continues with its original lifecycle decision unchanged.
    """
    try:
        record_diagnostic(project_dir, record)
    except Exception:
        return False
    return True


def record_operation(
    project_dir: Path,
    operation: str,
    *,
    phase: str,
    result: str = "started",
    provider: str = "",
    session: str = "",
    actor: str = "ariadex",
    details: dict[str, object] | None = None,
) -> bool:
    """Record a potentially destructive lifecycle operation best-effort.

    This is deliberately separate from scheduling diagnostics: an operation
    audit is written immediately before and after signals, tmux teardown, and
    provider startup so postmortems can identify the actor and target even
    when the operation fails.
    """
    safe_details = {"actor": actor, **(details or {})}
    return try_record(
        project_dir,
        build_diagnostic(
            "provider",
            operation,
            result=result,
            provider=provider,
            session=session,
            phase=phase,
            details=safe_details,
        ),
    )


def _parse_time(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.timestamp()


def read_diagnostics(
    project_dir: Path,
    *,
    limit: int = 100,
    since: str = "",
    categories: tuple[str, ...] = (),
) -> tuple[list[dict], dict]:
    """Read the stream oldest-first with filters; report skipped lines.

    Malformed lines are skipped and counted, never raised. An unreadable
    stream returns ([], {"unavailable": reason}) so the CLI can report
    the gap honestly instead of fabricating an empty history.
    """
    stream = diagnostics_path(project_dir)
    if not stream.is_file():
        return [], {"unavailable": f"no diagnostic stream at `{stream}` yet"}
    try:
        raw_lines = stream.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], {"unavailable": f"could not read `{stream}`: {exc}"}
    cutoff = _parse_time(since) if since else None
    wanted = {c for c in categories if c in CATEGORIES}
    records: list[dict] = []
    malformed = 0
    for line in raw_lines:
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(data, dict):
            malformed += 1
            continue
        if wanted and str(data.get("category", "")) not in wanted:
            continue
        if cutoff is not None:
            stamp = _parse_time(data.get("at"))
            if stamp is not None and stamp < cutoff:
                continue
        records.append(data)
    info: dict = {"malformed_skipped": malformed, "total_kept": len(records)}
    if limit >= 0:
        records = records[-limit:] if limit else []
    return records, info


def apply_retention(
    project_dir: Path,
    *,
    retention_days: int = RETENTION_DAYS,
    max_bytes: int = MAX_BYTES,
    now_s: float | None = None,
) -> dict:
    """Enforce age/size bounds on the diagnostic stream only.

    Oldest lines are dropped first so the freshest evidence survives.
    Malformed lines are crash-recovery evidence: retained by age, still
    trimmed when the byte cap requires it. Never touches durable state
    (handoff, config, locks, conversation records).
    """
    stream = diagnostics_path(project_dir)
    if not stream.is_file():
        return {"removed_lines": 0, "retained_lines": 0, "notes": []}
    moment = time.time() if now_s is None else now_s
    cutoff = moment - retention_days * 86400 if retention_days > 0 else None
    notes: list[str] = []
    try:
        raw_lines = stream.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {
            "removed_lines": 0,
            "retained_lines": 0,
            "notes": [f"could not read `{stream}`: {exc}"],
        }
    kept: list[str] = []
    removed = 0
    for line in raw_lines:
        if not line.strip():
            continue
        if cutoff is not None:
            try:
                data = json.loads(line)
                stamp = _parse_time(data.get("at") if isinstance(data, dict) else None)
            except json.JSONDecodeError:
                kept.append(line)
                continue
            if stamp is not None and stamp < cutoff:
                removed += 1
                continue
        kept.append(line)
    if max_bytes > 0:
        encoded = [(ln, len((ln + "\n").encode("utf-8"))) for ln in kept]
        total = sum(size for _, size in encoded)
        while encoded and total > max_bytes:
            _, size = encoded.pop(0)
            total -= size
            removed += 1
        kept = [ln for ln, _ in encoded]
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(stream.parent), prefix=".diagnostics.", suffix=".tmp"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for ln in kept:
                handle.write(ln + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, stream)
        logging_mod.ensure_secure_permissions(stream)
    except OSError as exc:
        notes.append(f"could not rewrite `{stream}`: {exc}")
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
    return {"removed_lines": removed, "retained_lines": len(kept), "notes": notes}


def format_diagnostics_text(records: list[dict], info: dict) -> str:
    """Chronological human-readable rendering of the stream."""
    unavailable = info.get("unavailable")
    if unavailable:
        return f"diagnostics: unavailable ({unavailable})"
    lines = [
        f"diagnostics: {len(records)} shown "
        f"(schema v{DIAGNOSTIC_SCHEMA_VERSION}, "
        f"malformed skipped: {info.get('malformed_skipped', 0)})"
    ]
    for record in records:
        lines.append(
            f"- {record.get('at', '?')} [{record.get('category', '?')}] "
            f"{record.get('action', '')}"
            + (f" => {record.get('result', '')}" if record.get("result") else "")
            + (f" :: {record.get('message', '')}" if record.get("message") else "")
        )
    return "\n".join(lines)


@dataclasses.dataclass
class BundleReport:
    files: int
    total_bytes: int
    destination: str
    notes: list[str]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _snapshot_openspec_evidence(project_dir: Path) -> dict:
    """Best-effort OpenSpec evidence snapshot; gaps reported, never raised."""
    from . import openspec_evidence as evidence_mod

    snapshot: dict = {"changes": [], "notes": []}
    try:
        changes = evidence_mod.query_changes(project_dir)
    except Exception as exc:
        snapshot["notes"].append(f"openspec list unavailable: {exc}")
        return snapshot
    for name in changes.order:
        progress = changes.entries.get(name)
        if progress is None:
            snapshot["changes"].append({"name": name, "note": "no progress entry"})
            continue
        snapshot["changes"].append(
            {
                "name": name,
                "total_tasks": progress.total,
                "completed_tasks": progress.completed,
                "open_tasks": progress.open_tasks,
            }
        )
    return snapshot


def build_bundle(
    project_dir: Path,
    dest: Path,
    *,
    max_bytes: int = 52428800,
    diagnostic_limit: int = 1000,
) -> BundleReport:
    """Write a local redacted diagnostic bundle for later research.

    Contains ``manifest.json`` (schema, exported-at, bounds), the current
    durable state snapshot, the OpenSpec evidence snapshot, the bounded
    diagnostic stream, and selected existing telemetry (metrics summary +
    recent attention events). Local-only, bounded, redacted; refuses with
    OSError above the byte bound. Raw provider captures are never
    included: only classifications and bounded evidence references.
    """
    from . import observability as observability_mod

    notes: list[str] = []
    records, info = read_diagnostics(project_dir, limit=diagnostic_limit)
    if info.get("unavailable"):
        notes.append(str(info["unavailable"]))
    metrics = logging_mod.read_metrics(
        project_dir / ".ariadex" / logging_mod.METRICS_FILENAME
    )
    summary = observability_mod.summarize_metrics(metrics)
    recent_events = observability_mod.read_events(project_dir, limit=50)
    state_snapshot: dict = {}
    for name in ("state.json", "conversation.json", "config.yaml"):
        candidate = project_dir / ".ariadex" / name
        if name == "config.yaml":
            candidate = project_dir / ".ariadex" / name
        try:
            if candidate.is_file():
                text, _ = logging_mod.redact_with_report(
                    candidate.read_text(encoding="utf-8")[:MAX_FIELD_CHARS]
                )
                state_snapshot[name] = text
        except OSError as exc:
            notes.append(f"skipped `{name}`: {exc}")
    bundle = {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "exported_at": now_iso(),
        "bounds": {
            "diagnostic_limit": diagnostic_limit,
            "malformed_skipped": info.get("malformed_skipped", 0),
        },
        "state": state_snapshot,
        "openspec": _snapshot_openspec_evidence(project_dir),
        "diagnostics": records,
        "metrics_summary": summary,
        "recent_events": recent_events,
        "notes": notes,
    }
    raw = json.dumps(bundle, sort_keys=True).encode("utf-8")
    if max_bytes > 0 and len(raw) > max_bytes:
        raise OSError(
            f"refused: diagnostic bundle is {len(raw)} bytes, above the "
            f"{max_bytes}-byte bound; lower --diagnostic-limit or prune first"
        )
    dest.mkdir(parents=True, exist_ok=True)
    logging_mod.ensure_secure_permissions(dest)
    manifest = {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "exported_at": bundle["exported_at"],
        "diagnostics_shown": len(records),
        "notes": notes,
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8"
    )
    (dest / "bundle.json").write_text(
        json.dumps(bundle, sort_keys=True, indent=2), encoding="utf-8"
    )
    for path in (dest / "manifest.json", dest / "bundle.json"):
        logging_mod.ensure_secure_permissions(path)
    total = sum(
        p.stat().st_size for p in (dest / "manifest.json", dest / "bundle.json")
    )
    return BundleReport(files=2, total_bytes=total, destination=str(dest), notes=notes)


def copy_telemetry_for_bundle(
    project_dir: Path, dest: Path, max_bytes: int = 52428800
) -> dict:
    """Copy runs/ + metrics.jsonl beside the bundle (bounded, telemetry only)."""
    report = logging_mod.export_logs(
        project_dir / ".ariadex" / logging_mod.RUNS_DIRNAME,
        project_dir / ".ariadex" / logging_mod.METRICS_FILENAME,
        dest / "telemetry",
        max_bytes=max_bytes,
    )
    return report.to_dict()
