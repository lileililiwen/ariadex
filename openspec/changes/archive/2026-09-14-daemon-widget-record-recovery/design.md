`widget_runtime.is_healthy` catches `psutil.Error` around the recorded process
identity lookup. A missing or inaccessible widget PID therefore follows the
existing replacement path instead of terminating daemon startup.
