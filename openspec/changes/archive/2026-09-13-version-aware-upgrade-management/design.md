## Design

Keep `ariadex.__version__` as the package source of truth. Add a standard
library version probe that compares the installed distribution with the
configured package index using bounded network access and explicit failure
states: current, update-available, ahead/local, unavailable, or invalid.

Detect installation provenance from distribution metadata and executable
context. The upgrade executor must select the matching owner tool: pipx for a
pipx environment, the active Python environment for a normal installation,
and a clear local-editable recovery instruction for editable/source installs.
It must never run a shell command assembled from package metadata and must
show the planned operation before confirmation.

`--check` performs no mutation. `--yes` confirms the selected safe upgrade in
non-interactive environments. A running daemon/provider is left untouched;
the result records that newly installed code applies to future starts and
reports the running version in status/diagnostics. Upgrade failures preserve
the existing installation and provide the next manual action.

Release validation reuses the existing tag, artifact metadata, PyPI exact
version, and clean-install checks. Upgrade tests use fake index and installer
executors and never mutate the developer environment.
