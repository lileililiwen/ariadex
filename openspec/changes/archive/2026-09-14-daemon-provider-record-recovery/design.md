`provider_runtime.is_reusable` catches the complete psutil lookup error family
(`psutil.Error`) around recorded process identity. A missing or inaccessible
record is therefore non-reusable; the existing adapter path clears/terminates
only the owned record and starts a new provider session. The daemon remains
available to report later failures.
