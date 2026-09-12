"""Durable runtime state with atomic replacement.

State records mode, session identifier, current spec, unresolved count,
and last update time. Supported modes are AUTO, MANUAL, and PAUSE.
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

STATE_REL_PATH = Path(".ariadex") / "state.json"

MODES = ("AUTO", "MANUAL", "PAUSE")


class StateError(Exception):
    """Raised when durable state is missing, unreadable, or invalid."""


@dataclasses.dataclass
class State:
    mode: str = "MANUAL"
    session_id: str = ""
    current_spec: str | None = None
    unresolved_count: int = 0
    updated_at: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def state_path(project_dir: Path) -> Path:
    return project_dir / STATE_REL_PATH


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initial_state() -> State:
    return State(
        mode="MANUAL",
        session_id=new_session_id(),
        current_spec=None,
        unresolved_count=0,
        updated_at=now_iso(),
    )


def validate_state(state: State, source: str = "state") -> State:
    if state.mode not in MODES:
        raise StateError(
            f"invalid mode `{state.mode}` in {source}: expected one of "
            f"{', '.join(MODES)}"
        )
    if not state.session_id:
        raise StateError(f"invalid session_id in {source}: must not be empty")
    if state.unresolved_count < 0:
        raise StateError(
            f"invalid unresolved_count `{state.unresolved_count}` in {source}: "
            "must be >= 0"
        )
    return state


def read(project_dir: Path) -> State:
    path = state_path(project_dir)
    if not path.is_file():
        raise StateError(
            f"missing runtime state at {STATE_REL_PATH}; run `ariadex init` first"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StateError(f"invalid runtime state in {STATE_REL_PATH}: {exc}") from exc
    if not isinstance(raw, dict):
        raise StateError(
            f"invalid runtime state in {STATE_REL_PATH}: object required"
        )
    known = {field.name for field in dataclasses.fields(State)}
    state = State(
        **{key: value for key, value in raw.items() if key in known}
    )
    return validate_state(state, source=str(STATE_REL_PATH))


def write(project_dir: Path, state: State) -> State:
    """Persist state atomically (temp file + rename). Updates updated_at."""
    validate_state(state)
    state.updated_at = now_iso()
    path = state_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".state.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state.to_dict(), handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return state
