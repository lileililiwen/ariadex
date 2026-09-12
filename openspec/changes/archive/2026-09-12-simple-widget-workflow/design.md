# Design: Self-contained widget workflow

`widget` initializes the project, checks Tkinter, and only then starts the
daemon and launches the existing companion window. When Tkinter is missing and
a supported package manager exists, interactive use asks for confirmation;
`--yes` supplies that explicit confirmation for automation. Installation
failure is reported and the daemon is not started. Unsupported package
managers receive the exact manual install hint.

The historical `companion` parser remains accepted for compatibility but is
hidden from normal help. README and command tables describe `widget` as the
only normal desktop workflow. No provider, editor, tmux-input, or autostart
behavior changes.
