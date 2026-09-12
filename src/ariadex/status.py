"""Operator status projection from durable state and recent records.

Derived only from persisted state, handoff, and metrics: it never implies
PASS from an absent verification record.
"""

from __future__ import annotations

from datetime import datetime, timezone


def format_elapsed(total_seconds: float) -> str:
    total = max(0, int(total_seconds))
    if total < 60:
        return f"{total}s"
    minutes, seconds = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return f"{hours}h{minutes:02d}m"
    return f"{hours // 24}d{(hours % 24):02d}h"


def elapsed_since(updated_at: str, now: datetime | None = None) -> str:
    try:
        updated = datetime.fromisoformat(updated_at)
    except (ValueError, TypeError):
        return "unknown"
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return format_elapsed((now - updated).total_seconds())


def tests_summary(latest: dict | None) -> str:
    if latest is None:
        return "no verification record"
    validation = latest.get("validation_result", "unknown")
    exit_code = latest.get("exit_code", "n/a")
    if exit_code is None:
        exit_code = "n/a"
    return f"{validation} (exit {exit_code})"


def render_status(
    *,
    mode: str,
    agent: str,
    spec: str | None,
    session: str,
    context_strategy: str,
    elapsed: str,
    open_count: int,
    blocked_count: int,
    tests: str,
    next_action: str | None,
) -> str:
    return "\n".join(
        [
            f"mode: {mode}",
            f"agent: {agent}",
            f"spec: {spec or '(none)'}",
            f"session: {session}",
            f"context: {context_strategy}",
            f"elapsed: {elapsed}",
            f"unresolved: open={open_count} blocked={blocked_count}",
            f"tests: {tests}",
            f"next: {next_action or '(none)'}",
        ]
    )
