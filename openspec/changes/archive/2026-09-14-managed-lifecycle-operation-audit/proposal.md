## Why

A provider can disappear while the Ariadex daemon remains alive, but the
current evidence does not identify whether Ariadex, tmux, the provider, or an
external signal caused it. Record destructive lifecycle operations and the
unexpected-exit observation before the evidence is lost.

## What Changes

Add durable, bounded lifecycle audit records for managed provider operations
and unexpected provider exits.

## Scope

- provider startup and termination;
- owned process termination and tmux session termination;
- actor, PID/session identity, generation, result, and bounded pane evidence;
- unexpected provider exit while the managed daemon remains alive.

## Non-goals

- changing provider behavior or adding provider API calls;
- killing or restarting a provider automatically;
- changing OpenDockify OpenSpec state.
