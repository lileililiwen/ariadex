# Design: Dead-owner lease recovery

Process identity and liveness use the cross-platform `psutil` SDK. Ariadex
does not inspect `/proc`, invoke `os.kill`, or depend on a Linux process
filesystem for ownership recovery.

`concurrency.is_live` treats an unobservable local PID as dead, so a recent
heartbeat cannot strand a lease after a crash. A live PID remains protected.
