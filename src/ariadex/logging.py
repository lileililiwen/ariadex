"""Session run logs, metrics records, and secret redaction.

Run logs live under `.ariadex/runs/<session-id>/` and record input,
output, session, spec, start/end times, exit code, validation result, and
reset reason. Metrics append one JSON object per cycle to
`.ariadex/metrics.jsonl` with the same identity plus retry count and usage:
`usage: unavailable` when the adapter cannot report usage, never an
invented estimate.

Log governance: redaction runs before persistence, files use restrictive
permissions where the host supports them, and retention/size bounds prune
only telemetry (run logs + metrics). Handoff history is never touched.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import re
import shutil
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

RUNS_DIRNAME = "runs"
METRICS_FILENAME = "metrics.jsonl"
LOG_SCHEMA_VERSION = 1
METRICS_SCHEMA_VERSION = 1

REDACTED = "<redacted>"

SECURE_FILE_MODE = 0o600
SECURE_DIR_MODE = 0o700

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9\-_]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?"
        r"-----END [A-Z ]*PRIVATE KEY-----"
    ),
    re.compile(r"(?i)((?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*)\S+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/=]{10,}"),
    re.compile(
        r"(?:ghp_[A-Za-z0-9]{8,}|gho_[A-Za-z0-9]{8,}|"
        r"github_pat_[A-Za-z0-9_]{8,}|glpat-[A-Za-z0-9\-_]{8,}|"
        r"xox[baprs]-[A-Za-z0-9\-]{8,})"
    ),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"(?i)((?:aws_secret_access_key|aws_session_token)\s*[:=]\s*)\S+"),
]


def redact_with_report(text: str) -> tuple[str, int]:
    """Redact likely secrets; return (redacted_text, substitution_count).

    Only the count is recorded as metadata; matched secret values are
    never stored anywhere.
    """
    if not text:
        return text, 0
    redacted = text
    count = 0
    for index, pattern in enumerate(_SECRET_PATTERNS):
        if index in (3, 4, 7):
            # Keep the `key=` / `Bearer ` prefix so operators see which
            # field was cut without storing the secret value.
            redacted, n = pattern.subn(r"\1" + REDACTED, redacted)
            count += n
        else:
            redacted, n = pattern.subn(REDACTED, redacted)
            count += n
    return redacted, count


def redact(text: str) -> str:
    """Replace likely secrets with `<redacted>`; leave other text intact."""
    redacted, _ = redact_with_report(text)
    return redacted


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclasses.dataclass
class RunLogRecord:
    session_id: str
    spec: str | None
    action: str
    input: str
    output: str
    exit_code: int | None
    validation_result: str
    reset_reason: str | None
    retry_count: int
    started_at: str = ""
    ended_at: str = ""
    redaction_count: int = 0
    schema_version: int = LOG_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def ensure_secure_permissions(path: Path) -> str | None:
    """Apply restrictive permissions; return a diagnostic or None on success.

    Directories get 0o700, files get 0o600. On platforms without POSIX
    ownership (e.g. Windows) or when chmod fails, the path is left as-is
    and a human-readable diagnostic is returned instead of raising.
    """
    try:
        if os.name == "nt":
            return (
                f"restrictive permissions not enforced for `{path}` "
                "on this platform (Windows ACLs apply)"
            )
        mode = SECURE_DIR_MODE if path.is_dir() else SECURE_FILE_MODE
        os.chmod(path, mode)
    except (OSError, NotImplementedError) as exc:
        return f"could not restrict permissions for `{path}`: {exc}"
    return None


def render_log(record: RunLogRecord) -> str:
    exit_code = "n/a" if record.exit_code is None else str(record.exit_code)
    return (
        f"schema: {record.schema_version}\n"
        f"session: {record.session_id}\n"
        f"spec: {record.spec or '(none)'}\n"
        f"action: {record.action}\n"
        f"started: {record.started_at}\n"
        f"ended: {record.ended_at}\n"
        f"exit code: {exit_code}\n"
        f"validation: {record.validation_result}\n"
        f"reset: {record.reset_reason or '(none)'}\n"
        f"retries: {record.retry_count}\n"
        f"redactions: {record.redaction_count}\n"
        f"--- input ---\n{record.input}\n"
        f"--- output ---\n{record.output}\n"
    )


def write_run_log(runs_dir: Path, record: RunLogRecord) -> Path:
    """Write one cycle log atomically; returns the log path."""
    if not record.started_at:
        record.started_at = now_iso()
    if not record.ended_at:
        record.ended_at = now_iso()
    record.input, in_count = redact_with_report(record.input)
    record.output, out_count = redact_with_report(record.output)
    record.redaction_count = in_count + out_count
    record.schema_version = LOG_SCHEMA_VERSION
    session_dir = runs_dir / (record.session_id or "unknown-session")
    session_dir.mkdir(parents=True, exist_ok=True)
    ensure_secure_permissions(session_dir)
    # Restrict the runs root as well (best-effort, never fails the write).
    if runs_dir.is_dir():
        ensure_secure_permissions(runs_dir)
    stamp = record.ended_at.replace(":", "").replace("+", "")
    name = f"{stamp}-{uuid.uuid4().hex[:6]}.log"
    path = session_dir / name
    fd, tmp_name = tempfile.mkstemp(dir=str(session_dir), prefix=".run.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(render_log(record))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
    ensure_secure_permissions(path)
    return path


def append_metrics(path: Path, record: dict) -> None:
    """Append one JSON object per line; creates parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_secure_permissions(path.parent)
    payload = {"schema_version": METRICS_SCHEMA_VERSION, **record}
    line = json.dumps(payload, sort_keys=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    ensure_secure_permissions(path)


def read_metrics(path: Path) -> list[dict]:
    """Read metrics, skipping blank or malformed lines (crash recovery)."""
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            records.append(data)
    return records


def usage_record(usage: dict | None) -> object:
    """Explicit unavailable marker instead of an invented estimate."""
    if usage is None:
        return "unavailable"
    return dict(usage)


@dataclasses.dataclass
class RetentionReport:
    removed_logs: list[str]
    removed_bytes: int
    retained_logs: int
    retained_bytes: int
    metrics_trimmed: bool
    metrics_removed_lines: int
    metrics_retained_lines: int
    notes: list[str]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _parse_record_time(value: object) -> float | None:
    """Parse an ISO timestamp from a metrics record; None when absent."""
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.timestamp()


def _iter_log_files(runs_dir: Path) -> list[Path]:
    if not runs_dir.is_dir():
        return []
    return sorted(
        (p for p in runs_dir.rglob("*.log") if p.is_file()),
        key=lambda p: str(p),
    )


def apply_retention(
    runs_dir: Path,
    metrics_path: Path,
    retention_days: int = 30,
    log_max_bytes: int = 10485760,
    metrics_max_bytes: int = 5242880,
    now_s: float | None = None,
) -> RetentionReport:
    """Enforce retention and size bounds on telemetry only.

    Removes or rotates eligible run logs and metrics lines and reports
    what was removed or retained. Scope is strictly `.ariadex/runs/` and
    `metrics.jsonl`; handoff, state, config, and lock files are never
    touched. A limit of 0 disables that bound (keep everything).
    """
    moment = time.time() if now_s is None else now_s
    removed: list[str] = []
    removed_bytes = 0
    notes: list[str] = []

    candidates = _iter_log_files(runs_dir)
    entries: list[tuple[Path, float, int]] = []
    for path in candidates:
        try:
            stat = path.stat()
        except OSError as exc:
            notes.append(f"skipped unreadable log `{path}`: {exc}")
            continue
        entries.append((path, stat.st_mtime, stat.st_size))

    cutoff = moment - retention_days * 86400 if retention_days > 0 else None
    survivors: list[tuple[Path, float, int]] = []
    for path, mtime, size in entries:
        if cutoff is not None and mtime < cutoff:
            try:
                path.unlink()
                removed.append(str(path))
                removed_bytes += size
            except OSError as exc:
                notes.append(f"could not remove expired log `{path}`: {exc}")
                survivors.append((path, mtime, size))
        else:
            survivors.append((path, mtime, size))

    if log_max_bytes > 0:
        total = sum(size for _, _, size in survivors)
        # Oldest first so the freshest telemetry survives the cap.
        for path, _mtime, size in sorted(survivors, key=lambda e: e[1]):
            if total <= log_max_bytes:
                break
            try:
                path.unlink()
                removed.append(str(path))
                removed_bytes += size
                total -= size
                survivors = [e for e in survivors if e[0] != path]
            except OSError as exc:
                notes.append(f"could not enforce size cap on `{path}`: {exc}")
                break

    retained = [(p, s) for p, _, s in survivors]
    retained_bytes = sum(s for _, s in retained)

    metrics_trimmed = False
    metrics_removed = 0
    metrics_retained = 0
    if metrics_path.is_file():
        try:
            raw_lines = metrics_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            notes.append(f"could not read metrics `{metrics_path}`: {exc}")
            raw_lines = []
        kept: list[str] = []
        for line in raw_lines:
            if not line.strip():
                continue
            if cutoff is not None:
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    # Malformed lines are crash-recovery evidence: retain
                    # them here; rotation by size still applies below.
                    kept.append(line)
                    continue
                stamp = _parse_record_time(
                    data.get("ended_at") if isinstance(data, dict) else None
                ) or _parse_record_time(
                    data.get("started_at") if isinstance(data, dict) else None
                )
                if stamp is not None and stamp < cutoff:
                    metrics_removed += 1
                    metrics_trimmed = True
                    continue
            kept.append(line)
        metrics_retained = len(kept)
        needs_size_trim = (
            metrics_max_bytes > 0 and metrics_path.stat().st_size > metrics_max_bytes
        ) or metrics_trimmed
        if needs_size_trim:
            # Newest lines survive: drop oldest until the byte cap holds.
            # When only retention applied, `kept` is already the retained set.
            if metrics_max_bytes > 0:
                encoded = [(ln, len((ln + "\n").encode("utf-8"))) for ln in kept]
                total_m = sum(size for _, size in encoded)
                drop = 0
                while encoded and total_m > metrics_max_bytes:
                    _, size = encoded.pop(0)
                    total_m -= size
                    drop += 1
                if drop:
                    metrics_removed += drop
                    metrics_trimmed = True
                    kept = [ln for ln, _ in encoded]
                    metrics_retained = len(kept)
            try:
                tmp_fd, tmp_name = tempfile.mkstemp(
                    dir=str(metrics_path.parent),
                    prefix=".metrics.",
                    suffix=".tmp",
                )
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
                    for ln in kept:
                        handle.write(ln + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_name, metrics_path)
                ensure_secure_permissions(metrics_path)
            except OSError as exc:
                notes.append(f"could not rewrite metrics `{metrics_path}`: {exc}")
                with contextlib.suppress(OSError):
                    os.unlink(tmp_name)
        else:
            metrics_retained = len([ln for ln in raw_lines if ln.strip()])
    return RetentionReport(
        removed_logs=removed,
        removed_bytes=removed_bytes,
        retained_logs=len(retained),
        retained_bytes=retained_bytes,
        metrics_trimmed=metrics_trimmed,
        metrics_removed_lines=metrics_removed,
        metrics_retained_lines=metrics_retained,
        notes=notes,
    )


@dataclasses.dataclass
class ExportReport:
    files: int
    total_bytes: int
    destination: str
    notes: list[str]

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def export_logs(
    runs_dir: Path,
    metrics_path: Path,
    dest: Path,
    max_bytes: int = 52428800,
) -> ExportReport:
    """Copy telemetry (runs/ + metrics.jsonl) into `dest`, bounded by size.

    Only telemetry is exported: handoff, state, config, and lock files are
    never included. Refuses with OSError when the payload exceeds
    `max_bytes` so an unbounded export cannot fill the disk. Logs on disk
    are already redacted at write time; no secret is reconstructed here.
    """
    files: list[Path] = _iter_log_files(runs_dir)
    total = 0
    for path in files:
        try:
            total += path.stat().st_size
        except OSError:
            continue
    try:
        metrics_size = metrics_path.stat().st_size if metrics_path.is_file() else 0
    except OSError:
        metrics_size = 0
    total += metrics_size
    if max_bytes > 0 and total > max_bytes:
        raise OSError(
            f"refused: telemetry export is {total} bytes, "
            f"above the {max_bytes}-byte bound; prune logs first"
        )
    notes: list[str] = []
    dest_runs = dest / RUNS_DIRNAME
    dest_runs.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in files:
        try:
            rel = path.relative_to(runs_dir)
        except ValueError:
            continue
        target = dest_runs / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(path, target)
            count += 1
        except OSError as exc:
            notes.append(f"skipped `{path}`: {exc}")
    if metrics_path.is_file():
        try:
            shutil.copy2(metrics_path, dest / METRICS_FILENAME)
            count += 1
        except OSError as exc:
            notes.append(f"skipped metrics: {exc}")
    return ExportReport(
        files=count, total_bytes=total, destination=str(dest), notes=notes
    )
