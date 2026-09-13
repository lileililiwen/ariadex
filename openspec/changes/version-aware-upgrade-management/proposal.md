## Why

The published package remains at `0.1.0` while the checkout has later
commits. Users can therefore run an older installed Ariadex without a clear,
safe way to discover or apply an available release, and a running managed
runtime can make version drift difficult to diagnose.

## What Changes

Add a user-facing `ariadex upgrade` workflow with read-only version checking,
installation-provenance detection, confirmation before package mutation,
provider/runtime version diagnostics, and exact release verification.

## Non-goals

Do not self-publish releases, silently replace editable checkouts with PyPI,
interrupt running provider sessions, mutate project `.ariadex` state, or
support arbitrary package indexes without explicit configuration.
