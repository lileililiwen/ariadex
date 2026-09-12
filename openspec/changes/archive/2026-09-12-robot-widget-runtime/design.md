# Design

The provider classifier reports approval and confirmation as `waiting`, not as
an error. The watcher remains alive, polls again, and resumes automatically
when the provider returns to a stable input-ready or working surface.

The robot window is a separate Tkinter desktop window with `-topmost` enabled
and middle-right geometry. It receives watcher status through a callback and
calls only watcher pause/quit callbacks. It never owns or kills the provider
tmux session.

The watcher command may continue running as the robot process, but its visible
control surface is the desktop window and remains independent of terminal
focus. A later service wrapper may detach process ownership without changing
this window contract.
