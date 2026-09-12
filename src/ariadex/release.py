"""Release-readiness dry run: fail-closed checks, no publishing.

Version invariants (tag, package, artifacts, PyPI must all agree):

- The single source of truth is `ariadex.__version__`.
- A release tag MUST be exactly `ariadex-v<package version>`.
- Built artifacts MUST carry the same version in their file names and in
  their embedded metadata (wheel `METADATA`, sdist `PKG-INFO`).
- The PyPI index MUST serve exactly the tagged version after publication;
  a different resolved version means the release is incomplete.
- Versions are immutable: an already-published version MUST NOT be
  overwritten. Remediation is a new version plus a new tag, never a
  republish under the same version.

Verifies that published metadata identifies Ariadex-owned resources, the
canonical `origin` remote is configured, the release tag matches the
single-source package version, build artifacts exist with recorded hashes
and matching embedded metadata, and the security-reporting route resolves
to the canonical tracker. Never uploads anything; PyPI publication happens
only in the tag-triggered release workflow via scoped trusted publishing
after every gate passes.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import subprocess
import tomllib
import urllib.request
from pathlib import Path

CANONICAL_REPO_URL = "https://github.com/lileililiwen/ariadex"
CANONICAL_ISSUES_URL = CANONICAL_REPO_URL + "/issues"
CANONICAL_SSH_PREFIXES = (
    "git@github.com:lileililiwen/ariadex",
    "ssh://git@github.com/lileililiwen/ariadex",
)
FOREIGN_MARKERS = ("anomalyco/opencode", "github.com/anomalyco")
REQUIRED_URL_KEYS = ("Homepage", "Security", "Changelog")

#: Canonical release tag prefix: a release tag is `ariadex-v<version>`.
TAG_PREFIX = "ariadex-v"

#: PyPI JSON endpoint listing published versions (network access required).
PYPI_JSON_URL = "https://pypi.org/pypi/ariadex/json"


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


def version_from_tag(tag: str) -> str | None:
    """Version named by a canonical tag, or None for a non-release tag."""
    if tag.startswith(TAG_PREFIX) and len(tag) > len(TAG_PREFIX):
        return tag[len(TAG_PREFIX) :]
    return None


def check_version_tag(version: str, tag: str) -> CheckResult:
    """Release tag must equal `ariadex-v<package version>`."""
    expected = f"{TAG_PREFIX}{version}"
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


def artifact_filenames(version: str) -> tuple[str, str]:
    """Expected sdist and wheel file names for `version`."""
    return (
        f"ariadex-{version}.tar.gz",
        f"ariadex-{version}-py3-none-any.whl",
    )


def read_metadata_version(path: Path) -> str | None:
    """Version from embedded build metadata, or None when unreadable.

    Wheels carry it in `<dist-info>/METADATA`; sdists in `<pkg>/PKG-INFO`.
    A mismatch between this value and the package version means the
    artifacts were built from a different tree than the tagged commit.
    """
    import tarfile
    import zipfile

    try:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                candidates = [
                    name
                    for name in archive.namelist()
                    if name.endswith(".dist-info/METADATA")
                ]
                if not candidates:
                    return None
                text = archive.read(sorted(candidates)[0]).decode(
                    "utf-8", errors="replace"
                )
        else:
            with tarfile.open(path, "r:gz") as archive:
                candidates = [
                    name for name in archive.getnames() if name.endswith("/PKG-INFO")
                ]
                if not candidates:
                    return None
                extracted = archive.extractfile(sorted(candidates)[0])
                if extracted is None:
                    return None
                text = extracted.read().decode("utf-8", errors="replace")
    except (OSError, ValueError, EOFError, tarfile.TarError, zipfile.BadZipFile):
        return None
    match = re.search(r"(?m)^Version:\s*(\S+)\s*$", text)
    return match.group(1) if match else None


def check_artifact_metadata(dist_dir: Path | str, version: str) -> CheckResult:
    """Embedded artifact metadata must name the release `version`.

    File names alone cannot prove the build matches the tagged commit; the
    wheel `METADATA` and sdist `PKG-INFO` versions must agree too. Runs
    before publication: any mismatch fails the release.
    """
    dist = Path(dist_dir)
    names = artifact_filenames(version)
    missing = [name for name in names if not (dist / name).is_file()]
    if missing:
        return CheckResult(
            "artifact-metadata",
            False,
            f"missing in {dist}: {missing}; run `python -m build`",
        )
    problems = []
    matched = []
    for name in names:
        found = read_metadata_version(dist / name)
        if found is None:
            problems.append(f"`{name}` carries no readable version metadata")
        elif found != version:
            problems.append(
                f"`{name}` metadata version `{found}` differs from `{version}`; "
                "rebuild from the tagged commit"
            )
        else:
            matched.append(f"`{name}`={found}")
    if problems:
        return CheckResult("artifact-metadata", False, "; ".join(problems))
    return CheckResult(
        "artifact-metadata", True, f"embedded versions agree: {'; '.join(matched)}"
    )


def fetch_pypi_payload(timeout_s: int = 30) -> str:
    """Raw PyPI JSON payload for this project (network; raises on failure)."""
    request = urllib.request.Request(
        PYPI_JSON_URL, headers={"Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
        return response.read().decode("utf-8", errors="replace")


def published_versions(payload: str) -> set[str]:
    """Version strings named by a PyPI JSON payload (raises ValueError)."""
    try:
        data = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"PyPI response is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("PyPI response names no `releases` mapping")
    releases = data.get("releases")
    if not isinstance(releases, dict):
        raise ValueError("PyPI response names no `releases` mapping")
    return {str(item) for item in releases}


def check_version_not_published(
    version: str,
    payload: str | None = None,
    fetcher=fetch_pypi_payload,
) -> CheckResult:
    """Release `version` must not already exist on PyPI (immutable versions).

    Pass an explicit `payload` to check without network access. A network
    failure fails closed: an unverified duplicate must never publish.
    Remediation is a new version plus a new tag, never an overwrite.
    """
    if payload is None:
        try:
            payload = fetcher()
        except Exception as exc:
            return CheckResult(
                "version-unused",
                False,
                f"could not query {PYPI_JSON_URL} ({exc}); rerun online; "
                "an already-published version must never be overwritten",
            )
    try:
        used = published_versions(payload)
    except ValueError as exc:
        return CheckResult("version-unused", False, str(exc))
    if version in used:
        return CheckResult(
            "version-unused",
            False,
            f"version `{version}` is already published on PyPI; bump "
            "`__version__`, add a CHANGELOG entry, and tag a new version; "
            "never overwrite or republish under the same version",
        )
    return CheckResult(
        "version-unused", True, f"version `{version}` is not on PyPI yet"
    )


def parse_reported_version(output: str) -> str | None:
    """Version from `ariadex --version` output (`ariadex X.Y.Z`)."""
    match = re.search(r"(?m)^ariadex\s+(\S+)\s*$", output.strip())
    return match.group(1) if match else None


def check_published_version(reported_output: str, version: str) -> CheckResult:
    """The PyPI index must resolve exactly the release `version`.

    A different resolved version means the release is incomplete: report it
    with the exact tag and remediation instead of silently republishing.
    """
    reported = parse_reported_version(reported_output)
    if reported is None:
        return CheckResult(
            "published-version",
            False,
            f"could not parse a version from `{reported_output.strip()[:80]}`; "
            f"expected `ariadex {version}` from the PyPI index",
        )
    if reported != version:
        return CheckResult(
            "published-version",
            False,
            f"incomplete release: PyPI resolved `ariadex {reported}`, expected "
            f"`ariadex {version}`; do not overwrite or republish under the "
            "same version — yank the broken release on PyPI if needed, then "
            "bump `__version__` and tag a new version",
        )
    return CheckResult(
        "published-version",
        True,
        f"PyPI index serves `ariadex {version}` as released",
    )


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
    check_pypi: bool = False,
    pypi_payload: str | None = None,
) -> list[CheckResult]:
    """Run every readiness check against a project root (no publishing).

    `remote_url=None` resolves `origin` via git in `root`; pass an explicit
    URL (or `""`) to check a value without touching git. `check_pypi=True`
    additionally rejects an already-published version via the PyPI index
    (needs network unless `pypi_payload` is supplied); local runs stay
    offline by default while the release workflow always checks.
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
    results.append(check_artifact_metadata(base / dist, __version__))
    if check_pypi or pypi_payload is not None:
        results.append(check_version_not_published(__version__, pypi_payload))
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
    parser.add_argument(
        "--check-pypi",
        action="store_true",
        help="reject an already-published version via the PyPI index",
    )
    parser.add_argument(
        "--verify-published",
        default=None,
        metavar="OUTPUT",
        help="`ariadex --version` output from a fresh PyPI install, "
        "checked against --tag (post-publish verification only)",
    )
    args = parser.parse_args(argv)
    if args.verify_published is not None:
        expected = version_from_tag(args.tag)
        if expected is None:
            result = CheckResult(
                "published-version",
                False,
                f"tag `{args.tag}` is not `{TAG_PREFIX}<version>`; "
                "verify the tagged release instead",
            )
        else:
            result = check_published_version(args.verify_published, expected)
        print(format_report([result]))
        return 0 if result.ok else 1
    results = dry_run(args.root, args.tag, args.dist, args.remote_url, args.check_pypi)
    print(format_report(results))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
