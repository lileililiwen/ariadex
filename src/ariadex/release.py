"""Release-readiness dry run: fail-closed checks, no publishing.

Verifies that published metadata identifies Ariadex-owned resources, the
canonical `origin` remote is configured, the release tag matches the
single-source package version, build artifacts exist with recorded hashes,
and the security-reporting route resolves to the canonical tracker. Never
uploads anything; PyPI publication happens only in the tag-triggered
release workflow via scoped trusted publishing after every gate passes.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import re
import subprocess
import tomllib
from pathlib import Path

CANONICAL_REPO_URL = "https://github.com/lileililiwen/ariadex"
CANONICAL_ISSUES_URL = CANONICAL_REPO_URL + "/issues"
CANONICAL_SSH_PREFIXES = (
    "git@github.com:lileililiwen/ariadex",
    "ssh://git@github.com/lileililiwen/ariadex",
)
FOREIGN_MARKERS = ("anomalyco/opencode", "github.com/anomalyco")
REQUIRED_URL_KEYS = ("Homepage", "Security", "Changelog")


@dataclasses.dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _foreign_or_placeholder(value: str) -> str | None:
    """Return the reason a URL value is unacceptable, or None when clean."""
    for marker in FOREIGN_MARKERS:
        if marker in value:
            return f"foreign-project reference `{marker}`"
    if "<" in value or ">" in value:
        return "placeholder brackets `<...>`"
    return None


def check_metadata_urls(pyproject_text: str) -> CheckResult:
    """`[project.urls]` must name Ariadex-owned resources only."""
    try:
        data = tomllib.loads(pyproject_text)
    except tomllib.TOMLDecodeError as exc:
        return CheckResult("metadata-urls", False, f"pyproject.toml is invalid: {exc}")
    urls = data.get("project", {}).get("urls", {})
    missing = [key for key in REQUIRED_URL_KEYS if key not in urls]
    if missing:
        return CheckResult(
            "metadata-urls", False, f"missing [project.urls] keys: {missing}"
        )
    problems = []
    for key in REQUIRED_URL_KEYS:
        value = urls[key]
        if not isinstance(value, str):
            problems.append(f"{key} is not a URL string")
            continue
        reason = _foreign_or_placeholder(value)
        if reason is not None:
            problems.append(f"{key}: {reason}")
        if not value.startswith(CANONICAL_REPO_URL):
            problems.append(f"{key} does not start with {CANONICAL_REPO_URL}")
    if problems:
        return CheckResult("metadata-urls", False, "; ".join(problems))
    return CheckResult(
        "metadata-urls",
        True,
        f"Homepage/Security/Changelog identify {CANONICAL_REPO_URL}",
    )


def check_security_route(security_text: str) -> CheckResult:
    """Vulnerability reporting must route to the canonical tracker."""
    if CANONICAL_ISSUES_URL not in security_text:
        return CheckResult(
            "security-route",
            False,
            f"SECURITY.md names no {CANONICAL_ISSUES_URL} reporting route",
        )
    angled = re.findall(r"<(https?://[^>\s]+)>", security_text)
    problems = []
    for url in angled:
        if not url.startswith(CANONICAL_REPO_URL):
            problems.append(f"non-canonical URL `<{url}>`")
            continue
        reason = _foreign_or_placeholder(url)
        if reason is not None:
            problems.append(f"`<{url}>`: {reason}")
    for marker in FOREIGN_MARKERS:
        if marker in security_text:
            problems.append(f"foreign-project reference `{marker}`")
    if problems:
        return CheckResult("security-route", False, "; ".join(sorted(set(problems))))
    return CheckResult(
        "security-route", True, f"reports route to {CANONICAL_ISSUES_URL}"
    )


def check_version_tag(version: str, tag: str) -> CheckResult:
    """Release tag must equal `ariadex-v<package version>`."""
    expected = f"ariadex-v{version}"
    if not tag:
        return CheckResult(
            "version-tag",
            False,
            f"no tag supplied; rerun with `--tag {expected}`",
        )
    if tag != expected:
        return CheckResult(
            "version-tag", False, f"tag `{tag}` does not match package `{expected}`"
        )
    return CheckResult("version-tag", True, f"tag `{tag}` matches package version")


def check_artifacts(dist_dir: Path | str, version: str) -> CheckResult:
    """sdist and wheel for `version` must exist; record their hashes."""
    dist = Path(dist_dir)
    names = (
        f"ariadex-{version}.tar.gz",
        f"ariadex-{version}-py3-none-any.whl",
    )
    missing = [name for name in names if not (dist / name).is_file()]
    if missing:
        return CheckResult(
            "artifacts", False, f"missing in {dist}: {missing}; run `python -m build`"
        )
    hashes = []
    for name in names:
        digest = hashlib.sha256((dist / name).read_bytes()).hexdigest()
        hashes.append(f"{name} sha256:{digest[:16]}...")
    return CheckResult("artifacts", True, "; ".join(hashes))


def normalize_remote_url(remote_url: str) -> str:
    """Normalize a git remote URL for canonical comparison.

    Accepts the canonical HTTPS URL with an optional `.git` suffix or
    trailing slash, and the equivalent GitHub SSH forms. Anything else is
    returned stripped but unmapped so the caller reports it as foreign.
    """
    cleaned = remote_url.strip().removesuffix("/").removesuffix(".git").strip()
    if cleaned in CANONICAL_SSH_PREFIXES:
        return CANONICAL_REPO_URL
    return cleaned


def check_canonical_remote(remote_url: str) -> CheckResult:
    """The `origin` remote must identify the canonical repository.

    A missing or non-canonical remote records the absent external
    prerequisite and fails closed: CI and publication success must never
    be claimed without it.
    """
    if not remote_url.strip():
        return CheckResult(
            "canonical-remote",
            False,
            "no `origin` remote configured; run "
            f"`git remote add origin {CANONICAL_REPO_URL}.git`",
        )
    for marker in FOREIGN_MARKERS:
        if marker in remote_url:
            return CheckResult(
                "canonical-remote",
                False,
                f"foreign-project reference `{marker}` "
                f"in remote `{remote_url.strip()}`",
            )
    if "<" in remote_url or ">" in remote_url:
        return CheckResult(
            "canonical-remote",
            False,
            f"placeholder brackets `<...>` in remote `{remote_url.strip()}`",
        )
    if normalize_remote_url(remote_url) != CANONICAL_REPO_URL:
        return CheckResult(
            "canonical-remote",
            False,
            f"remote `{remote_url.strip()}` does not identify {CANONICAL_REPO_URL}",
        )
    return CheckResult(
        "canonical-remote", True, f"origin identifies {CANONICAL_REPO_URL}"
    )


def resolve_origin_remote(workdir: Path | str) -> str:
    """Best-effort `git remote get-url origin`; `""` when unavailable."""
    try:
        proc = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def dry_run(
    root: Path | str,
    tag: str,
    dist: str = "dist",
    remote_url: str | None = None,
) -> list[CheckResult]:
    """Run every readiness check against a project root (no publishing).

    `remote_url=None` resolves `origin` via git in `root`; pass an explicit
    URL (or `""`) to check a value without touching git.
    """
    from . import __version__

    base = Path(root)
    try:
        pyproject_text = (base / "pyproject.toml").read_text(encoding="utf-8")
    except OSError as exc:
        pyproject_text = ""
        read_error = f"cannot read pyproject.toml: {exc}"
    else:
        read_error = ""
    try:
        security_text = (base / "SECURITY.md").read_text(encoding="utf-8")
    except OSError as exc:
        security_text = ""
        security_error = f"cannot read SECURITY.md: {exc}"
    else:
        security_error = ""
    results = []
    if read_error:
        results.append(CheckResult("metadata-urls", False, read_error))
    else:
        results.append(check_metadata_urls(pyproject_text))
    if security_error:
        results.append(CheckResult("security-route", False, security_error))
    else:
        results.append(check_security_route(security_text))
    results.append(check_version_tag(__version__, tag))
    results.append(check_artifacts(base / dist, __version__))
    if remote_url is None:
        remote_url = resolve_origin_remote(base)
    results.append(check_canonical_remote(remote_url))
    return results


def format_report(results: list[CheckResult]) -> str:
    lines = []
    for res in results:
        state = "ok" if res.ok else "FAIL"
        lines.append(f"{res.name}: {state} — {res.detail}")
    failed = sum(1 for r in results if not r.ok)
    lines.append(
        f"summary: {len(results) - failed} passed, {failed} failed "
        "(nothing was published)"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point: `python -m ariadex.release --tag ariadex-vX.Y.Z`."""
    parser = argparse.ArgumentParser(prog="ariadex release")
    parser.add_argument("--tag", default="", help="release tag, e.g. ariadex-v0.1.0")
    parser.add_argument("--root", default=".", help="project root to check")
    parser.add_argument("--dist", default="dist", help="artifact directory")
    parser.add_argument(
        "--remote-url",
        default=None,
        help="explicit `origin` URL to check (default: resolve via git)",
    )
    args = parser.parse_args(argv)
    results = dry_run(args.root, args.tag, args.dist, args.remote_url)
    print(format_report(results))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
