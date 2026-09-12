"""Repository identity and release-readiness tests (stdlib only).

Published metadata, changelog/security links, and the vulnerability route
must identify Ariadex-owned resources. Foreign OpenCode URLs and
placeholder contacts fail release readiness without publishing anything.
"""

import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

import ariadex
from ariadex.release import (
    CANONICAL_ISSUES_URL,
    CANONICAL_REPO_URL,
    check_artifact_metadata,
    check_artifacts,
    check_canonical_remote,
    check_metadata_urls,
    check_published_version,
    check_security_route,
    check_version_not_published,
    check_version_tag,
    dry_run,
    main,
    parse_reported_version,
    published_versions,
    read_metadata_version,
    resolve_origin_remote,
    version_from_tag,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

FOREIGN_PYPROJECT = """\
[project]
name = "ariadex"
[project.urls]
Homepage = "https://github.com/anomalyco/opencode"
Security = "https://github.com/anomalyco/opencode/blob/main/SECURITY.md"
Changelog = "https://github.com/anomalyco/opencode/blob/main/CHANGELOG.md"
"""

PLACEHOLDER_PYPROJECT = """\
[project]
name = "ariadex"
[project.urls]
Homepage = "https://example.com/<repo>"
Security = "https://example.com/<repo>/SECURITY.md"
Changelog = "https://example.com/<repo>/CHANGELOG.md"
"""


def canonical_pyproject() -> str:
    return f"""\
[project]
name = "ariadex"
[project.urls]
Homepage = "{CANONICAL_REPO_URL}"
Security = "{CANONICAL_REPO_URL}/blob/main/SECURITY.md"
Changelog = "{CANONICAL_REPO_URL}/blob/main/CHANGELOG.md"
"""


class MetadataIdentityTests(unittest.TestCase):
    def test_real_pyproject_identifies_ariadex(self):
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        result = check_metadata_urls(text)
        self.assertTrue(result.ok, result.detail)

    def test_foreign_opencode_urls_rejected(self):
        result = check_metadata_urls(FOREIGN_PYPROJECT)
        self.assertFalse(result.ok)
        self.assertIn("anomalyco/opencode", result.detail)

    def test_placeholder_urls_rejected(self):
        result = check_metadata_urls(PLACEHOLDER_PYPROJECT)
        self.assertFalse(result.ok)
        self.assertIn("placeholder", result.detail)

    def test_missing_url_key_rejected(self):
        result = check_metadata_urls('[project]\nname = "ariadex"\n')
        self.assertFalse(result.ok)
        self.assertIn("missing", result.detail)

    def test_invalid_toml_rejected(self):
        result = check_metadata_urls("[project\nbroken = = =")
        self.assertFalse(result.ok)


class SecurityRouteTests(unittest.TestCase):
    def test_real_security_md_routes_to_canonical_tracker(self):
        text = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
        result = check_security_route(text)
        self.assertTrue(result.ok, result.detail)

    def test_foreign_tracker_rejected(self):
        text = "Report at <https://github.com/anomalyco/opencode/issues> with details."
        result = check_security_route(text)
        self.assertFalse(result.ok)

    def test_placeholder_contact_rejected(self):
        text = f"Report at <https://example.com/<tracker>> or {CANONICAL_ISSUES_URL}."
        result = check_security_route(text)
        self.assertFalse(result.ok)

    def test_missing_route_rejected(self):
        result = check_security_route("No reporting instructions here.")
        self.assertFalse(result.ok)
        self.assertIn(CANONICAL_ISSUES_URL, result.detail)


class CanonicalRemoteTests(unittest.TestCase):
    def test_canonical_https_passes(self):
        result = check_canonical_remote(CANONICAL_REPO_URL)
        self.assertTrue(result.ok, result.detail)

    def test_canonical_git_suffix_and_slash_pass(self):
        for url in (
            CANONICAL_REPO_URL + ".git",
            CANONICAL_REPO_URL + "/",
            CANONICAL_REPO_URL + ".git/",
        ):
            with self.subTest(url=url):
                result = check_canonical_remote(url)
                self.assertTrue(result.ok, result.detail)

    def test_canonical_ssh_forms_pass(self):
        for url in (
            "git@github.com:lileililiwen/ariadex.git",
            "git@github.com:lileililiwen/ariadex",
            "ssh://git@github.com/lileililiwen/ariadex.git",
        ):
            with self.subTest(url=url):
                result = check_canonical_remote(url)
                self.assertTrue(result.ok, result.detail)

    def test_missing_remote_fails_with_add_command(self):
        for url in ("", "   "):
            with self.subTest(url=repr(url)):
                result = check_canonical_remote(url)
                self.assertFalse(result.ok)
                self.assertIn("git remote add origin", result.detail)
                self.assertIn(CANONICAL_REPO_URL, result.detail)

    def test_foreign_remote_rejected(self):
        result = check_canonical_remote("https://github.com/anomalyco/opencode.git")
        self.assertFalse(result.ok)
        self.assertIn("anomalyco/opencode", result.detail)

    def test_placeholder_remote_rejected(self):
        result = check_canonical_remote("https://example.com/<repo>.git")
        self.assertFalse(result.ok)
        self.assertIn("placeholder", result.detail)

    def test_non_canonical_remote_rejected(self):
        result = check_canonical_remote("https://github.com/someone-else/ariadex.git")
        self.assertFalse(result.ok)
        self.assertIn(CANONICAL_REPO_URL, result.detail)

    def test_resolve_origin_returns_empty_without_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(resolve_origin_remote(Path(tmp)), "")


class VersionTagTests(unittest.TestCase):
    def test_matching_tag_passes(self):
        result = check_version_tag(
            ariadex.__version__, f"ariadex-v{ariadex.__version__}"
        )
        self.assertTrue(result.ok, result.detail)

    def test_mismatched_tag_fails(self):
        result = check_version_tag("0.1.0", "ariadex-v9.9.9")
        self.assertFalse(result.ok)
        self.assertIn("does not match", result.detail)

    def test_missing_tag_fails_with_rerun(self):
        result = check_version_tag("0.1.0", "")
        self.assertFalse(result.ok)
        self.assertIn("--tag ariadex-v0.1.0", result.detail)


class ArtifactTests(unittest.TestCase):
    def test_matching_artifacts_pass_with_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "ariadex-0.1.0.tar.gz").write_bytes(b"sdist-bytes")
            (dist / "ariadex-0.1.0-py3-none-any.whl").write_bytes(b"wheel-bytes")
            result = check_artifacts(dist, "0.1.0")
        self.assertTrue(result.ok, result.detail)
        self.assertIn("sha256:", result.detail)

    def test_missing_artifact_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = check_artifacts(Path(tmp), "0.1.0")
        self.assertFalse(result.ok)
        self.assertIn("python -m build", result.detail)


def write_wheel(dist: Path, version: str, metadata_version: str | None = None) -> None:
    """Minimal wheel named for `version` carrying `metadata_version`."""
    dist.mkdir(parents=True, exist_ok=True)
    wheel = dist / f"ariadex-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"ariadex-{version}.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: ariadex\n"
            f"Version: {metadata_version or version}\n",
        )


def write_sdist(dist: Path, version: str, metadata_version: str | None = None) -> None:
    """Minimal sdist named for `version` carrying `metadata_version`."""
    dist.mkdir(parents=True, exist_ok=True)
    sdist = dist / f"ariadex-{version}.tar.gz"
    pkg_info = (
        "Metadata-Version: 2.1\nName: ariadex\n"
        f"Version: {metadata_version or version}\n"
    ).encode()
    with tarfile.open(sdist, "w:gz") as archive:
        info = tarfile.TarInfo(f"ariadex-{version}/PKG-INFO")
        info.size = len(pkg_info)
        archive.addfile(info, io.BytesIO(pkg_info))


def write_minimal_artifacts(dist: Path, version: str) -> None:
    """Minimal wheel/sdist carrying `version` in embedded metadata."""
    write_wheel(dist, version)
    write_sdist(dist, version)


class ArtifactMetadataTests(unittest.TestCase):
    def test_matching_embedded_versions_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            write_minimal_artifacts(dist, "0.1.0")
            self.assertEqual(
                read_metadata_version(dist / "ariadex-0.1.0.tar.gz"), "0.1.0"
            )
            self.assertEqual(
                read_metadata_version(dist / "ariadex-0.1.0-py3-none-any.whl"),
                "0.1.0",
            )
            result = check_artifact_metadata(dist, "0.1.0")
        self.assertTrue(result.ok, result.detail)

    def test_wheel_metadata_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            write_sdist(dist, "0.1.0")
            write_wheel(dist, "0.1.0", metadata_version="9.9.9")
            result = check_artifact_metadata(dist, "0.1.0")
        self.assertFalse(result.ok)
        self.assertIn("9.9.9", result.detail)
        self.assertIn("differs from", result.detail)
        self.assertIn("rebuild", result.detail)

    def test_sdist_metadata_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            write_wheel(dist, "0.1.0")
            write_sdist(dist, "0.1.0", metadata_version="9.9.9")
            result = check_artifact_metadata(dist, "0.1.0")
        self.assertFalse(result.ok)
        self.assertIn("9.9.9", result.detail)

    def test_missing_embedded_metadata_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "ariadex-0.1.0.tar.gz").write_bytes(b"sdist-bytes")
            (dist / "ariadex-0.1.0-py3-none-any.whl").write_bytes(b"wheel-bytes")
            result = check_artifact_metadata(dist, "0.1.0")
        self.assertFalse(result.ok)
        self.assertIn("no readable version metadata", result.detail)

    def test_missing_files_fail_with_build_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = check_artifact_metadata(Path(tmp), "0.1.0")
        self.assertFalse(result.ok)
        self.assertIn("python -m build", result.detail)


class VersionUnusedTests(unittest.TestCase):
    UNUSED = '{"releases": {"0.0.1": [], "0.0.9": []}}'
    USED = '{"releases": {"0.1.0": [], "0.0.9": []}}'

    def test_unused_version_passes(self):
        result = check_version_not_published("0.1.0", self.UNUSED)
        self.assertTrue(result.ok, result.detail)

    def test_duplicate_version_fails_with_bump_guidance(self):
        result = check_version_not_published("0.1.0", self.USED)
        self.assertFalse(result.ok)
        self.assertIn("already published", result.detail)
        self.assertIn("bump", result.detail)
        self.assertIn("never overwrite", result.detail)

    def test_network_failure_fails_closed(self):
        def failing() -> str:
            raise OSError("no network")

        result = check_version_not_published("0.1.0", fetcher=failing)
        self.assertFalse(result.ok)
        self.assertIn("could not query", result.detail)
        self.assertIn("never be overwritten", result.detail)

    def test_malformed_payload_fails(self):
        for bad in ("not json", '{"info": {}}', "[]"):
            with self.subTest(payload=bad):
                result = check_version_not_published("0.1.0", bad)
                self.assertFalse(result.ok)

    def test_published_versions_parses_release_keys(self):
        self.assertEqual(published_versions(self.USED), {"0.1.0", "0.0.9"})


class PublishedVersionTests(unittest.TestCase):
    def test_exact_match_passes(self):
        self.assertEqual(parse_reported_version("ariadex 0.1.0\n"), "0.1.0")
        result = check_published_version("ariadex 0.1.0", "0.1.0")
        self.assertTrue(result.ok, result.detail)

    def test_post_publish_mismatch_fails_incomplete(self):
        result = check_published_version("ariadex 0.2.0", "0.1.0")
        self.assertFalse(result.ok)
        self.assertIn("incomplete release", result.detail)
        self.assertIn("0.2.0", result.detail)
        self.assertIn("do not overwrite or republish", result.detail)

    def test_unparseable_output_fails(self):
        for bad in ("", "hello", "version 0.1.0"):
            with self.subTest(output=bad):
                result = check_published_version(bad, "0.1.0")
                self.assertFalse(result.ok)

    def test_version_from_tag(self):
        self.assertEqual(version_from_tag("ariadex-v0.2.0"), "0.2.0")
        self.assertIsNone(version_from_tag("v0.2.0"))
        self.assertIsNone(version_from_tag("ariadex-v"))
        self.assertIsNone(version_from_tag(""))

    def test_verify_published_cli_mode(self):
        self.assertEqual(
            main(["--tag", "ariadex-v0.1.0", "--verify-published", "ariadex 0.1.0"]),
            0,
        )
        self.assertEqual(
            main(["--tag", "ariadex-v0.1.0", "--verify-published", "ariadex 0.2.0"]),
            1,
        )
        self.assertEqual(
            main(["--tag", "main", "--verify-published", "ariadex 0.1.0"]),
            1,
        )


class DryRunTests(unittest.TestCase):
    def _write_root(self, root: Path) -> None:
        (root / "pyproject.toml").write_text(canonical_pyproject(), encoding="utf-8")
        (root / "SECURITY.md").write_text(
            f"Open an issue at <{CANONICAL_ISSUES_URL}> with details.\n",
            encoding="utf-8",
        )
        write_minimal_artifacts(root / "dist", ariadex.__version__)

    def test_dry_run_passes_on_ready_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_root(Path(tmp))
            results = dry_run(
                Path(tmp),
                f"ariadex-v{ariadex.__version__}",
                remote_url=CANONICAL_REPO_URL,
            )
            self.assertTrue(all(r.ok for r in results), results)
            self.assertEqual(
                main(
                    [
                        "--root",
                        tmp,
                        "--tag",
                        f"ariadex-v{ariadex.__version__}",
                        "--remote-url",
                        CANONICAL_REPO_URL,
                    ]
                ),
                0,
            )

    def test_dry_run_fails_closed_without_publishing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_root(Path(tmp))
            (Path(tmp) / "SECURITY.md").write_text(
                "Report at <https://github.com/anomalyco/opencode/issues>.\n",
                encoding="utf-8",
            )
            results = dry_run(
                Path(tmp), "ariadex-v9.9.9", remote_url=CANONICAL_REPO_URL
            )
            self.assertFalse(all(r.ok for r in results))
            self.assertEqual(
                main(
                    [
                        "--root",
                        tmp,
                        "--tag",
                        "ariadex-v9.9.9",
                        "--remote-url",
                        CANONICAL_REPO_URL,
                    ]
                ),
                1,
            )

    def test_dry_run_fails_closed_without_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_root(Path(tmp))
            results = dry_run(
                Path(tmp), f"ariadex-v{ariadex.__version__}", remote_url=""
            )
            names = [r.name for r in results]
            self.assertIn("canonical-remote", names)
            remote = next(r for r in results if r.name == "canonical-remote")
            self.assertFalse(remote.ok)
            self.assertIn("git remote add origin", remote.detail)
            self.assertFalse(all(r.ok for r in results))

    def test_dry_run_rejects_duplicate_version_with_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_root(Path(tmp))
            used = f'{{"releases": {{"{ariadex.__version__}": []}}}}'
            results = dry_run(
                Path(tmp),
                f"ariadex-v{ariadex.__version__}",
                remote_url=CANONICAL_REPO_URL,
                pypi_payload=used,
            )
            unused = next(r for r in results if r.name == "version-unused")
            self.assertFalse(unused.ok)
            self.assertIn("already published", unused.detail)
            self.assertFalse(all(r.ok for r in results))

    def test_dry_run_accepts_unused_version_with_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_root(Path(tmp))
            results = dry_run(
                Path(tmp),
                f"ariadex-v{ariadex.__version__}",
                remote_url=CANONICAL_REPO_URL,
                pypi_payload='{"releases": {"0.0.1": []}}',
            )
            self.assertTrue(all(r.ok for r in results), results)


class ReleaseWorkflowTests(unittest.TestCase):
    """The tag-triggered workflow gates and observes publication."""

    def _workflow_text(self) -> str:
        return (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )

    def test_trusted_publisher_with_oidc_and_release_environment(self):
        text = self._workflow_text()
        self.assertIn("pypa/gh-action-pypi-publish", text)
        self.assertIn("id-token: write", text)
        self.assertIn("environment: release", text)

    def test_publication_is_gated_on_evidence_and_readiness(self):
        text = self._workflow_text()
        gate = text.index("evidence --release-gate")
        readiness = text.index("ariadex.release --tag")
        publish = text.index("pypa/gh-action-pypi-publish")
        self.assertLess(
            gate, publish, "live evidence release gate must precede publication"
        )
        self.assertLess(
            readiness, publish, "readiness dry run must precede publication"
        )

    def test_published_install_is_verified_from_the_index(self):
        text = self._workflow_text()
        publish = text.index("pypa/gh-action-pypi-publish")
        tail = text[publish:]
        self.assertIn('pip install "ariadex==', tail)
        self.assertIn("ariadex --version", tail)
        self.assertIn("ariadex init", tail)
        self.assertIn("ariadex status", tail)

    def test_pre_publish_gates_include_metadata_and_unused_version(self):
        text = self._workflow_text()
        publish = text.index("pypa/gh-action-pypi-publish")
        head = text[:publish]
        self.assertIn("--check-pypi", head)
        self.assertIn("ariadex.release --tag", head)

    def test_index_verification_compares_the_exact_tagged_version(self):
        text = self._workflow_text()
        publish = text.index("pypa/gh-action-pypi-publish")
        tail = text[publish:]
        self.assertIn("--verify-published", tail)
        self.assertIn("${GITHUB_REF_NAME}", tail)

    def test_release_summary_names_tag_version_artifacts_and_index(self):
        text = self._workflow_text()
        publish = text.index("pypa/gh-action-pypi-publish")
        tail = text[publish:]
        self.assertIn("GITHUB_STEP_SUMMARY", tail)
        self.assertIn("SHA256SUMS", tail)
        self.assertIn("PyPI verification", tail)


if __name__ == "__main__":
    unittest.main()
