# Design

The collapsed target becomes 190px and the expanded target becomes 560px.
The titlebar is fixed at 30px and the action row at 36px with geometry
propagation disabled, so the initial `STARTING` render and later provider
state render use the same vertical structure. Existing screen clamping uses
the active target height, so taller windows remain on-screen.

During live-daemon `start` reconciliation, Ariadex reads daemon state. If it
is `PAUSE`, it sends the existing typed `resume` request once and keeps the
daemon/widget state authoritative. Failure to resume is left visible through
normal daemon state and does not cause provider teardown.
