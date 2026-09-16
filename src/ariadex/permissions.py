"""Safe temporary permission policy for provider file requests.

Provider permission prompts for harmless coding temporary files can stall an
unattended run. Granting all of shared `/tmp` would be unsafe: it is not
project-owned and may hold other users' files, symlinks, sockets, or
secrets. This module evaluates one parsed provider request against an
explicit policy and a private, project-scoped temporary root.

Fail-closed contract: unknown or ambiguous requests, traversal, symlink
escape, shared `/tmp`, and privileged operations (execution, chmod/chown,
sudo, shell metacharacters) never produce automatic approval. The default
policy is `prompt`: the supervisor sends no automatic approval and leaves
the provider waiting for explicit human action. Standard library only.
"""

from __future__ import annotations

import dataclasses
import os
import re
from pathlib import Path

#: Configured `permission_policy` values. `prompt` (default) never sends
#: automatic approval; `deny` additionally records every parsed request as
#: denied; `project-temp-auto` approves only contained temp-root requests;
#: `allowlist` approves only contained allowlist requests; `auto`
#: (explicit opt-in) approves every parsed request with an enabled
#: operation at any path, and still waits on unparsed surfaces.
PERMISSION_POLICIES = ("prompt", "project-temp-auto", "allowlist", "deny", "auto")

#: File operations the policy may approve. Anything else (execution,
#: chmod/chown, sudo, shell operators) is never approved.
PERMISSION_ACTIONS = ("read", "write", "create", "delete")

#: Default private project-scoped temporary root (project-relative).
DEFAULT_TEMP_ROOT = ".ariadex/tmp"

#: Decision outcomes. Both `waiting` and `deny` send no provider input;
#: `waiting` expects a human answer in the provider session, `deny`
#: additionally records that automatic approval is refused by policy.
DECISIONS = ("allow", "waiting", "deny")

#: Bounds for parsed/evidenced text (diagnostics stay bounded and redacted).
MAX_PATH_CHARS = 512
MAX_REASON_CHARS = 280

#: Privileged or destructive markers: any request containing one of these
#: (word-boundaried) is denied automatic approval, never parsed as a file
#: action. Shell metacharacters are checked separately over the path token.
_PRIVILEGED_WORDS = (
    "sudo",
    "su",
    "chmod",
    "chown",
    "chgrp",
    "exec",
    "eval",
    "shell",
    "script",
    "curl",
    "wget",
    "ssh",
    "rm",
    "mkfs",
    "dd",
    "mount",
    "passwd",
)

_PRIVILEGED_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:" + "|".join(_PRIVILEGED_WORDS) + r")(?![A-Za-z0-9_])"
)

#: Shell operator characters that must never appear in an approved path.
_SHELL_CHARS = ("|", "&", ";", "$", "`", "(", ")", "<", ">", "\n", "\r", "\0")

#: Operation synonyms mapped to the canonical permitted action. Words that
#: name execution or mutation outside read/write/create/delete are
#: deliberately absent: such requests stay unparsed (waiting), never
#: approved.
_OPERATION_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("read", ("read", "open", "view", "cat", "display", "show")),
    ("write", ("write", "edit", "modify", "update", "save", "append")),
    ("create", ("create", "new", "make", "touch", "mkdir")),
    ("delete", ("delete", "remove", "unlink", "rmdir")),
)

_OPERATION_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    + "|".join(word for _, words in _OPERATION_WORDS for word in words)
    + r")(?![A-Za-z0-9_])"
)

#: Directory nouns and access verbs for provider directory-access prompts
#: (for example a choice selector granting an external working directory).
#: No concrete path is special-cased here; containment always comes from
#: operator configuration at evaluation time.
_DIRECTORY_NOUNS = ("director", "folder")
_DIRECTORY_VERBS = ("access", "allow", "permit", "grant")

#: Glob characters that must never appear in an approved primary directory.
_DIRECTORY_GLOB_CHARS = ("*", "?", "[")

#: Path token shapes: quoted, backticked, or bare absolute/relative tokens.
_QUOTED_PATH_RE = re.compile(r"[`\"']([^`\"'\n]{1,512})[`\"']")
_BARE_PATH_RE = re.compile(r"(?<![\w@])(~?(?:/|\./)(?:[^\s'\"`|&;<>$(){}[\]]+))")


@dataclasses.dataclass
class ParsedRequest:
    """One conservatively parsed provider file request."""

    operation: str
    requested_path: str


@dataclasses.dataclass
class PermissionDecision:
    """Evaluated outcome for one provider permission request."""

    provider: str
    operation: str
    requested_path: str
    normalized_path: str
    policy: str
    result: str
    reason: str
    approve_input: str = ""


def canonical_operation(word: str) -> str | None:
    """Canonical permitted action for an operation synonym, else None."""
    lowered = word.lower()
    for canonical, synonyms in _OPERATION_WORDS:
        if lowered in synonyms:
            return canonical
    return None


def contains_privileged_markers(text: str) -> bool:
    """True when the request names privileged/destructive operations."""
    return _PRIVILEGED_RE.search(text or "") is not None


def _path_candidates(text: str) -> list[str]:
    """Ordered path-like tokens from quoted spans, then bare tokens.

    A quoted span counts only when it looks like a path (contains a
    slash or starts with `~`/`.`): quoted operation words such as `cat`
    must not make an otherwise precise request ambiguous.
    """
    found: list[str] = []
    for match in _QUOTED_PATH_RE.finditer(text or ""):
        candidate = match.group(1).strip()
        if (
            candidate
            and candidate not in found
            and ("/" in candidate or candidate.startswith(("~", ".")))
        ):
            found.append(candidate)
    for match in _BARE_PATH_RE.finditer(text or ""):
        candidate = match.group(1).strip().rstrip(".,:;!?")
        if candidate and candidate not in found:
            found.append(candidate)
    return [item[:MAX_PATH_CHARS] for item in found]


def parse_permission_request(text: str) -> ParsedRequest | None:
    """Parse one provider file request from a pane tail (fail-closed).

    Returns the canonical operation plus the single unambiguous requested
    path, or None when the surface is unknown, ambiguous (zero or several
    distinct paths), privileged, or names no permitted file action.
    Provider directory-access prompts (one unambiguous directory on the
    access line) additionally parse as a `read` request for the directory
    itself; surrounding pattern and history lines are context only. A
    failed file parse (for example scrollback commands that add extra
    paths) falls through to the directory attempt instead of stopping.
    Callers must treat None as waiting: never approve, never deny-blindly.
    """
    tail = "\n".join((text or "").splitlines()[-16:])
    if not tail.strip():
        return None
    if contains_privileged_markers(tail):
        return None
    lowered = tail.lower()
    operation: str | None = None
    for canonical, synonyms in _OPERATION_WORDS:
        for word in synonyms:
            if re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(word)}(?![A-Za-z0-9_])", lowered
            ):
                operation = canonical
                break
        if operation is not None:
            break
    if operation is not None:
        candidates = _path_candidates(tail)
        if len(candidates) == 1:
            requested = candidates[0]
            if not any(char in requested for char in _SHELL_CHARS) and (
                requested.strip()
            ):
                return ParsedRequest(operation=operation, requested_path=requested)
    return _parse_directory_access(tail)


def _parse_directory_access(tail: str) -> ParsedRequest | None:
    """Parse one provider directory-access prompt (fail-closed).

    Only the access line itself (the line naming directory access) may
    contribute the requested directory: it must carry exactly one
    path-like token with no glob characters. Every other line is context
    (match patterns, command history) and never widens the grant.
    A directory grant is recorded as a `read` of the directory itself;
    policy containment and `permission_actions` gating apply unchanged.
    """
    access_line: str | None = None
    for raw in (tail or "").splitlines():
        lowered = raw.lower()
        if any(verb in lowered for verb in _DIRECTORY_VERBS) and any(
            noun in lowered for noun in _DIRECTORY_NOUNS
        ):
            access_line = raw
            break
    if access_line is None:
        return None
    found: list[str] = []
    for match in _QUOTED_PATH_RE.finditer(access_line):
        candidate = match.group(1).strip()
        if (
            candidate
            and candidate not in found
            and ("/" in candidate or candidate.startswith(("~", ".")))
        ):
            found.append(candidate)
    for match in _BARE_PATH_RE.finditer(access_line):
        candidate = match.group(1).strip().rstrip(".,:;!?")
        if candidate and candidate not in found:
            found.append(candidate)
    if len(found) != 1:
        return None
    requested = found[0][:MAX_PATH_CHARS]
    if any(char in requested for char in _DIRECTORY_GLOB_CHARS):
        return None
    if any(char in requested for char in _SHELL_CHARS):
        return None
    if not requested.strip():
        return None
    return ParsedRequest(operation="read", requested_path=requested)


def temp_root_path(project_dir: Path, configured: str) -> Path:
    """Resolve the configured temp root; fail closed outside the project."""
    text = (configured or "").strip()
    if not text:
        raise ValueError(
            "permission_temp_root is empty; configure a project-relative "
            "directory such as `.ariadex/tmp`"
        )
    candidate = Path(text)
    if candidate.is_absolute():
        raise ValueError(
            f"permission_temp_root `{text[:120]}` must be project-relative, "
            "never absolute"
        )
    base = project_dir.resolve()
    resolved = (base / candidate).resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(
            f"permission_temp_root `{text[:120]}` escapes the project; "
            "configure a directory inside the project"
        )
    return resolved


def ensure_temp_root(project_dir: Path, configured: str) -> Path:
    """Create the private project-scoped temp root with owner-only access.

    Creates missing parents, repairs group/other-accessible permissions to
    0700 best-effort, and refuses paths that escape the project. Raises
    ValueError for misconfiguration and OSError for I/O failures so the
    caller stays waiting instead of approving.
    """
    root = temp_root_path(project_dir, configured)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"cannot create permission temp root `{root}`: {exc}") from exc
    if os.name != "nt":
        try:
            bits = root.stat().st_mode & 0o777
            if bits & 0o077:
                os.chmod(root, 0o700)
        except OSError as exc:
            raise OSError(
                f"cannot secure permission temp root `{root}`: {exc}"
            ) from exc
    return root


def _informational_paths(
    parsed: ParsedRequest | None, project_dir: Path | None
) -> tuple[str, str, str]:
    """Parsed (operation, requested, normalized) for non-approved outcomes.

    Prompt and deny policies send no approval, but the diagnostic still
    names what the provider asked for whenever it parsed cleanly.
    """
    if parsed is None:
        return "", "", ""
    requested = parsed.requested_path[:MAX_PATH_CHARS]
    if project_dir is None:
        return parsed.operation, requested, ""
    resolved, _ = _resolve_requested(project_dir, requested)
    return parsed.operation, requested, str(resolved) if resolved else ""


def _resolve_requested(project_dir: Path, requested: str) -> tuple[Path | None, str]:
    """Resolve the requested path against the project (symlinks resolved).

    Returns `(resolved, note)`; `resolved` is None when the path is
    empty or unresolvable. `~` expands to the user home (which containment
    then rejects unless explicitly allowlisted).
    """
    text = (requested or "").strip()
    if not text:
        return None, "empty requested path"
    expanded = os.path.expanduser(text)
    candidate = Path(expanded)
    if not candidate.is_absolute():
        candidate = project_dir.resolve() / candidate
    try:
        return candidate.resolve(strict=False), ""
    except OSError as exc:
        return None, f"path unresolvable: {exc}"


def _contained(resolved: Path, roots: list[Path]) -> bool:
    """True when `resolved` lies inside one of the containment roots."""
    return any(resolved == root or root in resolved.parents for root in roots)


def _redirected_outside(base: Path, requested: str, resolved: Path) -> bool:
    """True when a project-anchored path resolved outside the project.

    Relative paths without `..` and absolute paths beneath `base` start
    inside the project; resolving outside means a symlink redirected them.
    Absolute paths elsewhere are plain outside paths (waiting), not
    redirects. `..` segments are handled as traversal before this check.
    """
    candidate = Path(requested)
    if candidate.is_absolute():
        try:
            candidate.relative_to(base)
        except ValueError:
            return False
        anchored_inside = True
    else:
        anchored_inside = ".." not in candidate.parts
    if not anchored_inside:
        return False
    return resolved != base and base not in resolved.parents


def allowlist_roots(project_dir: Path, allowlist: list[str]) -> list[Path]:
    """Allowlist entries resolved against the project (best-effort)."""
    roots: list[Path] = []
    base = project_dir.resolve()
    for entry in allowlist or []:
        text = str(entry or "").strip()
        if not text:
            continue
        candidate = Path(os.path.expanduser(text))
        if not candidate.is_absolute():
            candidate = base / candidate
        try:
            roots.append(candidate.resolve(strict=False))
        except OSError:
            continue
    return roots


def evaluate(
    *,
    provider: str,
    parsed: ParsedRequest | None,
    raw_tail: str = "",
    policy: str = "prompt",
    temp_root: Path | None = None,
    allowlist: list[Path] | None = None,
    allowed_actions: list[str] | None = None,
    approve_input: str = "",
    project_dir: Path | None = None,
) -> PermissionDecision:
    """Decide one provider permission request (never raises for policy).

    Precedence: explicit `deny`/`prompt` policies first, then unparsable
    surfaces (waiting), privileged markers (deny), unresolvable paths
    (waiting), containment (outside root/allowlist waits; traversal and
    symlink escape deny), disabled operations (deny), and finally approval
    with the adapter-owned keystroke.
    """
    actions = (
        list(allowed_actions)
        if allowed_actions is not None
        else list(PERMISSION_ACTIONS)
    )
    roots = list(allowlist) if allowlist is not None else []
    if temp_root is not None:
        roots.append(temp_root)
    if policy not in PERMISSION_POLICIES:
        operation, requested, normalized = _informational_paths(parsed, project_dir)
        return PermissionDecision(
            provider,
            operation,
            requested,
            normalized,
            policy,
            "waiting",
            f"unknown permission_policy `{policy[:64]}`; "
            "answer the approval in the provider session",
        )
    if policy == "prompt":
        operation, requested, normalized = _informational_paths(parsed, project_dir)
        return PermissionDecision(
            provider,
            operation,
            requested,
            normalized,
            policy,
            "waiting",
            "policy `prompt`: automatic approval is disabled; answer the "
            "approval in the provider session; watching resumes afterwards",
        )
    if policy == "deny":
        operation, requested, normalized = _informational_paths(parsed, project_dir)
        return PermissionDecision(
            provider,
            operation,
            requested,
            normalized,
            policy,
            "deny",
            "policy `deny`: automatic approval is refused; answer the "
            "approval in the provider session",
        )
    if parsed is None:
        if contains_privileged_markers(raw_tail):
            return PermissionDecision(
                provider,
                "",
                "",
                "",
                policy,
                "deny",
                "privileged or destructive request (execution, chmod/chown, "
                "sudo, or shell operators); automatic approval is refused; "
                "answer the approval in the provider session",
            )
        return PermissionDecision(
            provider,
            "",
            "",
            "",
            policy,
            "waiting",
            "unparsable or ambiguous provider request; no automatic "
            "approval without a verified operation and path; answer the "
            "approval in the provider session",
        )
    requested = parsed.requested_path[:MAX_PATH_CHARS]
    if project_dir is None:
        return PermissionDecision(
            provider,
            parsed.operation,
            requested,
            "",
            policy,
            "waiting",
            "project directory unavailable; containment unverifiable; "
            "answer the approval in the provider session",
        )
    resolved, note = _resolve_requested(project_dir, requested)
    if resolved is None:
        return PermissionDecision(
            provider,
            parsed.operation,
            requested,
            "",
            policy,
            "waiting",
            f"{note}; answer the approval in the provider session",
        )
    normalized = str(resolved)
    if parsed.operation not in PERMISSION_ACTIONS:
        return PermissionDecision(
            provider,
            parsed.operation,
            requested,
            normalized,
            policy,
            "deny",
            f"operation `{parsed.operation}` is outside read/write/create/"
            "delete; automatic approval is refused",
        )
    if parsed.operation not in actions:
        return PermissionDecision(
            provider,
            parsed.operation,
            requested,
            normalized,
            policy,
            "deny",
            f"operation `{parsed.operation}` is not in permission_actions; "
            "automatic approval is refused; adjust the list or answer manually",
        )
    if policy == "auto":
        # Hands-off opt-in: containment is the only gate skipped. Parsing,
        # privileged-marker refusal, path resolution, and the operation
        # allowlist above all still apply.
        return PermissionDecision(
            provider,
            parsed.operation,
            requested,
            normalized,
            policy,
            "allow",
            f"policy `auto`: approving parsed `{parsed.operation}` at any "
            "path with the provider-owned keystroke",
            approve_input=approve_input,
        )
    if _contained(resolved, roots):
        return PermissionDecision(
            provider,
            parsed.operation,
            requested,
            normalized,
            policy,
            "allow",
            f"contained `{parsed.operation}` inside the project temp root "
            "or allowlist; approving with the provider-owned keystroke",
            approve_input=approve_input,
        )
    segments = [part for part in Path(requested).parts if part not in ("/",)]
    if ".." in segments:
        return PermissionDecision(
            provider,
            parsed.operation,
            requested,
            normalized,
            policy,
            "deny",
            "path traversal outside the project temp root and allowlist; "
            "automatic approval is refused",
        )
    if requested.startswith("~"):
        return PermissionDecision(
            provider,
            parsed.operation,
            requested,
            normalized,
            policy,
            "deny",
            "home-directory path outside the project temp root and "
            "allowlist; automatic approval is refused",
        )
    base = project_dir.resolve()
    if _redirected_outside(base, requested, resolved):
        return PermissionDecision(
            provider,
            parsed.operation,
            requested,
            normalized,
            policy,
            "deny",
            "symlink escape outside the project temp root and allowlist; "
            "automatic approval is refused",
        )
    return PermissionDecision(
        provider,
        parsed.operation,
        requested,
        normalized,
        policy,
        "waiting",
        "path is outside the private project temp root and allowlist "
        "(shared `/tmp` is never auto-approved); answer the approval in "
        "the provider session",
    )


def decision_summary(decision: PermissionDecision) -> str:
    """One bounded operator-readable line for activity and diagnostics."""
    path = decision.normalized_path or decision.requested_path or "(unknown path)"
    operation = decision.operation or "(unknown operation)"
    reason = decision.reason[:MAX_REASON_CHARS]
    return (
        f"permission {decision.result}: policy={decision.policy} "
        f"operation={operation} path={path[:MAX_PATH_CHARS]}; {reason}"
    )
