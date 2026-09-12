"""Repository identity and release-readiness tests (stdlib only).

Published metadata, changelog/security links, and the vulnerability route
must identify Ariadex-owned resources. Foreign OpenCode URLs and
placeholder contacts fail release readiness without publishing anything.
"""

import tempfile
import unittest
from pathlib import Path

import ariadex
from ariadex.release import (
    CANONICAL_ISSUES_URL,
    CANONICAL_REPO_URL,
    check_artifacts,
    check_canonical_remote,
    check_metadata_urls,
    check_security_route,
    check_version_tag,
    dry_run,
    main,
    resolve_origin_remote,
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


class DryRunTests(unittest.TestCase):
    def _write_root(self, root: Path) -> None:
        (root / "pyproject.toml").write_text(canonical_pyproject(), encoding="utf-8")
        (root / "SECURITY.md").write_text(
            f"Open an issue at <{CANONICAL_ISSUES_URL}> with details.\n",
            encoding="utf-8",
        )
        dist = root / "dist"
        dist.mkdir()
        version = ariadex.__version__
        (dist / f"ariadex-{version}.tar.gz").write_bytes(b"sdist-bytes")
        (dist / f"ariadex-{version}-py3-none-any.whl").write_bytes(b"wheel-bytes")

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


if __name__ == "__main__":
    unittest.main()
