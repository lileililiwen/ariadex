## Data flow

```text
read handoff -> inspect repository -> determine next action -> run adapter
    -> collect outcome -> persist handoff -> reset or stop
```

The handoff is a versioned YAML document with session metadata, current spec, status, completed items, unresolved items, next action, and next spec. Every unresolved item has an id, type, description, priority, and status. Deferred items require a target spec and reason.

## Reset policy

`per_spec` is the MVP default. `soft` sends the adapter’s reset operation; `hard` terminates and restarts; `auto` chooses the strongest supported operation. `manual` and `never` never reset automatically.

## Safety

The runner must be restartable and idempotent at handoff boundaries. It must not mark work complete based only on prose from the agent. A failed or interrupted operation is persisted as unresolved or blocked.
