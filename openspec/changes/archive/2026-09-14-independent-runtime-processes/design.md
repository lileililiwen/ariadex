# Design: Independent runtime processes

The daemon is the lifecycle authority and owns durable state and the control
socket. The provider remains a separate process/session identified by PID and
start identity. The widget is a separate Tk process and communicates only by
bounded typed IPC; it never becomes the parent or transport for the provider.

Tk control and polling operations run in worker threads and marshal results
back through `root.after`. The daemon accepts each socket connection and
handles it in a daemon worker thread. Explicit stop remains daemon-owned.
