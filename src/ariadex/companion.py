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
WIDGET_WIDTH = 280

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
    """Whether the Tkinter UI toolkit imports (no window is created)."""
    try:
        import tkinter  # noqa: F401

        return True
    except ImportError:
        return False


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
    return {
        "indicator": indicator,
        "indicator_text": indicator.upper(),
        "mode": mode,
        "alive": alive,
        "work_label": work_label,
        "actions": actions,
        "reconciliation_pending": indicator == "paused",
        "failure": None,
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
    actions = model.get("actions", {})
    enabled = sorted(name for name, on in actions.items() if on)
    lines.append(f"actions: {', '.join(enabled) if enabled else 'none available'}")
    if model.get("reconciliation_pending"):
        lines.append("reconciliation: pending — play resynchronizes before scheduling")
    if model.get("failure"):
        lines.append(f"failure: {model['failure']}")
    return "\n".join(lines)


def default_geometry(screen_width: int, screen_height: int) -> tuple[int, int]:
    """Middle-right placement for the collapsed widget."""
    x = max(0, screen_width - WIDGET_WIDTH - 24)
    y = max(0, screen_height // 2 - 60)
    return x, y


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
    Expanded: full text status, hotkey field, reconcile/editor/session/hide/quit.
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
        self.hotkey_active = False
        self.hotkey_error: str | None = None
        self.expanded = False
        self._poll_after: str | None = None
        self._save_after: str | None = None

        assert isinstance(root, tk.Tk)
        root.title("Ariadex")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.geometry(f"{WIDGET_WIDTH}x84")
        try:
            position = self._restored_geometry(root)
        except Exception:
            position = None
        if position is None:
            position = default_geometry(
                root.winfo_screenwidth(), root.winfo_screenheight()
            )
        root.geometry(f"+{position[0]}+{position[1]}")

        self.frame = tk.Frame(root, borderwidth=1, relief="solid", padx=8, pady=6)
        self.frame.pack(fill="both", expand=True)

        self.titlebar = tk.Frame(self.frame)
        self.titlebar.pack(fill="x")
        self.dot = tk.Label(self.titlebar, text="●", width=2)
        self.dot.pack(side="left")
        self.state_label = tk.Label(self.titlebar, text="STARTING", anchor="w")
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
        self.hide_button = tk.Button(
            self.titlebar,
            text="-",
            width=2,
            name="hide-button",
            takefocus=True,
            command=self._hide,
        )
        self.hide_button.pack(side="right")

        self.work_label = tk.Label(
            self.frame,
            text="(connecting)",
            anchor="w",
            justify="left",
            wraplength=WIDGET_WIDTH - 20,
        )
        self.work_label.pack(fill="x")

        controls = tk.Frame(self.frame)
        controls.pack(fill="x", pady=(4, 0))
        self.play_button = tk.Button(
            controls,
            text="▶ Play",
            name="play-button",
            takefocus=True,
            command=self._on_play,
        )
        self.play_button.pack(side="left", expand=True, fill="x")
        self.pause_button = tk.Button(
            controls,
            text="⏸ Yield",
            name="pause-button",
            takefocus=True,
            command=self._on_pause,
        )
        self.pause_button.pack(side="left", expand=True, fill="x")
        self.stop_button = tk.Button(
            controls,
            text="⏹ Stop",
            name="stop-button",
            takefocus=True,
            command=self._on_stop,
        )
        self.stop_button.pack(side="left", expand=True, fill="x")

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
            text="Quit companion (daemon keeps running)",
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

    def _drag_move(self, event: object) -> None:
        if self._drag_origin is None:
            return
        x = int(getattr(event, "x_root", 0)) - self._drag_origin[0]
        y = int(getattr(event, "y_root", 0)) - self._drag_origin[1]
        self.root.geometry(f"+{x}+{y}")  # type: ignore[attr-defined]

    def _drag_stop(self, _event: object) -> None:
        self._drag_origin = None
        if self._save_after is not None:
            with contextlib.suppress(Exception):
                self.root.after_cancel(self._save_after)  # type: ignore[attr-defined]
        self._save_after = self.root.after(500, self._persist_geometry)  # type: ignore[attr-defined]

    def _persist_geometry(self) -> None:
        self._save_after = None
        save_user_config(
            {
                "x": int(self.root.winfo_x()),  # type: ignore[attr-defined]
                "y": int(self.root.winfo_y()),  # type: ignore[attr-defined]
            }
        )

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

    def _notice(self, text: str) -> None:
        model = dict(self.model)
        model["failure"] = text
        self.model = model
        self._render()

    def _toggle_expanded(self) -> None:
        self.expanded = not self.expanded
        if self.expanded:
            self.details.pack(fill="x")
            self.toggle_button.configure(text="▴")
            self.root.geometry(f"{WIDGET_WIDTH}x340")  # type: ignore[attr-defined]
        else:
            self.details.pack_forget()
            self.toggle_button.configure(text="▾")
            self.root.geometry(f"{WIDGET_WIDTH}x84")  # type: ignore[attr-defined]

    def _hide(self) -> None:
        # Hidden, not stopped: the daemon keeps scheduling; the hotkey stays
        # armed. Restored from the taskbar/dock (iconify, never withdraw).
        self.root.iconify()  # type: ignore[attr-defined]

    def _quit(self) -> None:
        # Quits only the companion; the daemon is untouched.
        self._cancel_poll()
        self.adapter.unregister()
        self.root.destroy()  # type: ignore[attr-defined]

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
