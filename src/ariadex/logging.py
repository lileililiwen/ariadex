"""Session run logs, metrics records, and secret redaction.

Run logs live under `.ariadex/runs/<session-id>/` and record input,
output, session, spec, start/end times, exit code, validation result, and
reset reason. Metrics append one JSON object per cycle to
`.ariadex/metrics.jsonl` with the same identity plus retry count and usage:
`usage: unavailable` when the adapter cannot report usage, never an
invented estimate.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

RUNS_DIRNAME = "runs"
METRICS_FILENAME = "metrics.jsonl"

REDACTED = "<redacted>"

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9\-_]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?"
        r"-----END [A-Z ]*PRIVATE KEY-----"
    ),
    re.compile(
        r"(?i)((?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*)\S+"
    ),
]


def redact(text: str) -> str:
    """Replace likely secrets with `<redacted>`; leave other text intact."""
    if not text:
        return text
    redacted = text
    redacted = _SECRET_PATTERNS[0].sub(REDACTED, redacted)
    redacted = _SECRET_PATTERNS[1].sub(REDACTED, redacted)
    redacted = _SECRET_PATTERNS[2].sub(REDACTED, redacted)
    redacted = _SECRET_PATTERNS[3].sub(r"\1" + REDACTED, redacted)
    return redacted


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def render_log(record: RunLogRecord) -> str:
    exit_code = "n/a" if record.exit_code is None else str(record.exit_code)
    return (
        f"session: {record.session_id}\n"
        f"spec: {record.spec or '(none)'}\n"
        f"action: {record.action}\n"
        f"started: {record.started_at}\n"
        f"ended: {record.ended_at}\n"
        f"exit code: {exit_code}\n"
        f"validation: {record.validation_result}\n"
        f"reset: {record.reset_reason or '(none)'}\n"
        f"retries: {record.retry_count}\n"
        f"--- input ---\n{record.input}\n"
        f"--- output ---\n{record.output}\n"
    )


def write_run_log(runs_dir: Path, record: RunLogRecord) -> Path:
    """Write one cycle log atomically; returns the log path."""
    if not record.started_at:
        record.started_at = now_iso()
    if not record.ended_at:
        record.ended_at = now_iso()
    record.input = redact(record.input)
    record.output = redact(record.output)
    session_dir = runs_dir / (record.session_id or "unknown-session")
    session_dir.mkdir(parents=True, exist_ok=True)
    stamp = record.ended_at.replace(":", "").replace("+", "")
    name = f"{stamp}-{uuid.uuid4().hex[:6]}.log"
    path = session_dir / name
    fd, tmp_name = tempfile.mkstemp(
        dir=str(session_dir), prefix=".run.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(render_log(record))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return path


def append_metrics(path: Path, record: dict) -> None:
    """Append one JSON object per line; creates parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


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
