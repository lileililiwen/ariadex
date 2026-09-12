# Design: Human-yield hotkey and floating control

## Interaction model

### Concrete first target

The first desktop implementation MUST target Linux with an X11 session. It
MUST use Python Tkinter for the always-on-top window and a small isolated X11
global-hotkey adapter for `Ctrl+Esc` registration. The Tkinter UI and hotkey
adapter MUST be separate from daemon logic and MUST communicate only through
the daemon’s Unix socket. Wayland, macOS, and Windows integrations are later
platform-adapter work and MUST report unsupported status rather than pretend
to be installed.

The collapsed control resembles a mini-player: a status indicator, current
work label, and compact play/pause/stop actions. Clicking expands details and
an optional command field. The companion may open the configured editor or
agent session, but the daemon remains responsible for launching and tracking
them.

The default placement is middle-right, always-on-top, draggable, and persisted
per user. It must be dismissible or hidden without stopping the daemon.

The initial window MUST be undecorated or minimally decorated, approximately
240–320 pixels wide, vertically centered, and offset from the right screen
edge. It MUST poll or subscribe to daemon status at a bounded interval and
refresh after every command response; it MUST not busy-loop.

## Yield semantics

The global hotkey sends a typed `pause` or `resume` IPC request. It does not
inject input into the focused application. Pause follows existing cancellation
boundaries and leaves the user free to edit or operate the provider manually.
Resume first performs the daemon’s full reconciliation and only then enables
AUTO scheduling.

The hotkey is configurable and registration failure is visible in the widget
and doctor output; ordinary keyboard input continues to work when the widget
is not focused. The first implementation must isolate OS-specific registration
behind an adapter and define its supported desktop target before packaging.

## Accessibility and safety

Controls require accessible names, visible focus, keyboard navigation within
the widget, and a text status equivalent to color indicators. The companion
must not capture global input beyond the configured hotkey and must display
confirmation or an explicit state transition for stop.

## Boundaries

All state changes use the daemon IPC protocol. The UI has no direct access to
the state file, lease file, provider adapter, or tmux socket.
