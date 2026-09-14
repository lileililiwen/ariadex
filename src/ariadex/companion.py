"""Opt-in desktop companion: floating yield control over daemon IPC.

The companion is a small always-on-top mini-player (Linux X11 + Tkinter
first) that lets a human pause, resume, or inspect the resident daemon
without taking focus away from the editor or Coding CLI. Every daemon
mutation goes through the typed local IPC protocol (`status`, `pause`,
`resume`, `stop`, `wake`); the companion never writes Ariadex state,
controls the lease, touches tmux, or injects terminal input.

Tkinter and X11 are imported lazily so headless hosts fail closed with an
honest unsupported message instead of crashing at import time.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

DEFAULT_HOTKEY = "Ctrl+Esc"

#: Bounded companion poll of daemon status (no busy-loop).
POLL_INTERVAL_S = 2.0

#: Collapsed mini-player target width in pixels.
WIDGET_WIDTH = 360
WIDGET_COLLAPSED_HEIGHT = 116
WIDGET_EXPANDED_HEIGHT = 320
WIDGET_EXPANDED_WINDOW_HEIGHT = 340

#: Hub window heights: the hub detail panel carries a tab bar plus five
#: detail rows, so the single-widget heights would clip the controls row
#: out of the window (measured 219px collapsed / 390px expanded on Tk).
HUB_COLLAPSED_HEIGHT = 230
HUB_EXPANDED_HEIGHT = 400

#: Safety margin in pixels keeping the floating widget inside the usable
#: virtual-screen bounds (title bar and close control stay reachable).
WIDGET_SCREEN_MARGIN = 8

#: Bounded robot activity lines rendered in the expanded widget log.
ROBOT_LOG_VIEW_LINES = 20

HOTKEY_MODIFIERS = ("Ctrl", "Shift", "Alt", "Super")

SUPPORTED_SESSIONS = ("x11",)


class CompanionError(Exception):
    """A companion, hotkey, or IPC failure (fail-closed, no input sent)."""


@dataclasses.dataclass
class DesktopInfo:
    session: str  # x11 | wayland | macos | windows | headless | unknown
    supported: bool
    detail: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def detect_desktop(env: dict | None = None) -> DesktopInfo:
    """Classify the desktop session without touching any display server."""
    environ = env if env is not None else dict(os.environ)
    platform = sys.platform
    if platform == "darwin":
        return DesktopInfo(
            "macos", False, "macOS adapter not implemented; terminal controls apply"
        )
    if platform == "win32":
        return DesktopInfo(
            "windows",
            False,
            "Windows adapter not implemented; terminal controls apply",
        )
    if platform != "linux":
        return DesktopInfo(
            "unknown", False, f"platform `{platform}` has no companion adapter"
        )
    session_type = (environ.get("XDG_SESSION_TYPE") or "").lower()
    if session_type == "wayland" or (
        not session_type and environ.get("WAYLAND_DISPLAY")
    ):
        return DesktopInfo(
            "wayland",
            False,
            "Wayland adapter not implemented; terminal controls apply",
        )
    if session_type in ("x11", "") and environ.get("DISPLAY"):
        return DesktopInfo(
            "x11", True, "Linux X11 session with Tkinter companion support"
        )
    return DesktopInfo("headless", False, "no display session; terminal controls apply")


def tkinter_available() -> bool:
    """Whether the Tkinter UI toolkit imports."""
    try:
        import tkinter  # noqa: F401

        return True
    except ImportError:
        return False


def display_available() -> bool:
    """Whether this process can create and destroy a Tk window."""
    if not tkinter_available():
        return False
    import tkinter as tk

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.update_idletasks()
    except Exception:
        return False
    finally:
        with contextlib.suppress(Exception):
            if root is not None:
                root.destroy()
    return True


def parse_hotkey(text: str) -> tuple[frozenset[str], str]:
    """Split `Ctrl+Esc` style configuration into (modifiers, key).

    Raises CompanionError for empty input, unknown modifiers, missing keys,
    or multi-character keys that are not recognized names.
    """
    parts = [part.strip() for part in (text or "").split("+")]
    parts = [part for part in parts if part]
    if not parts:
        raise CompanionError("hotkey is empty; expected e.g. `Ctrl+Esc`")
    *mods, key = parts
    canonical_mods: list[str] = []
    for mod in mods:
        match = next(
            (known for known in HOTKEY_MODIFIERS if known.lower() == mod.lower()),
            None,
        )
        if match is None:
            raise CompanionError(
                f"unknown hotkey modifier `{mod}`: expected one of "
                f"{', '.join(HOTKEY_MODIFIERS)}"
            )
        if match not in canonical_mods:
            canonical_mods.append(match)
    if not key:
        raise CompanionError(f"hotkey `{text}` names no key")
    if len(key) > 1 and not key[0].isalnum() and key not in ("Esc",):
        raise CompanionError(f"hotkey key `{key}` is not a recognized name")
    return frozenset(canonical_mods), key


class HotkeyAdapter(Protocol):
    """OS-specific global-hotkey registration boundary."""

    name: str

    def register(self, hotkey: str, callback: Callable[[], None]) -> None:
        """Grab the hotkey; raise CompanionError when unsupported/failing."""
        ...  # pragma: no cover - interface only

    def unregister(self) -> None:
        """Release any grab. Never raises."""
        ...  # pragma: no cover - interface only


class UnsupportedHotkeyAdapter:
    """Fallback adapter: registration always refuses with a repair action."""

    def __init__(self, session: str) -> None:
        self.name = f"unsupported-{session}"

    def register(self, hotkey: str, callback: Callable[[], None]) -> None:
        raise CompanionError(
            f"global hotkey is unsupported on `{self.name}`; "
            "use `ariadex pause` / `ariadex resume` in a terminal"
        )

    def unregister(self) -> None:
        return None


class X11HotkeyAdapter:
    """Linux X11 global hotkey via isolated ctypes libX11 access.

    Grabs exactly one configured key combination on the root window and
    invokes the callback on KeyPress. Captures nothing else: ordinary
    keyboard input keeps flowing to the focused application.
    """

    name = "x11"

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._display: object = None

    def register(self, hotkey: str, callback: Callable[[], None]) -> None:
        import ctypes
        import ctypes.util

        modifiers, key = parse_hotkey(hotkey)
        libname = ctypes.util.find_library("X11")
        if libname is None:
            raise CompanionError(
                "libX11 not found; install the X11 client library or use "
                "`ariadex pause` / `ariadex resume`"
            )
        try:
            lib = ctypes.CDLL(libname)
        except OSError as exc:
            raise CompanionError(f"cannot load libX11 ({exc})") from exc
        lib.XOpenDisplay.restype = ctypes.c_void_p
        display = lib.XOpenDisplay(None)
        if not display:
            raise CompanionError(
                "cannot open the X display; is the X11 session running?"
            )
        lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        lib.XDefaultRootWindow.restype = ctypes.c_ulong
        lib.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        lib.XKeysymToKeycode.restype = ctypes.c_uint
        keysym = _keysym_for(key)
        keycode = lib.XKeysymToKeycode(display, keysym)
        if not keycode:
            lib.XCloseDisplay(display)
            raise CompanionError(f"hotkey key `{key}` has no X keycode")
        # XGrabKey reports failure asynchronously (BadAccess when the
        # combination is already taken), so install a scoped error handler
        # and synchronize: any protocol error during the grabs refuses
        # registration instead of pretending the hotkey is active.
        grab_failed = ctypes.c_int(0)
        HandlerType = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)

        @HandlerType
        def _on_x_error(_display: object, _event: object) -> int:
            grab_failed.value = 1
            return 0

        lib.XSetErrorHandler.argtypes = [HandlerType]
        lib.XSetErrorHandler.restype = ctypes.c_void_p
        lib.XGrabKey.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]
        lib.XGrabKey.restype = None
        lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.XSync.restype = ctypes.c_int
        root = lib.XDefaultRootWindow(display)
        previous = lib.XSetErrorHandler(_on_x_error)
        try:
            for mask in _grab_masks(modifiers):
                lib.XGrabKey(display, keycode, mask, root, True, 1, 1)
            lib.XSync(display, False)
        finally:
            with contextlib.suppress(Exception):
                if previous:
                    lib.XSetErrorHandler(
                        ctypes.cast(ctypes.c_void_p(previous), HandlerType)
                    )
                else:
                    lib.XSetErrorHandler(None)
        if grab_failed.value:
            lib.XCloseDisplay(display)
            raise CompanionError(
                f"global hotkey `{hotkey}` is already taken or rejected; "
                "configure another with `--hotkey`"
            )
        self._display = display
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._watch,
            args=(lib, display, keycode, callback),
            daemon=True,
        )
        self._thread.start()

    def _watch(
        self, lib: object, display: object, keycode: int, callback: Callable[[], None]
    ) -> None:
        import ctypes

        _, XEvent = _x_event_classes()

        lib.XPending.argtypes = [ctypes.c_void_p]  # type: ignore[attr-defined]
        lib.XPending.restype = ctypes.c_int  # type: ignore[attr-defined]
        lib.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.POINTER(XEvent)]  # type: ignore[attr-defined]
        while not self._stop.is_set():
            try:
                pending = lib.XPending(display)  # type: ignore[attr-defined]
            except Exception:
                break
            if not pending:
                self._stop.wait(0.05)
                continue
            event = XEvent()
            try:
                lib.XNextEvent(display, ctypes.byref(event))  # type: ignore[attr-defined]
            except Exception:
                break
            # KeyPress == 2; only the grabbed keycode invokes the callback.
            if event.key.type == 2 and event.key.keycode == keycode:
                with contextlib.suppress(Exception):
                    callback()

    def unregister(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2.0)
        display, self._display = self._display, None
        if display is not None:
            with contextlib.suppress(Exception):
                import ctypes
                import ctypes.util

                libname = ctypes.util.find_library("X11")
                if libname is not None:
                    lib = ctypes.CDLL(libname)
                    lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
                    lib.XCloseDisplay(display)


def _keysym_for(key: str) -> int:
    """Map a configured key name to its X keysym (Latin-1 + specials)."""
    specials = {"Esc": 0xFF1B, "Space": 0x0020, "Tab": 0xFF09, "Return": 0xFF0D}
    if key in specials:
        return specials[key]
    if key.startswith("F") and key[1:].isdigit():
        number = int(key[1:])
        if 1 <= number <= 35:
            return 0xFFBE + number - 1
    if len(key) == 1:
        return ord(key)
    raise CompanionError(f"hotkey key `{key}` has no known keysym")


def _grab_masks(modifiers: frozenset[str]) -> list[int]:
    """Modifier masks incl. NumLock/CapsLock combinations for reliable grabs."""
    base = 0
    mapping = {"Shift": 1, "Ctrl": 4, "Alt": 8, "Super": 64}
    for mod in modifiers:
        base |= mapping[mod]
    # NumLock (Mod2) and CapsLock (Lock) variants so the grab holds
    # regardless of lock-key state.
    return [base, base | 2, base | 16, base | 18]


def adapter_for_session(session: str) -> HotkeyAdapter:
    """Select the OS adapter; unsupported sessions refuse explicitly."""
    if session in SUPPORTED_SESSIONS:
        return X11HotkeyAdapter()
    return UnsupportedHotkeyAdapter(session)


def _x_event_classes() -> tuple[type, type]:
    """X11 event layouts for the hotkey watch loop (module-level for tests)."""
    import ctypes

    class XKeyEvent(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_int),
            ("serial", ctypes.c_ulong),
            ("send_event", ctypes.c_int),
            ("display", ctypes.c_void_p),
            ("window", ctypes.c_ulong),
            ("root", ctypes.c_ulong),
            ("subwindow", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("x", ctypes.c_int),
            ("y", ctypes.c_int),
            ("x_root", ctypes.c_int),
            ("y_root", ctypes.c_int),
            ("state", ctypes.c_uint),
            ("keycode", ctypes.c_uint),
            ("same_screen", ctypes.c_int),
        ]

    class XEvent(ctypes.Union):
        _fields_ = [("key", XKeyEvent), ("pad", ctypes.c_long * 24)]

    return XKeyEvent, XEvent


def user_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ariadex" / "companion.json"


def load_user_config() -> dict:
    """Per-user companion settings (hotkey + geometry); fail-soft defaults."""
    path = user_config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_user_config(values: dict) -> bool:
    """Persist per-user settings atomically. Returns False when unwritable."""
    path = user_config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        current = load_user_config()
        current.update(values)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=".companion.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(current, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise
        return True
    except OSError:
        return False


def configured_hotkey(override: str | None = None) -> str:
    """Effective hotkey: CLI override, else per-user config, else default."""
    if override:
        return override
    saved = load_user_config().get("hotkey")
    return str(saved) if saved else DEFAULT_HOTKEY


class CompanionClient:
    """Daemon IPC client for the companion. Mutations use IPC only.

    The client never reads Ariadex state files, never touches the
    scheduling lease, and never sends tmux input: every call is one
    bounded typed request over the project socket.
    """

    def __init__(self, project_dir: Path, timeout_s: float = 5.0) -> None:
        self.project_dir = project_dir
        self.timeout_s = timeout_s

    def _call(self, request_type: str) -> dict:
        from . import daemon as daemon_mod

        try:
            response = daemon_mod.send_request(
                self.project_dir, request_type, timeout_s=self.timeout_s
            )
        except daemon_mod.DaemonError as exc:
            raise CompanionError(
                f"daemon unreachable for `{request_type}`: {exc}"
            ) from exc
        if not isinstance(response, dict) or not response.get("ok"):
            detail = ""
            if isinstance(response, dict) and response.get("error"):
                detail = f": {response['error']}"
            # Never fabricate a state change: report the failure instead.
            raise CompanionError(f"daemon refused `{request_type}`{detail}")
        state = response.get("state")
        if not isinstance(state, dict):
            raise CompanionError(
                f"daemon returned no state for `{request_type}`; nothing was assumed"
            )
        return state

    def refresh(self) -> dict:
        """Read-only status poll."""
        return self._call("status")

    def pause(self) -> dict:
        """Yield: typed pause request, never terminal input."""
        return self._call("pause")

    def resume(self) -> dict:
        """Play: typed resume request (daemon reconciles before scheduling)."""
        return self._call("resume")

    def stop(self) -> dict:
        """Typed stop request (UI confirms before calling)."""
        return self._call("stop")

    def reconcile(self) -> dict:
        """Re-check durable reconciliation via a bounded wake request."""
        return self._call("wake")


INDICATORS = ("working", "paused", "manual", "blocked", "stopped", "completed")


def build_view_model(state: dict) -> dict:
    """Map one IPC status response to widget state (pure, no I/O).

    Every indicator has a text equivalent; colors are decorative only.
    Actions follow daemon truth: pause only when AUTO/working, play only
    when PAUSE/manual, stop only while the daemon is alive.
    """
    alive = bool(state.get("alive"))
    mode = str(state.get("mode", "unknown"))
    next_action = state.get("next_action")
    next_text = "" if next_action is None else str(next_action)
    open_count = int(state.get("open_count", 0) or 0)
    blocked_count = int(state.get("blocked_count", 0) or 0)
    if not alive:
        indicator = "stopped"
    elif mode == "PAUSE":
        indicator = "paused"
    elif blocked_count > 0 and "blocked" in next_text:
        indicator = "blocked"
    elif mode == "MANUAL":
        indicator = "manual"
    elif "idle" in next_text:
        indicator = "completed"
    elif mode == "AUTO":
        indicator = "working"
    else:
        indicator = "manual"
    work_label = next_text or "(no pending work)"
    if open_count or blocked_count:
        work_label += f" — {open_count} open, {blocked_count} blocked"
    actions = {
        "pause": alive and mode == "AUTO",
        "play": alive and mode in ("PAUSE", "MANUAL"),
        "stop": alive,
        "reconcile": alive,
    }
    context_summary = ""
    context_latest = ""
    managed_context: dict | None = None
    if isinstance(state.get("diagnostic_context"), dict):
        managed_context = build_managed_context(state)
        context_summary = str(managed_context.get("summary", ""))
        context_latest = str(managed_context.get("latest_text", ""))
        if context_summary:
            work_label += f"\n{context_summary}"
    return {
        "indicator": indicator,
        "indicator_text": indicator.upper(),
        "mode": mode,
        "alive": alive,
        "work_label": work_label,
        "actions": actions,
        "reconciliation_pending": indicator == "paused",
        "failure": None,
        "context_summary": context_summary,
        "context_latest": context_latest,
        "managed_context": managed_context,
    }


def failure_view_model(reason: str) -> dict:
    """Visible failure state: report, never fabricate daemon truth."""
    model = build_view_model({})
    model["indicator"] = "stopped"
    model["indicator_text"] = "UNREACHABLE"
    model["work_label"] = "(daemon unreachable)"
    model["failure"] = reason
    return model


def format_view_text(model: dict) -> str:
    """Text status equivalent of the widget (screen-reader / headless use)."""
    lines = [
        f"companion: {model.get('indicator_text')} (mode {model.get('mode')})",
        f"work: {model.get('work_label')}",
    ]
    context_summary = str(model.get("context_summary", "") or "")
    if context_summary:
        lines.append(f"context: {context_summary}")
    latest = str(model.get("context_latest", "") or "")
    if latest:
        lines.append(f"latest: {latest}")
    actions = model.get("actions", {})
    enabled = sorted(name for name, on in actions.items() if on)
    lines.append(f"actions: {', '.join(enabled) if enabled else 'none available'}")
    if model.get("reconciliation_pending"):
        lines.append("reconciliation: pending — play resynchronizes before scheduling")
    if model.get("failure"):
        lines.append(f"failure: {model['failure']}")
    return "\n".join(lines)


#: Bounded event lines rendered in the managed widget log.
MANAGED_LOG_VIEW_LINES = 20

#: Per-field bound for displayed and copied context text.
CONTEXT_FIELD_CHARS = 280


def _context_field(value: object, limit: int = CONTEXT_FIELD_CHARS) -> str:
    """Redacted, truncated display field (never raw secrets or unbounded)."""
    from .logging import redact

    text = redact(str(value or ""))
    if len(text) > limit:
        text = text[:limit] + f"... [truncated {len(text) - limit} chars]"
    return text


def build_managed_context(state: dict) -> dict:
    """Project one IPC status response to managed diagnostic context.

    Pure, no I/O: combines the watcher's durable current spec, OpenSpec
    active-change/task summary, phase/next decision, latest event, and a
    bounded chronological event list. HANDOFF unresolved counts stay
    labeled independently from OpenSpec task counts. Missing pieces are
    honest empty/unreachable notes, never fabricated values.
    """
    raw = state.get("diagnostic_context")
    context = raw if isinstance(raw, dict) else {}
    current_spec = context.get("current_spec")
    current = str(current_spec) if current_spec else "(none recorded)"
    queue_raw = context.get("queue")
    queue: list[dict] = []
    if isinstance(queue_raw, list):
        for entry in queue_raw[:MANAGED_LOG_VIEW_LINES]:
            if not isinstance(entry, dict):
                continue
            try:
                completed = int(entry.get("completed", 0) or 0)
                total = int(entry.get("total", 0) or 0)
            except (TypeError, ValueError):
                continue
            queue.append(
                {
                    "name": str(entry.get("name", "?")),
                    "completed": completed,
                    "total": total,
                }
            )
    selected = next((item for item in queue if item["name"] == current), None)
    if selected is not None:
        task_summary = f"{selected['completed']}/{selected['total']} OpenSpec tasks"
    elif queue:
        task_summary = (
            f"{len(queue)} active OpenSpec change(s); "
            "recorded current spec not in queue"
        )
    else:
        task_summary = "no active OpenSpec changes reported"
    events_raw = context.get("recent_events")
    events: list[dict] = []
    if isinstance(events_raw, list):
        for entry in events_raw[-MANAGED_LOG_VIEW_LINES:]:
            if not isinstance(entry, dict):
                continue
            queue_raw = entry.get("active_queue")
            queue_names = (
                [str(name) for name in queue_raw if name]
                if isinstance(queue_raw, list)
                else []
            )
            try:
                event_open = int(entry.get("open_tasks", 0) or 0)
            except (TypeError, ValueError):
                event_open = 0
            events.append(
                {
                    "at": _context_field(entry.get("at", "?"), 64),
                    "category": _context_field(entry.get("category", "?"), 64),
                    "action": _context_field(entry.get("action", "")),
                    "result": _context_field(entry.get("result", ""), 120),
                    "message": _context_field(entry.get("message", "")),
                    "current_spec": _context_field(entry.get("current_spec") or ""),
                    "classification": _context_field(
                        entry.get("classification", ""), 64
                    ),
                    "decision": _context_field(entry.get("decision", ""), 64),
                    "blocker": _context_field(entry.get("blocker", "")),
                    "operation": _context_field(entry.get("operation", ""), 64),
                    "next_action": _context_field(entry.get("next_action", "")),
                    "evidence_source": _context_field(
                        entry.get("evidence_source", ""), 64
                    ),
                    "requested_path": _context_field(entry.get("requested_path", "")),
                    "normalized_path": _context_field(entry.get("normalized_path", "")),
                    "policy": _context_field(entry.get("policy", ""), 64),
                    "open_tasks": event_open,
                    "active_queue": queue_names[:MANAGED_LOG_VIEW_LINES],
                }
            )
    latest_raw = context.get("latest_event")
    latest: dict | None = None
    if isinstance(latest_raw, dict):
        latest = {
            "category": _context_field(latest_raw.get("category", "?"), 64),
            "message": _context_field(latest_raw.get("message", "")),
            "decision": _context_field(latest_raw.get("decision", ""), 64),
            "blocker": _context_field(latest_raw.get("blocker", "")),
            "operation": _context_field(latest_raw.get("operation", ""), 64),
            "next_action": _context_field(latest_raw.get("next_action", "")),
        }
    elif events:
        last = events[-1]
        latest = {
            "category": last["category"],
            "message": last["message"],
            "decision": last.get("decision", ""),
            "blocker": last.get("blocker", ""),
            "operation": last.get("operation", ""),
            "next_action": last.get("next_action", ""),
        }
    if latest:
        latest_text = f"{latest['category']}: {latest['message']}"
        if latest.get("decision"):
            latest_text += f" [decision={latest['decision']}]"
        if latest.get("blocker"):
            latest_text += f" [blocker={latest['blocker']}]"
        if latest.get("next_action"):
            latest_text += f" [next={latest['next_action']}]"
    else:
        latest_text = "no events yet"
    notes_raw = context.get("notes")
    notes = (
        [_context_field(note) for note in notes_raw if note]
        if isinstance(notes_raw, list)
        else []
    )
    summary = f"{current} — {task_summary}"
    next_decision = _context_field(state.get("next_action", ""), 200)
    return {
        "current_spec": current,
        "queue": queue,
        "task_summary": task_summary,
        "summary": summary,
        "next_decision": next_decision,
        "latest_event": latest,
        "latest_text": latest_text,
        "events": events,
        "notes": notes,
    }


def format_managed_log_text(projection: dict) -> str:
    """Chronological read-only log text for the expanded widget and copy."""
    lines = [
        f"current spec: {projection.get('current_spec', '(none recorded)')}",
        f"tasks: {projection.get('task_summary', 'unknown')}",
    ]
    for item in projection.get("queue", []):
        lines.append(
            f"- {item.get('name')}: "
            f"{item.get('completed')}/{item.get('total')} OpenSpec tasks"
        )
    events = projection.get("events", [])
    if events:
        lines.append("events:")
        for entry in events:
            lines.append(
                f"- {entry.get('at', '?')} [{entry.get('category', '?')}] "
                f"{entry.get('action', '')}"
                + (f" => {entry.get('result', '')}" if entry.get("result") else "")
                + (f" :: {entry.get('message', '')}" if entry.get("message") else "")
            )
            details: list[str] = []
            if entry.get("classification"):
                details.append(f"classification={entry['classification']}")
            if entry.get("decision"):
                details.append(f"decision={entry['decision']}")
            if entry.get("current_spec"):
                details.append(f"spec={entry['current_spec']}")
            if entry.get("evidence_source"):
                details.append(f"evidence={entry['evidence_source']}")
            queue_names = entry.get("active_queue", [])
            if queue_names:
                names = ", ".join(str(name) for name in queue_names)
                details.append(f"queue=[{names}]")
            if details:
                lines.append(f"  {'; '.join(details)}")
            if entry.get("blocker"):
                lines.append(f"  blocker: {entry['blocker']}")
            if entry.get("operation"):
                lines.append(f"  operation: {entry['operation']}")
            permission_bits = []
            if entry.get("policy"):
                permission_bits.append(f"policy={entry['policy']}")
            decided_path = entry.get("normalized_path") or entry.get("requested_path")
            if decided_path:
                permission_bits.append(f"path={decided_path}")
            elif entry.get("requested_path"):
                permission_bits.append(f"path={entry['requested_path']}")
            if permission_bits:
                lines.append(f"  permission: {'; '.join(permission_bits)}")
            if entry.get("next_action"):
                lines.append(f"  next: {entry['next_action']}")
    else:
        lines.append("events: (none yet)")
    for note in projection.get("notes", []):
        lines.append(f"note: {note}")
    return "\n".join(lines)


def format_context_snapshot(projection: dict, state: dict) -> str:
    """Redacted copy-for-support snapshot: readable text, no secrets.

    Carries the project label, provider/session, current spec, OpenSpec
    queue snapshot, boundary decision, and recent events. Compatible with
    the diagnostic export: same schema version, current spec, per-change
    completed/total counts, and event categories.
    """
    from . import diagnostics as diagnostics_mod

    lines = [
        "ariadex diagnostic context "
        f"(schema v{diagnostics_mod.DIAGNOSTIC_SCHEMA_VERSION})",
        f"provider: {_context_field(state.get('provider', 'unknown'), 120)} @ "
        f"{_context_field(state.get('session', 'unknown'), 120)}",
        f"mode: {_context_field(state.get('mode', 'unknown'), 64)}",
        f"current spec: {projection.get('current_spec', '(none recorded)')}",
        f"tasks: {projection.get('task_summary', 'unknown')}",
        f"next decision: {projection.get('next_decision', 'unknown')}",
        "openspec queue:",
    ]
    queue = projection.get("queue", [])
    if queue:
        for item in queue:
            lines.append(
                f"- {item.get('name')}: "
                f"{item.get('completed')}/{item.get('total')} tasks complete"
            )
    else:
        lines.append("- (none reported)")
    open_count = state.get("open_count", "?")
    blocked_count = state.get("blocked_count", "?")
    lines.append(
        f"handoff unresolved (separate from OpenSpec tasks): "
        f"{open_count} open, {blocked_count} blocked"
    )
    lines.append("recent events:")
    events = projection.get("events", [])
    if events:
        for entry in events:
            lines.append(
                f"- {entry.get('at', '?')} [{entry.get('category', '?')}] "
                f"{entry.get('action', '')}"
                + (f" => {entry.get('result', '')}" if entry.get("result") else "")
                + (f" :: {entry.get('message', '')}" if entry.get("message") else "")
            )
            if entry.get("decision"):
                lines.append(f"  decision: {entry['decision']}")
            if entry.get("blocker"):
                lines.append(f"  blocker: {entry['blocker']}")
            permission_bits = []
            if entry.get("policy"):
                permission_bits.append(f"policy={entry['policy']}")
            decided_path = entry.get("normalized_path") or entry.get("requested_path")
            if decided_path:
                permission_bits.append(f"path={decided_path}")
            if permission_bits:
                lines.append(f"  permission: {'; '.join(permission_bits)}")
            if entry.get("next_action"):
                lines.append(f"  next: {entry['next_action']}")
    else:
        lines.append("- (none yet)")
    for note in projection.get("notes", []):
        lines.append(f"note: {note}")
    latest = projection.get("latest_event") or {}
    if isinstance(latest, dict) and latest.get("decision"):
        lines.append(f"latest decision: {latest.get('decision', '')}")
    if isinstance(latest, dict) and latest.get("blocker"):
        lines.append(f"latest blocker: {latest.get('blocker', '')}")
    if isinstance(latest, dict) and latest.get("next_action"):
        lines.append(f"latest next action: {latest.get('next_action', '')}")
    return "\n".join(lines)


def copy_to_clipboard(root: object, text: str) -> str | None:
    """Copy text via Tk's native clipboard; return an error or None on ok.

    Uses only Tk (`clipboard_clear`/`clipboard_append`); no `xclip`,
    `xsel`, or other prerequisite is required. Never raises.
    """
    try:
        root.clipboard_clear()  # type: ignore[attr-defined]
        root.clipboard_append(text)  # type: ignore[attr-defined]
        update = getattr(root, "update", None)
        if callable(update):
            update()
    except Exception as exc:
        return f"clipboard copy failed: {exc}"
    return None


def default_geometry(screen_width: int, screen_height: int) -> tuple[int, int]:
    """Middle-right placement for the collapsed widget."""
    x = max(0, screen_width - WIDGET_WIDTH - 24)
    y = max(0, screen_height // 2 - 60)
    return x, y


def virtual_screen_bounds(root: object) -> tuple[int, int, int, int]:
    """Usable virtual-screen bounds as (origin_x, origin_y, width, height).

    Uses Tk's virtual-root geometry so negative multi-monitor origins are
    supported. Falls back to the primary screen size with a zero origin.
    Never raises: geometry failures stay fail-soft for the caller.
    """
    try:
        width_fn = getattr(root, "winfo_screenwidth", None)
        height_fn = getattr(root, "winfo_screenheight", None)
        width = int(width_fn()) if callable(width_fn) else 0
        height = int(height_fn()) if callable(height_fn) else 0
        origin_x = 0
        origin_y = 0
        for attr, fallback in (
            ("winfo_vrootx", 0),
            ("winfo_vrooty", 0),
            ("winfo_vrootwidth", width),
            ("winfo_vrootheight", height),
        ):
            getter = getattr(root, attr, None)
            if not callable(getter):
                if attr == "winfo_vrootwidth":
                    width = int(width)
                elif attr == "winfo_vrootheight":
                    height = int(height)
                continue
            try:
                value = int(getter())
            except Exception:
                value = int(fallback)
            if attr == "winfo_vrootx":
                origin_x = value
            elif attr == "winfo_vrooty":
                origin_y = value
            elif attr == "winfo_vrootwidth":
                width = value
            else:
                height = value
        if width <= 0 or height <= 0:
            raise ValueError("unusable screen bounds")
        return origin_x, origin_y, width, height
    except Exception:
        try:
            width = int(root.winfo_screenwidth())  # type: ignore[attr-defined]
            height = int(root.winfo_screenheight())  # type: ignore[attr-defined]
        except Exception:
            width, height = 0, 0
        return 0, 0, max(0, width), max(0, height)


def clamp_widget_position(
    x: int,
    y: int,
    widget_width: int,
    widget_height: int,
    origin_x: int,
    origin_y: int,
    screen_width: int,
    screen_height: int,
    margin: int = WIDGET_SCREEN_MARGIN,
) -> tuple[int, int]:
    """Clamp a widget top-left corner inside the usable screen rectangle.

    Pure helper (no Tk access) covering negative origins and small screens.
    When the screen is smaller than the widget plus margins, the position
    clamps to the screen origin so the title bar and close control stay
    reachable instead of stranding the dialog off-screen.
    """
    try:
        x = int(x)
    except (TypeError, ValueError):
        x = int(origin_x)
    try:
        y = int(y)
    except (TypeError, ValueError):
        y = int(origin_y)
    try:
        margin = max(0, int(margin))
    except (TypeError, ValueError):
        margin = WIDGET_SCREEN_MARGIN
    widget_width = max(1, int(widget_width))
    widget_height = max(1, int(widget_height))
    min_x = int(origin_x) + margin
    min_y = int(origin_y) + margin
    max_x = int(origin_x) + int(screen_width) - widget_width - margin
    max_y = int(origin_y) + int(screen_height) - widget_height - margin
    if max_x < min_x or max_y < min_y:
        return int(origin_x), int(origin_y)
    return max(min_x, min(max_x, x)), max(min_y, min(max_y, y))


def clamp_to_screen(
    root: object, x: int, y: int, widget_width: int, widget_height: int
) -> tuple[int, int]:
    """Clamp (x, y) to the root's virtual-screen bounds; fail-soft."""
    try:
        origin_x, origin_y, screen_width, screen_height = virtual_screen_bounds(root)
        if screen_width <= 0 or screen_height <= 0:
            return int(x), int(y)
        return clamp_widget_position(
            x,
            y,
            widget_width,
            widget_height,
            origin_x,
            origin_y,
            screen_width,
            screen_height,
        )
    except Exception:
        try:
            return int(x), int(y)
        except (TypeError, ValueError):
            return 0, 0


def open_editor(project_dir: Path, editor: str | None = None) -> str:
    """Open the configured editor on the project (no daemon involvement).

    Uses `$EDITOR` (or an explicit override); refuses when unset rather
    than guessing. The editor is a detached convenience launcher: the
    daemon remains responsible for all scheduling state.
    """
    import subprocess

    command = (editor or os.environ.get("EDITOR") or "").strip()
    if not command:
        raise CompanionError("no editor configured; set `$EDITOR` or pass `--editor`")
    try:
        proc = subprocess.Popen(  # noqa: S603
            [command, str(project_dir)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise CompanionError(f"editor `{command}` failed to start: {exc}") from exc
    return f"editor `{command}` opened (pid {proc.pid}); daemon untouched"


def session_guidance(project_dir: Path) -> str:
    """Read-only agent/session info: how to watch the live session."""
    from . import state as state_mod

    try:
        session = state_mod.read(project_dir).session_id
    except state_mod.StateError as exc:
        raise CompanionError(str(exc)) from exc
    return (
        f"agent session `{session}` is owned by the daemon; "
        "watch it with `ariadex attach` (the companion never injects input)"
    )


class CompanionWindow:
    """Tkinter mini-player. All daemon mutations go through CompanionClient.

    Collapsed: status indicator (text + color), work label, play/pause/stop.
    Expanded: full text status, hotkey field, reconcile/editor/session/quit.
    The window never grabs focus, never captures input beyond its own
    buttons, and polls on a bounded interval (refreshing after every command).
    """

    def __init__(
        self,
        root: object,
        client: CompanionClient,
        adapter: HotkeyAdapter,
        hotkey: str,
        editor: str | None = None,
        poll_interval_s: float = POLL_INTERVAL_S,
    ) -> None:
        import tkinter as tk

        self.root = root
        self.client = client
        self.adapter = adapter
        self.hotkey = hotkey
        self.editor = editor
        self.poll_interval_ms = max(1, int(poll_interval_s * 1000))
        self.model: dict = failure_view_model("starting")
        self._state: dict = {}
        self.hotkey_active = False
        self.hotkey_error: str | None = None
        self.expanded = False
        self._poll_after: str | None = None
        self._save_after: str | None = None

        assert isinstance(root, tk.Tk)
        root.title("Ariadex")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.geometry(f"{WIDGET_WIDTH}x{WIDGET_COLLAPSED_HEIGHT}")
        restored: tuple[int, int] | None
        try:
            restored = self._restored_geometry(root)
        except Exception:
            restored = None
        if restored is None:
            position = default_geometry(
                root.winfo_screenwidth(), root.winfo_screenheight()
            )
        else:
            position = restored
        clamped = clamp_to_screen(
            root, position[0], position[1], WIDGET_WIDTH, WIDGET_COLLAPSED_HEIGHT
        )
        if restored is not None and clamped != (int(restored[0]), int(restored[1])):
            with contextlib.suppress(Exception):
                save_user_config({"x": int(clamped[0]), "y": int(clamped[1])})
        position = clamped
        root.geometry(f"+{position[0]}+{position[1]}")

        self.frame = tk.Frame(
            root,
            background="#20242b",
            borderwidth=1,
            relief="solid",
            padx=10,
            pady=9,
        )
        self.frame.pack(fill="both", expand=True)

        self.titlebar = tk.Frame(self.frame, background="#20242b")
        self.titlebar.pack(fill="x")
        self.dot = tk.Label(
            self.titlebar,
            text="●",
            width=2,
            background="#20242b",
            foreground="#7dd3a8",
        )
        self.dot.pack(side="left")
        self.state_label = tk.Label(
            self.titlebar,
            text="STARTING",
            anchor="w",
            background="#20242b",
            foreground="#f3f4f6",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.state_label.pack(side="left", fill="x", expand=True)
        for widget in (self.titlebar, self.state_label):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
            widget.bind("<ButtonRelease-1>", self._drag_stop)
        self.toggle_button = tk.Button(
            self.titlebar,
            text="▾",
            width=2,
            name="expand-button",
            takefocus=True,
            command=self._toggle_expanded,
        )
        self.toggle_button.pack(side="right")
        self.close_button = tk.Button(
            self.titlebar,
            text="\u00d7",
            width=2,
            name="close-button",
            takefocus=True,
            background="#20242b",
            foreground="#f3f4f6",
            activebackground="#9b3d52",
            activeforeground="#ffffff",
            relief="flat",
            command=self._on_close,
        )
        self.close_button.pack(side="right")

        self.work_label = tk.Label(
            self.frame,
            text="(connecting)",
            anchor="w",
            justify="left",
            wraplength=WIDGET_WIDTH - 20,
            background="#20242b",
            foreground="#c9d1d9",
        )
        self.work_label.pack(fill="x")

        self.controls = tk.Frame(self.frame, background="#20242b")
        controls = self.controls
        controls.pack(fill="x", pady=(4, 0))
        self.play_button = tk.Button(
            controls,
            text="Play",
            name="play-button",
            width=8,
            padx=6,
            pady=5,
            takefocus=True,
            command=self._on_play,
        )
        self.play_button.pack(side="left", expand=True, fill="x")
        self.pause_button = tk.Button(
            controls,
            text="Pause",
            name="pause-button",
            width=8,
            padx=6,
            pady=5,
            takefocus=True,
            command=self._on_pause,
        )
        self.pause_button.pack(side="left", expand=True, fill="x")
        self.stop_button = tk.Button(
            controls,
            text="Stop",
            name="stop-button",
            width=8,
            padx=6,
            pady=5,
            takefocus=True,
            command=self._on_stop,
        )
        self.stop_button.pack(side="left", expand=True, fill="x")
        self.copy_log_button = tk.Button(
            controls,
            text="Copy log",
            name="copy-log-button",
            takefocus=False,
            command=self._on_copy_log,
        )
        self.copy_log_button.pack(side="left", expand=True, fill="x")

        self.details = tk.Frame(self.frame)
        self.status_text = tk.Text(
            self.details,
            height=6,
            width=34,
            wrap="word",
            name="status-text",
        )
        self.status_text.configure(state="disabled")
        self.status_text.pack(fill="x", pady=(4, 0))
        self.context_log = tk.Text(
            self.details,
            height=8,
            width=34,
            wrap="word",
            takefocus=False,
            name="context-log-text",
        )
        self.context_log.configure(state="disabled")
        self.context_log.pack(fill="x", pady=(4, 0))
        copy_row = tk.Frame(self.details)
        copy_row.pack(fill="x", pady=(4, 0))
        self.copy_context_button = tk.Button(
            copy_row,
            text="Copy context",
            name="copy-context-button",
            takefocus=False,
            command=self._on_copy_context,
        )
        self.copy_context_button.pack(side="left", expand=True, fill="x")
        hotkey_row = tk.Frame(self.details)
        hotkey_row.pack(fill="x")
        hotkey_label = tk.Label(hotkey_row, text="Hotkey:")
        hotkey_label.pack(side="left")
        self.hotkey_var = tk.StringVar(value=hotkey)
        self.hotkey_entry = tk.Entry(
            hotkey_row,
            textvariable=self.hotkey_var,
            width=12,
            name="hotkey-entry",
            takefocus=True,
        )
        self.hotkey_entry.pack(side="left", padx=4)
        self.hotkey_entry.bind("<Return>", lambda _e: self._apply_hotkey())
        self.apply_button = tk.Button(
            hotkey_row,
            text="Apply",
            name="hotkey-apply-button",
            takefocus=True,
            command=self._apply_hotkey,
        )
        self.apply_button.pack(side="left")
        extra = tk.Frame(self.details)
        extra.pack(fill="x", pady=(4, 0))
        self.reconcile_button = tk.Button(
            extra,
            text="Reconcile",
            name="reconcile-button",
            takefocus=True,
            command=self._on_reconcile,
        )
        self.reconcile_button.pack(side="left", expand=True, fill="x")
        self.editor_button = tk.Button(
            extra,
            text="Editor",
            name="editor-button",
            takefocus=True,
            command=self._on_editor,
        )
        self.editor_button.pack(side="left", expand=True, fill="x")
        self.session_button = tk.Button(
            extra,
            text="Session",
            name="session-button",
            takefocus=True,
            command=self._on_session,
        )
        self.session_button.pack(side="left", expand=True, fill="x")
        self.quit_button = tk.Button(
            self.details,
            text="Close Ariadex",
            name="quit-button",
            takefocus=True,
            command=self._quit,
        )
        self.quit_button.pack(fill="x", pady=(4, 0))

        self._drag_origin: tuple[int, int] | None = None
        root.bind("<FocusIn>", lambda _e: self._render())
        self._register_hotkey()
        self._refresh()
        self._schedule_poll()

    # -- geometry ------------------------------------------------------
    def _restored_geometry(self, root: object) -> tuple[int, int] | None:
        saved = load_user_config()
        if isinstance(saved.get("x"), int) and isinstance(saved.get("y"), int):
            return int(saved["x"]), int(saved["y"])
        return None

    def _drag_start(self, event: object) -> None:
        x = getattr(event, "x_root", 0)
        y = getattr(event, "y_root", 0)
        origin_x = self.root.winfo_x()  # type: ignore[attr-defined]
        origin_y = self.root.winfo_y()  # type: ignore[attr-defined]
        self._drag_origin = (int(x) - int(origin_x), int(y) - int(origin_y))

    def _active_window_height(self) -> int:
        if self.expanded:
            return WIDGET_EXPANDED_WINDOW_HEIGHT
        return WIDGET_COLLAPSED_HEIGHT

    def _drag_move(self, event: object) -> None:
        if self._drag_origin is None:
            return
        x = int(getattr(event, "x_root", 0)) - self._drag_origin[0]
        y = int(getattr(event, "y_root", 0)) - self._drag_origin[1]
        clamped = clamp_to_screen(
            self.root, x, y, WIDGET_WIDTH, self._active_window_height()
        )
        self.root.geometry(f"+{clamped[0]}+{clamped[1]}")  # type: ignore[attr-defined]

    def _drag_stop(self, _event: object) -> None:
        self._drag_origin = None
        if self._save_after is not None:
            with contextlib.suppress(Exception):
                self.root.after_cancel(self._save_after)  # type: ignore[attr-defined]
        self._save_after = self.root.after(500, self._persist_geometry)  # type: ignore[attr-defined]

    def _persist_geometry(self) -> None:
        self._save_after = None
        try:
            raw_x = int(self.root.winfo_x())  # type: ignore[attr-defined]
            raw_y = int(self.root.winfo_y())  # type: ignore[attr-defined]
        except Exception:
            return
        clamped = clamp_to_screen(
            self.root, raw_x, raw_y, WIDGET_WIDTH, self._active_window_height()
        )
        if (clamped[0], clamped[1]) != (raw_x, raw_y):
            with contextlib.suppress(Exception):
                self.root.geometry(f"+{clamped[0]}+{clamped[1]}")  # type: ignore[attr-defined]
        save_user_config({"x": int(clamped[0]), "y": int(clamped[1])})

    # -- hotkey --------------------------------------------------------
    def _register_hotkey(self) -> None:
        try:
            self.adapter.register(self.hotkey, self._on_hotkey)
        except CompanionError as exc:
            self.hotkey_active = False
            self.hotkey_error = str(exc)
            return
        self.hotkey_active = True
        self.hotkey_error = None

    def _apply_hotkey(self) -> None:
        candidate = self.hotkey_var.get().strip()
        try:
            parse_hotkey(candidate)
        except CompanionError as exc:
            self._notice(f"hotkey refused: {exc}")
            return
        self.adapter.unregister()
        self.hotkey = candidate
        self._register_hotkey()
        if self.hotkey_active:
            save_user_config({"hotkey": candidate})
            self._notice(f"hotkey `{candidate}` active")
        else:
            self._notice(f"hotkey failed: {self.hotkey_error}")
        self._render()

    def _on_hotkey(self) -> None:
        # Hotkey thread: marshal onto the Tk thread, never act directly.
        with contextlib.suppress(Exception):
            self.root.after(0, self._hotkey_toggle)  # type: ignore[attr-defined]

    def _hotkey_toggle(self) -> None:
        # The hotkey issues only a daemon pause/resume request: no keystroke
        # is ever injected into the focused application.
        if self.model.get("mode") == "AUTO":
            self._on_pause()
        else:
            self._on_play()

    # -- actions (IPC only) --------------------------------------------
    def _run_client(self, action: str) -> None:
        try:
            if action == "pause":
                state = self.client.pause()
            elif action == "resume":
                state = self.client.resume()
            elif action == "stop":
                state = self.client.stop()
            else:
                state = self.client.reconcile()
        except CompanionError as exc:
            self.model = failure_view_model(str(exc))
        else:
            self._state = state
            self.model = build_view_model(state)
        self._render()

    def _on_pause(self) -> None:
        self._run_client("pause")

    def _on_play(self) -> None:
        self._run_client("resume")

    def _on_stop(self) -> None:
        import tkinter.messagebox as messagebox

        if not messagebox.askyesno(
            "Ariadex",
            "Stop the daemon? In-flight work is cancelled at the safe "
            "boundary; durable state is kept for `recover`.",
            parent=cast(Any, self.root),
        ):
            return
        self._run_client("stop")

    def _on_reconcile(self) -> None:
        self._run_client("reconcile")

    def _on_editor(self) -> None:
        try:
            note = open_editor(self.client.project_dir, self.editor)
        except CompanionError as exc:
            self._notice(str(exc))
        else:
            self._notice(note)

    def _on_session(self) -> None:
        try:
            note = session_guidance(self.client.project_dir)
        except CompanionError as exc:
            self._notice(str(exc))
        else:
            self._notice(note)

    def _managed_projection(self) -> dict | None:
        projection = self.model.get("managed_context")
        return projection if isinstance(projection, dict) else None

    def _copy_text(self, text: str, label: str) -> None:
        """Copy via Tk's native clipboard with visible feedback.

        Read-only and local: no provider input, no scheduling change, no
        focus change beyond the clicked button itself.
        """
        error = copy_to_clipboard(self.root, text)
        if error is None:
            self._notice(f"{label} copied to clipboard")
        else:
            self._notice(error)

    def _on_copy_log(self) -> None:
        projection = self._managed_projection()
        if projection is None:
            self._notice("no diagnostic context yet; nothing to copy")
            return
        self._copy_text(format_managed_log_text(projection), "log")

    def _on_copy_context(self) -> None:
        projection = self._managed_projection()
        if projection is None:
            self._notice("no diagnostic context yet; nothing to copy")
            return
        self._copy_text(
            format_context_snapshot(projection, self._last_state()), "context"
        )

    def _last_state(self) -> dict:
        state = getattr(self, "_state", None)
        return dict(state) if isinstance(state, dict) else {}

    def _notice(self, text: str) -> None:
        model = dict(self.model)
        model["failure"] = text
        self.model = model
        self._render()

    def _toggle_expanded(self) -> None:
        self.expanded = not self.expanded
        height = (
            WIDGET_EXPANDED_WINDOW_HEIGHT if self.expanded else WIDGET_COLLAPSED_HEIGHT
        )
        if self.expanded:
            self.details.pack(fill="x")
            self.toggle_button.configure(text="▴")
        else:
            self.details.pack_forget()
            self.toggle_button.configure(text="▾")
        try:
            raw_x = int(self.root.winfo_x())  # type: ignore[attr-defined]
            raw_y = int(self.root.winfo_y())  # type: ignore[attr-defined]
        except Exception:
            self.root.geometry(f"{WIDGET_WIDTH}x{height}")  # type: ignore[attr-defined]
            return
        clamped = clamp_to_screen(self.root, raw_x, raw_y, WIDGET_WIDTH, height)
        with contextlib.suppress(Exception):
            self.root.geometry(  # type: ignore[attr-defined]
                f"{WIDGET_WIDTH}x{height}+{clamped[0]}+{clamped[1]}"
            )

    def _render_context_log(self, model: dict) -> None:
        """Write the read-only managed log; never raises into the poll loop."""
        projection = model.get("managed_context")
        if not isinstance(projection, dict):
            lines = ["diagnostic context: (daemon unreachable or not started yet)"]
        else:
            lines = format_managed_log_text(projection).splitlines()
        with contextlib.suppress(Exception):
            self.context_log.configure(state="normal")
            self.context_log.delete("1.0", "end")
            self.context_log.insert("1.0", "\n".join(lines))
            self.context_log.configure(state="disabled")

    def _hide(self) -> None:
        # Hidden, not stopped: the daemon keeps scheduling; the hotkey stays
        # armed. Restored from the taskbar/dock (iconify, never withdraw).
        self.root.iconify()  # type: ignore[attr-defined]

    def _quit(self) -> None:
        # Close only this Tk process; callers decide whether the daemon also
        # needs to be stopped before invoking this cleanup path.
        self._cancel_poll()
        self.adapter.unregister()
        self.root.destroy()  # type: ignore[attr-defined]

    def _on_close(self) -> None:
        """Stop the daemon, then exit the widget process."""
        try:
            self.client.stop()
        except CompanionError as exc:
            # Do not close the only visible control while the daemon is still
            # running. The operator must be able to retry or use the
            # diagnostic controls; a silent IPC failure leaves the managed
            # editor alive after an intentional quit.
            model = dict(self.model)
            model["failure"] = str(exc)
            self.model = model
            self._render()
            return
        self._quit()

    # -- polling / rendering -------------------------------------------
    def _schedule_poll(self) -> None:
        self._cancel_poll()
        self._poll_after = self.root.after(self.poll_interval_ms, self._poll)  # type: ignore[attr-defined]

    def _cancel_poll(self) -> None:
        if self._poll_after is not None:
            with contextlib.suppress(Exception):
                self.root.after_cancel(self._poll_after)  # type: ignore[attr-defined]
            self._poll_after = None

    def _poll(self) -> None:
        self._poll_after = None
        self._refresh()
        self._schedule_poll()

    def _refresh(self) -> None:
        try:
            state = self.client.refresh()
        except CompanionError as exc:
            if self.model.get("failure") is None and not self.model.get("alive"):
                self.model = failure_view_model(str(exc))
            else:
                model = dict(self.model)
                model["failure"] = str(exc)
                self.model = model
        else:
            self._state = state
            self.model = build_view_model(state)
        self._render()

    def _render(self) -> None:
        model = self.model
        indicator = str(model.get("indicator_text", "?"))
        colors = {
            "WORKING": "green",
            "PAUSED": "orange",
            "MANUAL": "blue",
            "BLOCKED": "red",
            "STOPPED": "gray",
            "COMPLETED": "green",
            "UNREACHABLE": "red",
        }
        self.dot.configure(foreground=colors.get(indicator, "black"))
        suffix = "" if self.hotkey_active else " (hotkey off)"
        if self.hotkey_error and not self.hotkey_active:
            suffix = " (hotkey unavailable)"
        self.state_label.configure(text=f"{indicator}{suffix}")
        self.work_label.configure(text=str(model.get("work_label", "")))
        actions = model.get("actions", {})
        self.pause_button.configure(text="Pause")
        self.pause_button.configure(
            state="normal" if actions.get("pause") else "disabled"
        )
        self.play_button.configure(
            state="normal" if actions.get("play") else "disabled"
        )
        self.stop_button.configure(
            state="normal" if actions.get("stop") else "disabled"
        )
        text = format_view_text(model)
        if self.hotkey_error and not self.hotkey_active:
            text += f"\nhotkey: {self.hotkey_error}"
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", text)
        self.status_text.configure(state="disabled")
        self._render_context_log(model)


ROBOT_INDICATORS = (
    "watching",
    "working",
    "waiting",
    "paused",
    "blocked",
    "completed",
    "stopped",
)


def build_robot_view_model(status: dict) -> dict:
    """Map one robot status snapshot to widget state (pure, no I/O).

    Only provider/session identity and robot state are shown; there are
    no scheduler controls. Pause stops new input, quit stops watching,
    and both leave the user-owned provider session untouched. The model
    also carries the latest Ariadex activity event plus a bounded
    read-only activity list for the expandable widget log.
    """
    phase = str(status.get("phase", "unknown"))
    provider = str(status.get("provider", "unknown"))
    session = str(status.get("session", "unknown"))
    paused = bool(status.get("paused"))
    reason = str(status.get("block_reason", "") or "")
    raw_activity = status.get("activity", [])
    activity: list[dict] = []
    if isinstance(raw_activity, list):
        for entry in raw_activity[-ROBOT_LOG_VIEW_LINES:]:
            if not isinstance(entry, dict):
                continue
            activity.append(
                {
                    "category": str(entry.get("category", "info")),
                    "message": str(entry.get("message", ""))[:280],
                }
            )
    latest_raw = status.get("latest_event")
    latest: dict | None = None
    if isinstance(latest_raw, dict):
        latest = {
            "category": str(latest_raw.get("category", "info")),
            "message": str(latest_raw.get("message", ""))[:280],
        }
    elif activity:
        latest = dict(activity[-1])
    latest_text = (
        f"{latest['category']}: {latest['message']}" if latest else "no activity yet"
    )
    if phase in ("stopped",):
        indicator = "stopped"
    elif phase in ("done",):
        indicator = "completed"
    elif phase in ("blocked",):
        indicator = "blocked"
    elif phase in ("waiting",):
        indicator = "waiting"
    elif paused or phase in ("paused",):
        indicator = "paused"
    elif phase in ("attached", "unknown"):
        indicator = "watching"
    else:
        indicator = "working"
    identity = f"{provider} @ {session}"
    work_label = f"{identity} — {phase}"
    if reason and indicator == "blocked":
        work_label += f": {reason}"
    try:
        prompts = int(status.get("prompts_sent", 0))
    except (TypeError, ValueError):
        prompts = 0
    try:
        confirmations = int(status.get("confirmations_sent", 0))
    except (TypeError, ValueError):
        confirmations = 0
    try:
        approvals = int(status.get("permissions_granted", 0))
    except (TypeError, ValueError):
        approvals = 0
    run_stats = (
        f"prompts {prompts} · confirmations {confirmations} · approvals {approvals}"
    )
    return {
        "indicator": indicator,
        "indicator_text": indicator.upper(),
        "phase": phase,
        "identity": identity,
        "work_label": work_label,
        "run_stats": run_stats,
        "failure": reason if indicator == "blocked" else None,
        "latest_event": latest,
        "latest_text": latest_text,
        "activity": activity,
        "expanded": bool(status.get("expanded", False)),
        "actions": {
            "pause": indicator in ("watching", "working", "waiting"),
            "resume": indicator == "paused",
            "quit": indicator != "stopped",
        },
    }


def format_robot_activity_line(entry: dict) -> str:
    """Render one activity entry as a single operator-readable line."""
    return f"{entry.get('category', 'info')}: {entry.get('message', '')}"


#: Max characters for the project segment of a hub tab label.
HUB_TAB_LABEL_MAX = 24

#: Max characters for the session segment appended during disambiguation.
HUB_TAB_SESSION_MAX = 16

#: Per-tab state dots (text-only, no color dependency).
HUB_INDICATOR_DOTS = {
    "blocked": "\u25cf",
    "working": "\u25cf",
    "watching": "\u25cb",
    "waiting": "\u25cc",
    "paused": "\u275a\u275a",
    "completed": "\u2713",
    "stopped": "\u25a0",
    "unreachable": "\u2715",
}

#: Per-tab state colors for the tab bar (foreground on dark background).
HUB_INDICATOR_COLORS = {
    "blocked": "#f85149",
    "working": "#3fb950",
    "watching": "#9aa4b2",
    "waiting": "#d29922",
    "paused": "#d29922",
    "completed": "#3fb950",
    "stopped": "#6e7681",
    "unreachable": "#f85149",
}

#: Hub attention precedence: worst state first (unreachable needs a look,
#: so it ranks just below blocked).
HUB_PRECEDENCE = (
    "blocked",
    "unreachable",
    "working",
    "watching",
    "waiting",
    "paused",
    "completed",
    "stopped",
)


def _hub_path_segments(project_dir: str | Path) -> list[str]:
    """Split a project dir into significant path segments (pure, no I/O)."""
    text = str(project_dir)
    segments = [seg for seg in Path(text).parts if seg not in ("", "/", ".")]
    return segments or [text]


def _hub_short_name(project_dir: str | Path, depth: int) -> str:
    """Last `depth` path segments, front-truncated to the label bound."""
    segments = _hub_path_segments(project_dir)
    name = "/".join(segments[-max(1, depth) :])
    if len(name) > HUB_TAB_LABEL_MAX:
        name = "\u2026" + name[-(HUB_TAB_LABEL_MAX - 1) :]
    return name


def hub_tab_label(project_dir: str | Path, provider: str) -> str:
    """Short tab label: project folder name plus the AI-agent provider badge."""
    return f"{_hub_short_name(project_dir, 1)} [{provider}]"


def _hub_candidate(
    project_dir: str | Path,
    provider: str,
    session: str,
    depth: int,
    with_session: bool,
) -> str:
    name = _hub_short_name(project_dir, depth)
    if with_session:
        short_session = str(session)
        if len(short_session) > HUB_TAB_SESSION_MAX:
            short_session = short_session[: HUB_TAB_SESSION_MAX - 1] + "\u2026"
        name = f"{name}@{short_session}"
    return f"{name} [{provider}]"


def disambiguate_hub_labels(
    entries: list[tuple[str | Path, str, str]],
) -> list[str]:
    """Unique short tab labels for `(project_dir, provider, session)` entries.

    Basename collisions gain parent segments, then the session name, until
    unique. A trailing index guarantees termination for fully identical
    entries (the CLI refuses those earlier; this never guesses silently).
    """
    depths = [1] * len(entries)
    suffixed = [False] * len(entries)
    while True:
        labels = [
            _hub_candidate(project, provider, session, depths[i], suffixed[i])
            for i, (project, provider, session) in enumerate(entries)
        ]
        duplicates = {label for label in labels if labels.count(label) > 1}
        if not duplicates:
            return labels
        progressed = False
        for i, (project, _provider, _session) in enumerate(entries):
            if labels[i] not in duplicates:
                continue
            if depths[i] < len(_hub_path_segments(project)):
                depths[i] += 1
                progressed = True
            elif not suffixed[i]:
                suffixed[i] = True
                progressed = True
        if not progressed:
            return [
                f"{label} #{i + 1}" if label in duplicates else label
                for i, label in enumerate(labels)
            ]


def _hub_tab_key(model: dict) -> str:
    """Precedence key for one per-tab view model."""
    if model.get("indicator_text") == "UNREACHABLE":
        return "unreachable"
    return str(model.get("indicator", "unknown"))


def build_hub_view_model(
    tab_models: list[dict], labels: list[str], active: int = 0
) -> dict:
    """Aggregate per-tab robot models into one hub model (pure, no I/O)."""
    tabs = []
    for i, model in enumerate(tab_models):
        key = _hub_tab_key(model)
        tabs.append(
            {
                "label": labels[i] if i < len(labels) else f"tab {i + 1}",
                "indicator": key,
                "indicator_text": (
                    "UNREACHABLE"
                    if key == "unreachable"
                    else str(model.get("indicator_text", "?"))
                ),
            }
        )
    order = {key: rank for rank, key in enumerate(HUB_PRECEDENCE)}
    hub_key = "stopped"
    for tab in tabs:
        if order.get(tab["indicator"], len(order)) < order.get(hub_key, len(order)):
            hub_key = tab["indicator"]
    hub_text = "UNREACHABLE" if hub_key == "unreachable" else hub_key.upper()
    return {
        "count": len(tabs),
        "active": min(max(0, active), max(0, len(tabs) - 1)),
        "tabs": tabs,
        "hub_indicator": hub_key,
        "hub_indicator_text": hub_text,
        "title": f"Ariadex Robots ({len(tabs)}) \u2014 {hub_text}",
    }


def format_robot_text(model: dict) -> str:
    """Text status equivalent of the robot widget (screen-reader use)."""
    lines = [
        f"robot: {model.get('indicator_text')} (phase {model.get('phase')})",
        f"watching: {model.get('identity')}",
        f"latest: {model.get('latest_text', 'no activity yet')}",
    ]
    actions = model.get("actions", {})
    enabled = sorted(name for name, on in actions.items() if on)
    lines.append(f"actions: {', '.join(enabled) if enabled else 'none available'}")
    if model.get("failure"):
        lines.append(f"blocked: {model['failure']}")
    activity = model.get("activity", [])
    if activity:
        lines.append("activity:")
        for entry in activity[-ROBOT_LOG_VIEW_LINES:]:
            lines.append(f"- {format_robot_activity_line(entry)}")
    else:
        lines.append("activity: (none)")
    return "\n".join(lines)


class RobotWindow:
    """Minimal robot control: fixed middle-right, state, Pause, Quit.

    The window polls a status function and forwards Pause/Quit to the
    watcher callbacks. It never touches tmux, leases, or state files;
    closing it quits watching and leaves the provider session running.
    The collapsed view shows the latest Ariadex activity event; an
    explicit toggle expands a bounded read-only activity log without
    moving the window or taking focus from the provider editor.
    """

    def __init__(
        self,
        root: object,
        status_fn: Callable[[], dict],
        on_pause: Callable[[], str],
        on_quit: Callable[[], str],
        on_resume: Callable[[], str] | None = None,
        hotkey_adapter: HotkeyAdapter | None = None,
        hotkey: str = DEFAULT_HOTKEY,
        poll_interval_s: float = POLL_INTERVAL_S,
    ) -> None:
        import tkinter as tk

        self.root = root
        self.status_fn = status_fn
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.on_quit = on_quit
        self.hotkey_adapter = hotkey_adapter
        self.hotkey = hotkey
        self.poll_interval_ms = max(1, int(poll_interval_s * 1000))
        self.model: dict = build_robot_view_model({})
        self._poll_after: str | None = None

        assert isinstance(root, tk.Tk)
        root.title("Ariadex Robot")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.geometry(f"{WIDGET_WIDTH}x{WIDGET_COLLAPSED_HEIGHT}")
        position = default_geometry(root.winfo_screenwidth(), root.winfo_screenheight())
        position = clamp_to_screen(
            root, position[0], position[1], WIDGET_WIDTH, WIDGET_COLLAPSED_HEIGHT
        )
        root.geometry(f"+{position[0]}+{position[1]}")

        self.frame = tk.Frame(
            root,
            background="#20242b",
            borderwidth=1,
            relief="solid",
            padx=10,
            pady=9,
        )
        self.frame.pack(fill="both", expand=True)
        self.state_label = tk.Label(
            self.frame,
            text="WATCHING",
            anchor="w",
            background="#20242b",
            foreground="#f3f4f6",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.state_label.pack(fill="x")
        self.identity_label = tk.Label(
            self.frame,
            text="(connecting)",
            anchor="w",
            justify="left",
            wraplength=WIDGET_WIDTH - 20,
            background="#20242b",
            foreground="#c9d1d9",
        )
        self.identity_label.pack(fill="x")
        self.event_label = tk.Label(
            self.frame,
            text="no activity yet",
            anchor="w",
            justify="left",
            wraplength=WIDGET_WIDTH - 20,
            background="#20242b",
            foreground="#9aa4b2",
        )
        self.event_label.pack(fill="x")
        self.expanded = False
        self.log_text = self._build_log_panel(tk)
        controls = tk.Frame(self.frame, background="#20242b")
        controls.pack(fill="x", pady=(4, 0))
        self.pause_button = tk.Button(
            controls,
            text="Pause",
            name="robot-pause-button",
            width=8,
            takefocus=True,
            command=self._on_pause,
        )
        self.pause_button.pack(side="left", expand=True, fill="x")
        self.quit_button = tk.Button(
            controls,
            text="Quit",
            name="robot-quit-button",
            width=8,
            takefocus=True,
            command=self._on_quit,
        )
        self.quit_button.pack(side="left", expand=True, fill="x")
        self.toggle_button = tk.Button(
            controls,
            text="Show log",
            name="robot-log-toggle",
            width=8,
            takefocus=False,
            command=self._on_toggle,
        )
        self.toggle_button.pack(side="left", expand=True, fill="x")
        if self.hotkey_adapter is not None:
            self.hotkey_adapter.register(self.hotkey, self._on_hotkey)
        self._refresh()
        self._schedule_poll()

    def _build_log_panel(self, tk):
        """Create the read-only activity log without touching window focus."""
        text_cls = getattr(tk, "Text", None)
        if text_cls is None:
            return None
        try:
            widget = text_cls(
                self.frame,
                height=8,
                wrap="word",
                takefocus=False,
                background="#14171c",
                foreground="#c9d1d9",
            )
        except Exception:
            return None
        with contextlib.suppress(Exception):
            widget.configure(state="disabled")
        return widget

    def _on_toggle(self) -> None:
        """Expand or collapse the activity log; never sends provider input."""
        self.expanded = not self.expanded
        with contextlib.suppress(Exception):
            if self.expanded and self.log_text is not None:
                self.log_text.pack(fill="both", expand=True, pady=(4, 0))
            elif self.log_text is not None:
                pack_forget = getattr(self.log_text, "pack_forget", None)
                if callable(pack_forget):
                    pack_forget()
        with contextlib.suppress(Exception):
            height = (
                WIDGET_EXPANDED_HEIGHT if self.expanded else WIDGET_COLLAPSED_HEIGHT
            )
            try:
                raw_x = int(self.root.winfo_x())  # type: ignore[attr-defined]
                raw_y = int(self.root.winfo_y())  # type: ignore[attr-defined]
            except Exception:
                self.root.geometry(f"{WIDGET_WIDTH}x{height}")  # type: ignore[attr-defined]
            else:
                clamped = clamp_to_screen(self.root, raw_x, raw_y, WIDGET_WIDTH, height)
                self.root.geometry(  # type: ignore[attr-defined]
                    f"{WIDGET_WIDTH}x{height}+{clamped[0]}+{clamped[1]}"
                )
        self._render()

    def _on_pause(self) -> None:
        with contextlib.suppress(Exception):
            if self.model.get("indicator") == "paused" and self.on_resume:
                self.on_resume()
            else:
                self.on_pause()
        self._refresh()

    def _on_hotkey(self) -> None:
        """Marshal the X11 callback onto Tk's UI thread."""
        with contextlib.suppress(Exception):
            self.root.after(0, self._on_pause)  # type: ignore[attr-defined]

    def _on_quit(self) -> None:
        with contextlib.suppress(Exception):
            self.on_quit()
        if self.hotkey_adapter is not None:
            self.hotkey_adapter.unregister()
        self._cancel_poll()
        self.root.destroy()  # type: ignore[attr-defined]

    def _schedule_poll(self) -> None:
        self._cancel_poll()
        self._poll_after = self.root.after(  # type: ignore[attr-defined]
            self.poll_interval_ms, self._poll
        )

    def _cancel_poll(self) -> None:
        if self._poll_after is not None:
            with contextlib.suppress(Exception):
                self.root.after_cancel(self._poll_after)  # type: ignore[attr-defined]
            self._poll_after = None

    def _poll(self) -> None:
        self._poll_after = None
        self._refresh()
        self._schedule_poll()

    def _refresh(self) -> None:
        try:
            status = self.status_fn()
        except Exception as exc:
            model = build_robot_view_model({})
            model["indicator"] = "stopped"
            model["indicator_text"] = "UNREACHABLE"
            model["failure"] = str(exc)
            self.model = model
        else:
            self.model = build_robot_view_model(status)
        self._render()

    def _log_lines(self, model: dict) -> list[str]:
        """Honest expanded-log lines for empty/unreachable/blocked states."""
        activity = model.get("activity", [])
        lines = [format_robot_activity_line(entry) for entry in activity]
        if lines:
            return lines[-ROBOT_LOG_VIEW_LINES:]
        if model.get("indicator_text") == "UNREACHABLE":
            detail = str(model.get("failure", "") or "").strip()
            return [f"watcher unreachable{': ' + detail if detail else ''}"]
        if model.get("failure"):
            return ["(no activity yet)", f"blocked: {model['failure']}"]
        return ["(no activity yet)"]

    def _render(self) -> None:
        model = self.model
        self.state_label.configure(text=str(model.get("indicator_text", "?")))
        self.identity_label.configure(text=str(model.get("work_label", "")))
        with contextlib.suppress(Exception):
            self.event_label.configure(
                text=str(model.get("latest_text", "no activity yet"))
            )
            self.toggle_button.configure(
                text="Hide log" if self.expanded else "Show log"
            )
        self._render_log(model)
        actions = model.get("actions", {})
        self.pause_button.configure(
            text="Resume" if model.get("indicator") == "paused" else "Pause"
        )
        self.pause_button.configure(
            state=(
                "normal"
                if actions.get("pause") or actions.get("resume")
                else "disabled"
            )
        )
        self.quit_button.configure(
            state="normal" if actions.get("quit") else "disabled"
        )

    def _render_log(self, model: dict) -> None:
        """Write the read-only log; never raises into the poll loop."""
        if self.log_text is None or not self.expanded:
            return
        lines = self._log_lines(model)
        with contextlib.suppress(Exception):
            self.log_text.configure(state="normal")
        with contextlib.suppress(Exception):
            delete = getattr(self.log_text, "delete", None)
            insert = getattr(self.log_text, "insert", None)
            if callable(delete):
                delete("1.0", "end")
            if callable(insert):
                insert("1.0", "\n".join(lines))
        with contextlib.suppress(Exception):
            self.log_text.configure(state="disabled")


def format_hub_queue_text(summary: dict) -> str:
    """Render one tab's queue evidence as a single row (pure, no I/O)."""
    reason = str(summary.get("unavailable") or "")
    if reason:
        return f"queue: n/a ({reason})"
    try:
        active = int(summary.get("active_count", 0))
    except (TypeError, ValueError):
        active = 0
    current = str(summary.get("current_spec") or "")
    if not current:
        if active:
            return f"queue: {active} active · no current spec"
        return "queue: empty"
    try:
        open_tasks = int(summary.get("open_tasks", 0))
    except (TypeError, ValueError):
        open_tasks = 0
    try:
        total_tasks = int(summary.get("total_tasks", 0))
    except (TypeError, ValueError):
        total_tasks = 0
    return f"queue: {active} active · {current} {open_tasks}/{total_tasks} open"


@dataclasses.dataclass
class RobotHubTab:
    """One supervised project inside the hub window."""

    project: str
    label: str
    status_fn: Callable[[], dict]
    on_pause: Callable[[], str]
    on_resume: Callable[[], str]
    on_quit: Callable[[], str]
    run_fn: Callable[[], object] | None = None
    queue_fn: Callable[[], dict] | None = None


class RobotHubWindow:
    """Multi-project robot hub: tab bar plus one shared detail panel.

    Each tab owns an independent watcher; the hub only polls status
    functions and forwards Pause/Resume/Quit to the visible tab (or to all
    tabs for Pause-all). It never touches tmux, leases, or state files;
    quitting a tab leaves that provider session running and attachable.
    Switching tabs or expanding the log never sends provider input and
    never moves the window.
    """

    def __init__(
        self,
        root: object,
        tabs: list[RobotHubTab],
        hotkey_adapter: HotkeyAdapter | None = None,
        hotkey: str = DEFAULT_HOTKEY,
        poll_interval_s: float = POLL_INTERVAL_S,
        active: int = 0,
        on_empty: Callable[[], None] | None = None,
    ) -> None:
        import tkinter as tk

        self._tk = tk
        self.root = root
        self.tabs = list(tabs)
        self.active = min(max(0, active), max(0, len(self.tabs) - 1))
        self.hotkey_adapter = hotkey_adapter
        self.hotkey = hotkey
        self.poll_interval_ms = max(1, int(poll_interval_s * 1000))
        self.models: list[dict] = [build_robot_view_model({}) for _ in self.tabs]
        self.queue_texts: list[str] = [
            "queue: n/a (no queue source)" for _ in self.tabs
        ]
        self.queue_specs: list[str] = ["" for _ in self.tabs]
        self._poll_after: str | None = None
        #: Called when the last tab leaves (hub server exits itself).
        self.on_empty = on_empty

        assert isinstance(root, tk.Tk)
        root.title(f"Ariadex Robots ({len(self.tabs)})")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.geometry(f"{WIDGET_WIDTH}x{HUB_COLLAPSED_HEIGHT}")
        position = default_geometry(root.winfo_screenwidth(), root.winfo_screenheight())
        position = clamp_to_screen(
            root, position[0], position[1], WIDGET_WIDTH, HUB_COLLAPSED_HEIGHT
        )
        root.geometry(f"+{position[0]}+{position[1]}")

        self.frame = tk.Frame(
            root,
            background="#20242b",
            borderwidth=1,
            relief="solid",
            padx=10,
            pady=9,
        )
        self.frame.pack(fill="both", expand=True)
        self.tab_bar = tk.Frame(self.frame, background="#20242b")
        self.tab_bar.pack(fill="x")
        self.tab_buttons: list[object] = []
        self._rebuild_tab_bar()
        self.state_label = tk.Label(
            self.frame,
            text="WATCHING",
            anchor="w",
            background="#20242b",
            foreground="#f3f4f6",
            font=("TkDefaultFont", 10, "bold"),
        )
        self.state_label.pack(fill="x")
        self.identity_label = tk.Label(
            self.frame,
            text="(connecting)",
            anchor="w",
            justify="left",
            wraplength=WIDGET_WIDTH - 20,
            background="#20242b",
            foreground="#c9d1d9",
        )
        self.identity_label.pack(fill="x")
        self.session_label = tk.Label(
            self.frame,
            text="",
            anchor="w",
            justify="left",
            wraplength=WIDGET_WIDTH - 20,
            background="#20242b",
            foreground="#c9d1d9",
        )
        self.session_label.pack(fill="x")
        self.queue_label = tk.Label(
            self.frame,
            text="queue: n/a (no queue source)",
            anchor="w",
            justify="left",
            wraplength=WIDGET_WIDTH - 20,
            background="#20242b",
            foreground="#7db8f0",
        )
        self.queue_label.pack(fill="x")
        self.event_label = tk.Label(
            self.frame,
            text="no activity yet",
            anchor="w",
            justify="left",
            wraplength=WIDGET_WIDTH - 20,
            background="#20242b",
            foreground="#9aa4b2",
        )
        self.event_label.pack(fill="x")
        self.stats_label = tk.Label(
            self.frame,
            text="",
            anchor="w",
            justify="left",
            wraplength=WIDGET_WIDTH - 20,
            background="#20242b",
            foreground="#9aa4b2",
        )
        self.expanded = False
        self.log_text = self._build_log_panel(tk)
        controls = tk.Frame(self.frame, background="#20242b")
        controls.pack(fill="x", pady=(4, 0))
        self.pause_button = tk.Button(
            controls,
            text="Pause",
            name="robot-hub-pause-button",
            width=8,
            takefocus=True,
            command=self._on_pause_active,
        )
        self.pause_button.pack(side="left", expand=True, fill="x")
        self.pause_all_button = tk.Button(
            controls,
            text="Pause all",
            name="robot-hub-pause-all-button",
            width=8,
            takefocus=False,
            command=self._on_pause_all,
        )
        self.pause_all_button.pack(side="left", expand=True, fill="x")
        self.quit_button = tk.Button(
            controls,
            text="Quit",
            name="robot-hub-quit-button",
            width=8,
            takefocus=True,
            command=self._on_quit_active,
        )
        self.quit_button.pack(side="left", expand=True, fill="x")
        self.toggle_button = tk.Button(
            controls,
            text="Show log",
            name="robot-hub-log-toggle",
            width=8,
            takefocus=False,
            command=self._on_toggle,
        )
        self.toggle_button.pack(side="left", expand=True, fill="x")
        self.close_button = tk.Button(
            controls,
            text="Close",
            name="robot-hub-close-button",
            width=8,
            takefocus=False,
            command=self._on_close_window,
        )
        self.close_button.pack(side="left", expand=True, fill="x")
        if self.hotkey_adapter is not None:
            self.hotkey_adapter.register(self.hotkey, self._on_hotkey)
        self._refresh()
        self._schedule_poll()

    def _select_fn(self, index: int) -> Callable[[], None]:
        def select() -> None:
            self.active = index
            self._render()

        return select

    def _rebuild_tab_bar(self) -> None:
        """Recreate tab buttons for the current tab list (hub auto-join)."""
        tk = self._tk
        for child in list(self.tab_bar.winfo_children()):
            with contextlib.suppress(Exception):
                child.destroy()
        self.tab_buttons = []
        for index in range(len(self.tabs)):
            button = tk.Button(
                self.tab_bar,
                name=f"robot-hub-tab-{index}",
                width=8,
                takefocus=False,
                command=self._select_fn(index),
            )
            button.pack(side="left", expand=True, fill="x")
            self.tab_buttons.append(button)

    def add_tab(self, tab: RobotHubTab) -> None:
        """Append one tab (idempotent per project); sends no input."""
        for existing in self.tabs:
            if existing.project == tab.project:
                return
        self.tabs.append(tab)
        self.models.append(build_robot_view_model({}))
        self.queue_texts.append("queue: n/a (no queue source)")
        self.queue_specs.append("")
        self._rebuild_tab_bar()
        self._refresh()

    def remove_project(self, project: str) -> None:
        """Drop one tab by project; exits the window when none remain."""
        index = next(
            (i for i, tab in enumerate(self.tabs) if tab.project == project),
            None,
        )
        if index is None:
            return
        del self.tabs[index]
        for cache in (self.models, self.queue_texts, self.queue_specs):
            if index < len(cache):
                del cache[index]
        self.active = min(self.active, max(0, len(self.tabs) - 1))
        if not self.tabs:
            if self.on_empty is not None:
                with contextlib.suppress(Exception):
                    self.on_empty()
            with contextlib.suppress(Exception):
                self.root.destroy()  # type: ignore[attr-defined]
            return
        self._rebuild_tab_bar()
        self._refresh()

    def _on_close_window(self) -> None:
        """Close the hub window only; daemons, sessions, watchers persist."""
        with contextlib.suppress(Exception):
            self.root.destroy()  # type: ignore[attr-defined]

    def _build_log_panel(self, tk):
        """Create the read-only activity log without touching window focus."""
        text_cls = getattr(tk, "Text", None)
        if text_cls is None:
            return None
        try:
            widget = text_cls(
                self.frame,
                height=8,
                wrap="word",
                takefocus=False,
                background="#14171c",
                foreground="#c9d1d9",
            )
        except Exception:
            return None
        with contextlib.suppress(Exception):
            widget.configure(state="disabled")
        return widget

    def _hub_model(self) -> dict:
        return build_hub_view_model(
            self.models, [tab.label for tab in self.tabs], self.active
        )

    def _on_toggle(self) -> None:
        """Expand or collapse the activity log; never sends provider input."""
        self.expanded = not self.expanded
        with contextlib.suppress(Exception):
            if self.expanded and self.log_text is not None:
                self.log_text.pack(fill="both", expand=True, pady=(4, 0))
            elif self.log_text is not None:
                pack_forget = getattr(self.log_text, "pack_forget", None)
                if callable(pack_forget):
                    pack_forget()
        with contextlib.suppress(Exception):
            height = HUB_EXPANDED_HEIGHT if self.expanded else HUB_COLLAPSED_HEIGHT
            try:
                raw_x = int(self.root.winfo_x())  # type: ignore[attr-defined]
                raw_y = int(self.root.winfo_y())  # type: ignore[attr-defined]
            except Exception:
                self.root.geometry(f"{WIDGET_WIDTH}x{height}")  # type: ignore[attr-defined]
            else:
                clamped = clamp_to_screen(self.root, raw_x, raw_y, WIDGET_WIDTH, height)
                self.root.geometry(  # type: ignore[attr-defined]
                    f"{WIDGET_WIDTH}x{height}+{clamped[0]}+{clamped[1]}"
                )
        self._render()

    def _on_pause_active(self) -> None:
        """Pause or resume the visible tab only; other tabs are untouched."""
        if not self.tabs:
            return
        tab = self.tabs[self.active]
        model = self.models[self.active]
        with contextlib.suppress(Exception):
            if model.get("indicator") == "paused":
                tab.on_resume()
            else:
                tab.on_pause()
        self._refresh()

    def _on_pause_all(self) -> None:
        """Pause every non-stopped tab; each watcher records its own pause."""
        for index, tab in enumerate(self.tabs):
            model = self.models[index] if index < len(self.models) else {}
            actions = model.get("actions", {})
            if actions.get("pause"):
                with contextlib.suppress(Exception):
                    tab.on_pause()
        self._refresh()

    def _on_hotkey(self) -> None:
        """Marshal the X11 callback onto Tk's UI thread (active tab only)."""
        with contextlib.suppress(Exception):
            self.root.after(0, self._on_pause_active)  # type: ignore[attr-defined]

    def _on_quit_active(self) -> None:
        """Detach the visible tab; the hub stays alive while tabs remain."""
        if not self.tabs:
            return
        tab = self.tabs[self.active]
        with contextlib.suppress(Exception):
            tab.on_quit()
        self.remove_project(tab.project)
        if not self.tabs:
            if self.hotkey_adapter is not None:
                with contextlib.suppress(Exception):
                    self.hotkey_adapter.unregister()
            self._cancel_poll()

    def _on_quit_all(self) -> None:
        """Quit every watcher in tab order; sessions stay attachable."""
        for tab in self.tabs:
            with contextlib.suppress(Exception):
                tab.on_quit()
        if self.hotkey_adapter is not None:
            self.hotkey_adapter.unregister()
        self._cancel_poll()
        self.root.destroy()  # type: ignore[attr-defined]

    def _schedule_poll(self) -> None:
        self._cancel_poll()
        self._poll_after = self.root.after(  # type: ignore[attr-defined]
            self.poll_interval_ms, self._poll
        )

    def _cancel_poll(self) -> None:
        if self._poll_after is not None:
            with contextlib.suppress(Exception):
                self.root.after_cancel(self._poll_after)  # type: ignore[attr-defined]
            self._poll_after = None

    def _poll(self) -> None:
        self._poll_after = None
        self._refresh()
        self._schedule_poll()

    def _refresh(self) -> None:
        models: list[dict] = []
        queue_texts: list[str] = []
        queue_specs: list[str] = []
        for tab in self.tabs:
            try:
                status = tab.status_fn()
            except Exception as exc:
                model = build_robot_view_model({})
                model["indicator"] = "stopped"
                model["indicator_text"] = "UNREACHABLE"
                model["failure"] = str(exc)
                models.append(model)
            else:
                models.append(build_robot_view_model(status))
            summary = self._queue_summary(tab)
            try:
                queue_texts.append(format_hub_queue_text(summary))
            except Exception as exc:
                queue_texts.append(f"queue: n/a ({exc})")
            if str(summary.get("unavailable") or ""):
                queue_specs.append("")
            else:
                queue_specs.append(str(summary.get("current_spec") or ""))
        self.models = models
        self.queue_texts = queue_texts
        self.queue_specs = queue_specs
        self.active = min(self.active, max(0, len(self.models) - 1))
        self._render()

    @staticmethod
    def _queue_summary(tab: RobotHubTab) -> dict:
        """Fetch one tab's queue evidence; never raises into the poll loop."""
        if tab.queue_fn is None:
            return {
                "active_count": 0,
                "current_spec": "",
                "open_tasks": 0,
                "total_tasks": 0,
                "unavailable": "no queue source",
            }
        try:
            summary = tab.queue_fn()
        except Exception as exc:
            return {
                "active_count": 0,
                "current_spec": "",
                "open_tasks": 0,
                "total_tasks": 0,
                "unavailable": str(exc),
            }
        if not isinstance(summary, dict):
            return {
                "active_count": 0,
                "current_spec": "",
                "open_tasks": 0,
                "total_tasks": 0,
                "unavailable": "invalid queue summary",
            }
        return summary

    def _render(self) -> None:
        if not self.tabs:
            return
        # Clamp first: a stale active index must render the nearest tab,
        # never kill the poll loop with IndexError.
        self.active = min(self.active, len(self.tabs) - 1)
        hub = self._hub_model()
        with contextlib.suppress(Exception):
            self.root.title(str(hub["title"]))  # type: ignore[attr-defined]
        for index, button in enumerate(self.tab_buttons):
            info = hub["tabs"][index]
            dot = HUB_INDICATOR_DOTS.get(info["indicator"], "?")
            color = HUB_INDICATOR_COLORS.get(info["indicator"], "#f3f4f6")
            with contextlib.suppress(Exception):
                button.configure(  # type: ignore[attr-defined]
                    text=f"{dot} {info['label']}",
                    foreground=color,
                )
        model = self.models[self.active]
        tab = self.tabs[self.active]
        dot = HUB_INDICATOR_DOTS.get(str(model.get("indicator", "")), "?")
        spec = self.queue_specs[self.active] if self.queue_specs else ""
        header = f"{dot} {model.get('indicator_text', '?')} — {spec or tab.label}"
        self.state_label.configure(text=header)
        self.identity_label.configure(text=f"project  {tab.project}")
        with contextlib.suppress(Exception):
            self.session_label.configure(text=f"session  {model.get('identity', '?')}")
            self.queue_label.configure(
                text=self.queue_texts[self.active]
                if self.queue_texts
                else "queue: n/a (no queue source)"
            )
            self.event_label.configure(
                text=f"latest  {model.get('latest_text', 'no activity yet')}"
            )
            self.stats_label.configure(text=str(model.get("run_stats", "")))
            if self.expanded:
                self.stats_label.pack(fill="x")
            else:
                self.stats_label.pack_forget()
            self.toggle_button.configure(
                text="Hide log" if self.expanded else "Show log"
            )
        self._render_log(model)
        actions = model.get("actions", {})
        self.pause_button.configure(
            text="Resume" if model.get("indicator") == "paused" else "Pause"
        )
        self.pause_button.configure(
            state=(
                "normal"
                if actions.get("pause") or actions.get("resume")
                else "disabled"
            )
        )
        self.quit_button.configure(
            state="normal" if actions.get("quit") else "disabled"
        )

    def _render_log(self, model: dict) -> None:
        """Write the read-only log; never raises into the poll loop."""
        if self.log_text is None or not self.expanded:
            return
        activity = model.get("activity", [])
        lines = [format_robot_activity_line(entry) for entry in activity]
        if not lines:
            if model.get("indicator_text") == "UNREACHABLE":
                detail = str(model.get("failure", "") or "").strip()
                lines = [f"watcher unreachable{': ' + detail if detail else ''}"]
            elif model.get("failure"):
                lines = ["(no activity yet)", f"blocked: {model['failure']}"]
            else:
                lines = ["(no activity yet)"]
        lines = lines[-ROBOT_LOG_VIEW_LINES:]
        with contextlib.suppress(Exception):
            self.log_text.configure(state="normal")
        with contextlib.suppress(Exception):
            delete = getattr(self.log_text, "delete", None)
            insert = getattr(self.log_text, "insert", None)
            if callable(delete):
                delete("1.0", "end")
            if callable(insert):
                insert("1.0", "\n".join(lines))
        with contextlib.suppress(Exception):
            self.log_text.configure(state="disabled")


class RobotWatcherBoundary(Protocol):
    """Structural boundary for watchers driven by the floating widget."""

    def status_view(self) -> dict: ...
    def request_pause(self) -> str: ...
    def request_resume(self) -> str: ...
    def request_quit(self) -> str: ...
    def run(self) -> object: ...


def run_robot_widget(
    watcher: RobotWatcherBoundary, *, poll_interval_s: float = 2.0
) -> int:
    """Run a floating robot window around a watcher running in a worker thread.

    The Tk process is a desktop window, not a tmux pane. The watcher owns
    provider observation; the window only reads its status and invokes pause
    or quit callbacks. Closing the window never terminates the provider
    session.
    """
    info = detect_desktop()
    if not info.supported:
        raise CompanionError(f"robot widget unavailable: {info.detail}")
    if not tkinter_available():
        raise CompanionError("robot widget unavailable: Tkinter is not installed")
    import tkinter as tk

    try:
        hotkey = configured_hotkey()
        parse_hotkey(hotkey)
        hotkey_adapter = adapter_for_session(info.session)
    except CompanionError as exc:
        raise CompanionError(f"robot widget unavailable: {exc}") from exc

    root = tk.Tk()
    status_fn = watcher.status_view
    on_pause = watcher.request_pause
    on_quit = watcher.request_quit
    window = RobotWindow(
        root,
        status_fn=status_fn,
        on_pause=on_pause,
        on_resume=watcher.request_resume,
        on_quit=on_quit,
        hotkey_adapter=hotkey_adapter,
        hotkey=hotkey,
        poll_interval_s=poll_interval_s,
    )
    root.protocol("WM_DELETE_WINDOW", window._on_quit)

    def run_watch() -> None:
        with contextlib.suppress(Exception):
            watcher.run()

    thread = threading.Thread(target=run_watch, name="ariadex-robot-watch", daemon=True)
    thread.start()
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print(watcher.request_quit())
        with contextlib.suppress(Exception):
            root.destroy()
    finally:
        hotkey_adapter.unregister()
    return 0


def run_robot_hub(tabs: list[RobotHubTab], *, poll_interval_s: float = 2.0) -> int:
    """Run one hub window around several watchers in worker threads.

    The desktop probe runs before any watcher thread starts, so an
    unsupported desktop starts nothing. Each tab's `run_fn` (when set)
    runs in its own daemon thread; the window only reads tab statuses
    and invokes pause or quit callbacks. Closing the window quits every
    watcher in tab order and never terminates provider sessions.
    """
    if not tabs:
        raise CompanionError("robot hub unavailable: no project entries supplied")
    info = detect_desktop()
    if not info.supported:
        raise CompanionError(f"robot hub unavailable: {info.detail}")
    if not tkinter_available():
        raise CompanionError("robot hub unavailable: Tkinter is not installed")
    import tkinter as tk

    try:
        hotkey = configured_hotkey()
        parse_hotkey(hotkey)
        hotkey_adapter = adapter_for_session(info.session)
    except CompanionError as exc:
        raise CompanionError(f"robot hub unavailable: {exc}") from exc

    root = tk.Tk()
    window = RobotHubWindow(
        root,
        tabs,
        hotkey_adapter=hotkey_adapter,
        hotkey=hotkey,
        poll_interval_s=poll_interval_s,
    )
    root.protocol("WM_DELETE_WINDOW", window._on_quit_all)

    for index, tab in enumerate(tabs):
        if tab.run_fn is None:
            continue

        def run_watch(run: Callable[[], object] = tab.run_fn) -> None:
            with contextlib.suppress(Exception):
                run()

        thread = threading.Thread(
            target=run_watch,
            name=f"ariadex-robot-hub-{index}",
            daemon=True,
        )
        thread.start()
    try:
        root.mainloop()
    except KeyboardInterrupt:
        for tab in tabs:
            with contextlib.suppress(Exception):
                print(tab.on_quit())
        with contextlib.suppress(Exception):
            root.destroy()
    finally:
        hotkey_adapter.unregister()
    return 0


def run_companion(
    project_dir: Path,
    *,
    hotkey: str | None = None,
    editor: str | None = None,
    poll_interval_s: float = POLL_INTERVAL_S,
) -> int:
    """Launch the floating companion. Fail-closed on unsupported desktops.

    Returns the Tk mainloop exit (0). Raises CompanionError when the desktop
    session, the UI toolkit, or the hotkey configuration is unusable; a
    daemon that is merely unreachable is shown as a failure view instead.
    """
    info = detect_desktop()
    if not info.supported:
        raise CompanionError(f"companion unavailable: {info.detail}")
    try:
        selected = configured_hotkey(hotkey)
        parse_hotkey(selected)
    except CompanionError as exc:
        raise CompanionError(f"companion unavailable: {exc}") from exc
    if not tkinter_available():
        raise CompanionError(
            "companion unavailable: Tkinter is not installed; "
            "use `ariadex status` / `ariadex pause` / `ariadex resume`"
        )
    import tkinter as tk

    try:
        root = tk.Tk()
    except Exception as exc:
        raise CompanionError(
            f"companion unavailable: cannot open a window ({exc})"
        ) from exc
    client = CompanionClient(project_dir)
    adapter = adapter_for_session(info.session)
    _window = CompanionWindow(
        root,
        client,
        adapter,
        selected,
        editor=editor,
        poll_interval_s=poll_interval_s,
    )
    with contextlib.suppress(Exception):
        root.mainloop()
    with contextlib.suppress(Exception):
        adapter.unregister()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for detached use: `python -m ariadex.companion`."""
    import argparse

    parser = argparse.ArgumentParser(prog="ariadex companion")
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--hotkey", default=None)
    parser.add_argument("--editor", default=None)
    args = parser.parse_args(argv)
    try:
        return run_companion(Path(args.project), hotkey=args.hotkey, editor=args.editor)
    except CompanionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys as _sys

    raise SystemExit(main(_sys.argv[1:]))
