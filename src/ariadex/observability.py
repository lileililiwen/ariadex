"""Versioned metrics events, provider-neutral export, bounded notifications.

Stdout and local files stay authoritative. Every lifecycle attention
signal (blocker, verification failure, stale session, verified completion)
is recorded locally as a versioned event first; opt-in sinks (local file,
shell command, webhook) receive redacted payloads afterwards. Export or
notification failure is observable (a local failure event) but never marks
work complete, never erases blockers, never retries unboundedly, and never
changes a scheduling decision.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from . import logging as logging_mod

EVENT_SCHEMA_VERSION = 1
EVENTS_FILENAME = "events.jsonl"
NOTIFY_STATE_FILENAME = "notify_state.json"

EVENT_BLOCKER = "blocker"
EVENT_VERIFICATION_FAILED = "verification-failed"
EVENT_STALE_SESSION = "stale-session"
EVENT_COMPLETED = "completed"
EVENT_EXPORT_FAILED = "export-failed"
EVENT_NOTIFICATION_FAILED = "notification-failed"

ATTENTION_EVENTS = (
    EVENT_BLOCKER,
    EVENT_VERIFICATION_FAILED,
    EVENT_STALE_SESSION,
    EVENT_COMPLETED,
)

#: Cycle outcomes that map to an attention event. Anything else (idle,
#: mode-guard, unverified, internal failures) stays local-only telemetry.
OUTCOME_TO_EVENT = {
    "blocked": EVENT_BLOCKER,
    "verification-failed": EVENT_VERIFICATION_FAILED,
    "interrupted": EVENT_STALE_SESSION,
    "completed": EVENT_COMPLETED,
}

MAX_NOTIFY_KEYS = 200


class ExportError(Exception):
    """An opt-in export or notification sink failed."""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _redacted(text: str) -> tuple[str, int]:
    return logging_mod.redact_with_report(text or "")


def build_event(
    event_type: str,
    *,
    session: str = "",
    spec: str | None = None,
    action: str = "",
    outcome: str = "",
    detail: str = "",
    retry_count: int = 0,
    usage_available: bool = False,
) -> dict:
    """Build a versioned, redacted event payload with stable keys."""
    clean_detail, detail_cuts = _redacted(detail)
    clean_action, action_cuts = _redacted(action)
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "type": event_type,
        "at": now_iso(),
        "session": session,
        "spec": spec,
        "action": clean_action,
        "outcome": outcome,
        "detail": clean_detail,
        "retry_count": retry_count,
        "usage": "available" if usage_available else "unavailable",
        "redactions": detail_cuts + action_cuts,
    }


def event_for_result(
    result,
    *,
    session: str = "",
    spec: str | None = None,
    usage_available: bool = False,
) -> dict | None:
    """Map a cycle result to its attention event, or None when local-only."""
    event_type = OUTCOME_TO_EVENT.get(result.outcome)
    if event_type is None:
        return None
    return build_event(
        event_type,
        session=session,
        spec=spec,
        action=result.action,
        outcome=result.outcome,
        detail=result.detail,
        retry_count=getattr(result, "retry_count", 0),
        usage_available=usage_available,
    )


def events_path(project_dir: Path) -> Path:
    return project_dir / ".ariadex" / EVENTS_FILENAME


def record_event(project_dir: Path, event: dict) -> None:
    """Append one event to the local log. Raises OSError on I/O failure."""
    path = events_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    logging_mod.ensure_secure_permissions(path.parent)
    payload = {"schema_version": EVENT_SCHEMA_VERSION, **event}
    line = json.dumps(payload, sort_keys=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    logging_mod.ensure_secure_permissions(path)


def read_events(project_dir: Path, limit: int = 50) -> list[dict]:
    """Recent local events, oldest first; malformed lines are skipped."""
    path = events_path(project_dir)
    if not path.is_file():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            records.append(data)
    if limit >= 0:
        records = records[-limit:] if limit else []
    return records


def _duration_s(record: dict) -> float | None:
    try:
        start = logging_mod._parse_record_time(record.get("started_at"))
        end = logging_mod._parse_record_time(record.get("ended_at"))
    except Exception:
        return None
    if start is None or end is None or end < start:
        return None
    return end - start


def summarize_metrics(records: list[dict]) -> dict:
    """Aggregate cycle metrics into a versioned, deterministic summary."""
    outcomes: dict[str, int] = {}
    retries_total = 0
    retries_max = 0
    durations: list[float] = []
    usage_available = 0
    usage_unavailable = 0
    validations: dict[str, int] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        outcome = str(record.get("outcome", "unknown"))
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        try:
            retries = int(record.get("retry_count", 0))
        except (TypeError, ValueError):
            retries = 0
        retries_total += retries
        retries_max = max(retries_max, retries)
        duration = _duration_s(record)
        if duration is not None:
            durations.append(duration)
        usage = record.get("usage", "unavailable")
        if usage == "unavailable" or usage is None:
            usage_unavailable += 1
        else:
            usage_available += 1
        validation = str(record.get("validation_result", "unknown"))
        validations[validation] = validations.get(validation, 0) + 1
    durations.sort()
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "cycles": len(records),
        "outcomes": dict(sorted(outcomes.items())),
        "verification_failed": outcomes.get("verification-failed", 0),
        "blocked": outcomes.get("blocked", 0),
        "completed": outcomes.get("completed", 0),
        "retries_total": retries_total,
        "retries_max": retries_max,
        "cycle_duration_s": {
            "count": len(durations),
            "min": durations[0] if durations else None,
            "max": durations[-1] if durations else None,
            "avg": (sum(durations) / len(durations)) if durations else None,
            "last": durations[-1] if durations else None,
        },
        "usage": {
            "available": usage_available,
            "unavailable": usage_unavailable,
        },
        "validation_results": dict(sorted(validations.items())),
    }


class ExportSink:
    """Provider-neutral destination. `send` raises ExportError on failure."""

    name = "sink"

    def send(self, payload: dict) -> None:
        raise NotImplementedError


class FileSink(ExportSink):
    """Local-only default: write the versioned snapshot as JSON."""

    name = "file"

    def __init__(self, dest: Path) -> None:
        self.dest = dest

    def send(self, payload: dict) -> None:
        try:
            self.dest.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(self.dest.parent), prefix=".export.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, sort_keys=True, indent=2))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_name, self.dest)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_name)
                raise
        except ExportError:
            raise
        except Exception as exc:
            raise ExportError(f"file sink failed for `{self.dest}`: {exc}") from exc


class CommandSink(ExportSink):
    """Opt-in shell command receiving the payload JSON on stdin.

    `argv` is executed without a shell; the payload is never interpolated
    into a command line, so secret-bearing text cannot become code.
    """

    name = "command"

    def __init__(self, argv: list[str], timeout_s: int = 30) -> None:
        self.argv = list(argv)
        self.timeout_s = timeout_s

    def send(self, payload: dict) -> None:
        try:
            # Opt-in command sink: argv from operator configuration, no shell,
            # payload delivered on stdin (never interpolated into the command).
            proc = subprocess.run(  # noqa: S603
                self.argv,
                input=json.dumps(payload, sort_keys=True),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ExportError(f"command sink failed (`{self.argv[0]}`): {exc}") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[:500]
            raise ExportError(
                f"command sink exited {proc.returncode} (`{self.argv[0]}`)"
                f"{f': {detail}' if detail else ''}"
            )


class WebhookSink(ExportSink):
    """Opt-in HTTP(S) POST of the payload JSON. Never carries secrets raw:
    callers pass already-redacted payloads."""

    name = "webhook"

    def __init__(self, url: str, timeout_s: int = 30) -> None:
        self.url = url
        self.timeout_s = timeout_s

    def send(self, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        # Operator-configured webhook URL; redacted JSON POST, HTTPS expected.
        request = urllib.request.Request(  # noqa: S310
            self.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            # Same operator-configured endpoint; response status checked below.
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:  # noqa: S310
                status = getattr(response, "status", 200)
        except Exception as exc:
            raise ExportError(f"webhook sink failed (`{self.url}`): {exc}") from exc
        if not (200 <= status < 300):
            raise ExportError(f"webhook sink returned HTTP {status} (`{self.url}`)")


@dataclasses.dataclass
class SinkResult:
    sink: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def build_snapshot(
    project_dir: Path,
    *,
    session: str = "",
    event_limit: int = 50,
) -> dict:
    """Versioned export payload: summary + recent events. Local reads only."""
    metrics = logging_mod.read_metrics(
        project_dir / ".ariadex" / logging_mod.METRICS_FILENAME
    )
    events = read_events(project_dir, limit=event_limit)
    return {
        "schema_version": EVENT_SCHEMA_VERSION,
        "exported_at": now_iso(),
        "session": session,
        "summary": summarize_metrics(metrics),
        "events": events,
    }


def export_snapshot(
    project_dir: Path,
    sinks: list[ExportSink],
    *,
    session: str = "",
    event_limit: int = 50,
) -> list[SinkResult]:
    """Deliver the snapshot to every sink. Never raises.

    Each sink failure is recorded locally as an `export-failed` event and
    reported; success is claimed only per sink that actually delivered.
    Scheduling decisions are untouched: the caller decides what to do with
    the report.
    """
    try:
        snapshot = build_snapshot(project_dir, session=session, event_limit=event_limit)
    except Exception as exc:
        failure = build_event(
            EVENT_EXPORT_FAILED,
            session=session,
            action="export snapshot",
            outcome="export-failed",
            detail=f"could not build export snapshot: {exc}",
        )
        with contextlib.suppress(Exception):
            record_event(project_dir, failure)
        return [
            SinkResult(sink=sink.name, ok=False, detail="snapshot build failed")
            for sink in sinks
        ]
    results: list[SinkResult] = []
    for sink in sinks:
        try:
            sink.send(snapshot)
        except ExportError as exc:
            detail = str(exc)
            results.append(SinkResult(sink=sink.name, ok=False, detail=detail))
            failure = build_event(
                EVENT_EXPORT_FAILED,
                session=session,
                action=f"export via {sink.name}",
                outcome="export-failed",
                detail=detail,
            )
            with contextlib.suppress(Exception):
                record_event(project_dir, failure)
        except Exception as exc:  # pragma: no cover - defensive
            detail = f"unexpected sink error ({sink.name}): {exc}"
            results.append(SinkResult(sink=sink.name, ok=False, detail=detail))
            with contextlib.suppress(Exception):
                record_event(
                    project_dir,
                    build_event(
                        EVENT_EXPORT_FAILED,
                        session=session,
                        action=f"export via {sink.name}",
                        outcome="export-failed",
                        detail=detail,
                    ),
                )
        else:
            results.append(SinkResult(sink=sink.name, ok=True, detail="delivered"))
    return results


def _notify_state_path(project_dir: Path) -> Path:
    return project_dir / ".ariadex" / NOTIFY_STATE_FILENAME


def _load_notify_state(project_dir: Path) -> dict:
    path = _notify_state_path(project_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_notify_state(project_dir: Path, state: dict) -> None:
    path = _notify_state_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".notify.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(state, sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
    logging_mod.ensure_secure_permissions(path)


def dedup_key(event: dict) -> str:
    """Repeated observations of the same attention share one key."""
    return f"{event.get('type', '?')}:{event.get('action', '?')}"


def notify_allowed(
    state: dict,
    key: str,
    *,
    rate_limit: int,
    window_s: int,
    now_s: float | None = None,
) -> tuple[bool, dict]:
    """Sliding-window rate check. Returns (allowed, updated_state).

    Pure function over the persisted state mapping so tests can drive it
    without I/O. State stays bounded: timestamps outside the window are
    dropped and excess keys are evicted oldest-first.
    """
    now = time.time() if now_s is None else now_s
    cutoff = now - window_s if window_s > 0 else float("-inf")
    cleaned: dict[str, list[float]] = {}
    for known, stamps in state.items():
        if not isinstance(stamps, list):
            continue
        kept = [s for s in stamps if isinstance(s, (int, float)) and s >= cutoff]
        if kept:
            cleaned[known] = sorted(kept)
    stamps = cleaned.get(key, [])
    if rate_limit <= 0:
        return False, {**cleaned, key: stamps}
    if len(stamps) >= rate_limit:
        return False, {**cleaned, key: stamps}
    updated = {**cleaned, key: [*stamps, now]}
    while len(updated) > MAX_NOTIFY_KEYS:
        oldest = min(updated, key=lambda k: min(updated[k]) if updated[k] else now)
        del updated[oldest]
    return True, updated


@dataclasses.dataclass
class NotifyResult:
    delivered: bool
    suppressed: bool
    sinks: list[SinkResult]

    def to_dict(self) -> dict:
        return {
            "delivered": self.delivered,
            "suppressed": self.suppressed,
            "sinks": [s.to_dict() for s in self.sinks],
        }


def notify_event(
    project_dir: Path,
    event: dict,
    sinks: list[ExportSink],
    *,
    rate_limit: int = 5,
    window_s: int = 3600,
    now_s: float | None = None,
) -> NotifyResult:
    """Deliver one attention event once per rate window. Never raises.

    Deduplication and rate limiting bound repeated alerts: the same key
    within the window is suppressed locally. A failed delivery is recorded
    as a `notification-failed` event; no unbounded retry follows — the next
    observation may try once more, at most at the configured rate.
    """
    if not sinks:
        return NotifyResult(delivered=False, suppressed=True, sinks=[])
    try:
        state = _load_notify_state(project_dir)
    except Exception:
        state = {}
    key = dedup_key(event)
    allowed, updated = notify_allowed(
        state, key, rate_limit=rate_limit, window_s=window_s, now_s=now_s
    )
    if not allowed:
        with contextlib.suppress(Exception):
            _save_notify_state(project_dir, updated)
        return NotifyResult(delivered=False, suppressed=True, sinks=[])
    sink_results: list[SinkResult] = []
    delivered_any = False
    for sink in sinks:
        try:
            sink.send(event)
        except ExportError as exc:
            detail = str(exc)
            sink_results.append(SinkResult(sink=sink.name, ok=False, detail=detail))
            failure = build_event(
                EVENT_NOTIFICATION_FAILED,
                session=str(event.get("session", "")),
                spec=event.get("spec"),
                action=f"notify via {sink.name}: {key}",
                outcome="notification-failed",
                detail=detail,
            )
            with contextlib.suppress(Exception):
                record_event(project_dir, failure)
        except Exception as exc:  # pragma: no cover - defensive
            detail = f"unexpected sink error ({sink.name}): {exc}"
            sink_results.append(SinkResult(sink=sink.name, ok=False, detail=detail))
        else:
            sink_results.append(SinkResult(sink=sink.name, ok=True, detail="delivered"))
            delivered_any = True
    # Consume rate budget only on actual delivery; a total failure leaves
    # the next observation free to try once more without waiting out the
    # window for an alert the operator never received.
    with contextlib.suppress(Exception):
        if delivered_any:
            _save_notify_state(project_dir, updated)
        else:
            _save_notify_state(project_dir, state)
    return NotifyResult(
        delivered=delivered_any,
        suppressed=False,
        sinks=sink_results,
    )


def notification_sinks(cfg) -> list[ExportSink]:
    """Opt-in sinks from configuration. Empty unless explicitly configured."""
    sinks: list[ExportSink] = []
    command = list(getattr(cfg, "notification_command", []) or [])
    if command:
        sinks.append(CommandSink(command))
    webhook = getattr(cfg, "notification_webhook", "") or ""
    if webhook:
        sinks.append(WebhookSink(webhook))
    return sinks


def announce(project_dir: Path, cfg, event: dict) -> NotifyResult | None:
    """Record an attention event locally, then notify iff opt-in. Never raises.

    Local recording is unconditional (stdout and files stay authoritative);
    delivery happens only when `notifications_enabled` is true and at least
    one sink is configured. Any failure is suppressed: observability never
    changes a scheduling decision.
    """
    try:
        record_event(project_dir, event)
    except Exception:
        return None
    if not getattr(cfg, "notifications_enabled", False):
        return None
    sinks = notification_sinks(cfg)
    if not sinks:
        return None
    try:
        return notify_event(
            project_dir,
            event,
            sinks,
            rate_limit=int(getattr(cfg, "notification_rate_limit", 5)),
            window_s=int(getattr(cfg, "notification_window_seconds", 3600)),
        )
    except Exception:
        return None


def format_events_text(events: list[dict], summary: dict) -> str:
    lines = [
        f"events: {len(events)} shown (schema v{EVENT_SCHEMA_VERSION})",
        f"cycles: {summary.get('cycles', 0)} "
        f"(completed={summary.get('completed', 0)} "
        f"verification-failed={summary.get('verification_failed', 0)} "
        f"blocked={summary.get('blocked', 0)})",
        f"retries: total={summary.get('retries_total', 0)} "
        f"max={summary.get('retries_max', 0)}",
    ]
    usage = summary.get("usage", {})
    lines.append(
        f"usage: available={usage.get('available', 0)} "
        f"unavailable={usage.get('unavailable', 0)}"
    )
    for event in events:
        lines.append(
            f"- {event.get('at', '?')} [{event.get('type', '?')}] "
            f"{event.get('action', '')}"
            + (f" :: {event.get('detail', '')}" if event.get("detail") else "")
        )
    return "\n".join(lines)
