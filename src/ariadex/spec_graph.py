"""Spec dependency graph and deterministic execution governance.

Optional per-change metadata declares ordering without mutating specs:

    openspec/changes/<name>/.openspec.yaml
        depends_on: [<predecessor>, ...]

`depends_on` (alias `dependencies`) is a list of change names that must be
verified complete before `<name>` is eligible to start. Absent metadata
means no predecessors. Malformed metadata never crashes scheduling; it
becomes a durable blocker with a reason.

A predecessor counts as verified complete only when the durable handoff
records a completed-spec entry for that name. A predecessor still present
in the active spec directory, or absent from both the directory and the
handoff, is incomplete. Cycles are rejected deterministically; an explicit
handoff target that is missing or ineligible is preserved as unresolved
work with a reason instead of silently selecting another spec.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import handoff as handoff_mod

METADATA_FILENAME = ".openspec.yaml"
DEPENDENCY_KEYS = ("depends_on", "dependencies")

_COMPLETED_SPEC_RE = re.compile(r"completed spec `([^`]+)`")


class SpecGraphError(Exception):
    """Malformed dependency metadata that cannot be trusted."""


def read_spec_dependencies(spec_dir: Path, name: str) -> list[str]:
    """Return the declared predecessors for one active change.

    Raises SpecGraphError on malformed metadata (non-mapping YAML,
    non-list dependencies, empty entries, self-dependency).
    """
    meta_path = spec_dir / name / METADATA_FILENAME
    if not meta_path.is_file():
        return []
    try:
        raw = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecGraphError(
            f"spec `{name}` has malformed {METADATA_FILENAME}: {exc}"
        ) from exc
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise SpecGraphError(
            f"spec `{name}` has malformed {METADATA_FILENAME}: mapping required"
        )
    declared: list[str] = []
    seen_key = False
    for key in DEPENDENCY_KEYS:
        if key not in raw or raw[key] is None:
            continue
        seen_key = True
        value = raw[key]
        if not isinstance(value, list):
            raise SpecGraphError(
                f"spec `{name}` has invalid `{key}`: list of change names required"
            )
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise SpecGraphError(
                    f"spec `{name}` has invalid `{key}`: "
                    "non-empty change names required"
                )
            cleaned = entry.strip()
            if cleaned == name:
                raise SpecGraphError(
                    f"spec `{name}` depends on itself: cycle of length 1"
                )
            if cleaned not in declared:
                declared.append(cleaned)
    if not seen_key:
        return []
    return declared


def load_graph(
    project_dir: Path, spec_dir: str
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Build the deterministic dependency graph over active changes.

    Returns (graph, errors) where graph maps each active change (sorted) to
    its declared predecessors (declared order, deduplicated) and errors maps
    each change with malformed metadata to its reason. Callers treat errors
    as blockers; they never raise.
    """
    base = project_dir / spec_dir
    graph: dict[str, list[str]] = {}
    errors: dict[str, str] = {}
    if not base.is_dir():
        return graph, errors
    names = sorted(entry.name for entry in base.iterdir() if entry.is_dir())
    for name in names:
        try:
            graph[name] = read_spec_dependencies(base, name)
        except SpecGraphError as exc:
            graph[name] = []
            errors[name] = str(exc)
        except OSError as exc:
            graph[name] = []
            errors[name] = f"spec `{name}` metadata unreadable: {exc}"
    return graph, errors


def completed_spec_names(handoff: handoff_mod.Handoff) -> set[str]:
    """Verified-complete predecessors from durable handoff history."""
    names: set[str] = set()
    for item in handoff.completed:
        summary = getattr(item, "summary", "") or ""
        for match in _COMPLETED_SPEC_RE.finditer(summary):
            candidate = match.group(1).strip()
            if candidate:
                names.add(candidate)
    return names


def find_missing(
    graph: dict[str, list[str]],
    active: set[str],
    completed: set[str],
) -> dict[str, list[str]]:
    """Predecessors in neither the active directory nor handoff history."""
    missing: dict[str, list[str]] = {}
    for name in sorted(graph):
        absent = sorted(
            {dep for dep in graph[name] if dep not in active and dep not in completed}
        )
        if absent:
            missing[name] = absent
    return missing


def find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Deterministic cycle detection over edges between active changes.

    Only dependencies that are themselves active can form a cycle;
    predecessors already completed or entirely missing are not cycle edges.
    Returns cycles sorted by their normalized rotation (smallest member
    first) so repeated runs report identical output.
    """
    active = set(graph)
    cycles: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    color: dict[str, int] = {}
    stack: list[str] = []

    def _normalize(cycle: list[str]) -> list[str]:
        pivot = cycle.index(min(cycle))
        return cycle[pivot:] + cycle[:pivot]

    def _visit(node: str) -> None:
        color[node] = 1
        stack.append(node)
        for dep in sorted(set(graph.get(node, ())) & active):
            state = color.get(dep, 0)
            if state == 0:
                _visit(dep)
            elif state == 1 and dep in stack:
                raw = stack[stack.index(dep) :]
                norm = _normalize(list(raw))
                key = tuple(norm)
                if key not in seen:
                    seen.add(key)
                    cycles.append(norm)
        stack.pop()
        color[node] = 2

    for name in sorted(graph):
        if color.get(name, 0) == 0:
            _visit(name)
    cycles.sort()
    return cycles


def specs_in_cycles(cycles: list[list[str]]) -> set[str]:
    members: set[str] = set()
    for cycle in cycles:
        members.update(cycle)
    return members


def incomplete_predecessors(
    name: str,
    graph: dict[str, list[str]],
    completed: set[str],
) -> list[str]:
    """Declared predecessors not yet verified complete (sorted)."""
    return sorted(dep for dep in graph.get(name, []) if dep not in completed)


def eligible_specs(
    graph: dict[str, list[str]],
    completed: set[str],
) -> list[str]:
    """Active changes whose predecessors are all verified complete.

    Excludes changes with missing predecessors, in dependency cycles, or
    already verified complete. Membership is driven by dependency state,
    never by raw directory position: a blocked change early in directory
    order never shadows a ready change later in it. Order among ready
    peers is deterministic topological depth first (shallower changes
    unblock more work), alphabetical among equal depths.
    """
    active = set(graph)
    missing = find_missing(graph, active, completed)
    blocked = specs_in_cycles(find_cycles(graph))
    ready = sorted(
        name
        for name in active
        if name not in missing
        and name not in blocked
        and name not in completed
        and all(dep in completed for dep in graph.get(name, []))
    )
    depth_cache: dict[str, int] = {}

    def _depth(name: str, seen: frozenset[str] = frozenset()) -> int:
        if name in depth_cache:
            return depth_cache[name]
        if name in seen:
            return 0
        deps = [dep for dep in graph.get(name, []) if dep in active]
        depth = 0 if not deps else 1 + max(_depth(dep, seen | {name}) for dep in deps)
        depth_cache[name] = depth
        return depth

    return sorted(ready, key=lambda name: (_depth(name), name))


def validate_target(
    target: str,
    graph: dict[str, list[str]],
    active: set[str],
    completed: set[str],
) -> tuple[bool, str]:
    """Check an explicit handoff target against dependency state.

    Returns (True, "") when the target may schedule, else (False, reason)
    where reason names the missing, cyclic, or incomplete predecessors.
    """
    if target not in active:
        return False, f"spec `{target}` is missing from the spec directory"
    missing = find_missing(graph, active, completed)
    if target in missing:
        names = ", ".join(f"`{dep}`" for dep in missing[target])
        return (
            False,
            f"spec `{target}` depends on missing {names}; "
            "declare the predecessor or remove the dependency",
        )
    cycles = find_cycles(graph)
    members = specs_in_cycles(cycles)
    if target in members:
        for cycle in cycles:
            if target in cycle:
                chain = " -> ".join(f"`{part}`" for part in [*cycle, cycle[0]])
                return (
                    False,
                    f"spec `{target}` is in dependency cycle {chain}; "
                    "break the cycle before scheduling",
                )
        return (
            False,
            f"spec `{target}` is in dependency cycle; break the cycle first",
        )
    incomplete = incomplete_predecessors(target, graph, completed)
    if incomplete:
        names = ", ".join(f"`{dep}`" for dep in incomplete)
        return (
            False,
            f"spec `{target}` waits on incomplete {names}; complete predecessors first",
        )
    return True, ""
