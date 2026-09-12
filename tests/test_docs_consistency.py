"""Documentation consistency: purposes, queue agreement, links.

Guards the canonical-spec-governance capability: durable documentation must
stay complete and internally consistent without live tmux or provider access.
Repository-identity URLs (pyproject.toml, SECURITY.md pointing at the OpenCode
repository) are explicitly out of scope here: no canonical Ariadex remote is
configured, so those corrections belong to
`repository-identity-security-and-release-readiness`, whose first task is
choosing the canonical URL.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS_DIR = ROOT / "openspec" / "specs"
CHANGES_DIR = ROOT / "openspec" / "changes"
ARCHIVE_DIRNAME = "archive"

PURPOSE_PLACEHOLDERS = (
    "TBD",
    "TODO",
    "FIXME",
    "XXX",
    "Update Purpose after archive",
)
IDLE_CLAIMS = (
    "No active changes remain",
    "openspec list` is empty",
)
GOVERNED_DOCS = ("README.md", "ROADMAP.md", "HANDOFF.md", "AGENTS.md")
HISTORICAL_BOUNDARY = "## Historical evidence"


def active_changes() -> list[str]:
    """Top-level change directories excluding the archive and hidden names."""
    return sorted(
        entry.name
        for entry in CHANGES_DIR.iterdir()
        if entry.is_dir()
        and entry.name != ARCHIVE_DIRNAME
        and not entry.name.startswith(".")
    )


def purpose_body(spec_path: Path) -> str:
    """Text under `## Purpose` up to the next Markdown heading."""
    text = spec_path.read_text(encoding="utf-8")
    match = re.search(r"^## Purpose\s*\n(?P<body>.*?)(?=^#|\Z)", text, re.S | re.M)
    if match is None:
        raise AssertionError(f"{spec_path}: no `## Purpose` section")
    return match.group("body")


class CanonicalPurposeTest(unittest.TestCase):
    def test_every_canonical_purpose_is_complete(self) -> None:
        specs = sorted(SPECS_DIR.glob("*/spec.md"))
        self.assertTrue(specs, "no canonical specs found")
        for spec in specs:
            with self.subTest(spec=spec.parent.name):
                body = purpose_body(spec).strip()
                self.assertTrue(body, f"{spec}: empty Purpose")
                for marker in PURPOSE_PLACEHOLDERS:
                    self.assertNotIn(marker, body, f"{spec}: placeholder {marker!r}")
                self.assertNotRegex(body, r"<[A-Za-z]")


class HandoffQueueAgreementTest(unittest.TestCase):
    def test_next_change_names_an_existing_active_change(self) -> None:
        active = active_changes()
        handoff = (ROOT / "HANDOFF.md").read_text(encoding="utf-8")
        section = handoff.split("## Next change", 1)[1].split("## ", 1)[0]
        named = re.findall(r"`([a-z0-9][a-z0-9-]*)`", section)
        named = [name for name in named if "-" in name]
        if active:
            self.assertTrue(named, "active changes exist but Next change names none")
            for name in named:
                self.assertIn(name, active, f"Next change names absent change {name!r}")
        else:
            self.assertFalse(named, "no active changes but Next change names work")

    def test_every_active_change_is_tracked_in_handoff(self) -> None:
        handoff = (ROOT / "HANDOFF.md").read_text(encoding="utf-8")
        for name in active_changes():
            with self.subTest(change=name):
                self.assertIn(name, handoff, f"active change {name!r} untracked")

    def test_no_contradictory_idle_claims(self) -> None:
        handoff = (ROOT / "HANDOFF.md").read_text(encoding="utf-8")
        current, _, _ = handoff.partition(HISTORICAL_BOUNDARY)
        bodies = {"HANDOFF.md (current)": current}
        for doc in ("README.md", "ROADMAP.md", "AGENTS.md"):
            bodies[doc] = (ROOT / doc).read_text(encoding="utf-8")
        if not active_changes():
            self.skipTest("no active changes; idle claims are consistent")
        for doc, body in bodies.items():
            with self.subTest(doc=doc):
                for claim in IDLE_CLAIMS:
                    self.assertNotIn(claim, body, f"{doc}: contradicts active queue")


class DocLinkTest(unittest.TestCase):
    LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)\s]*)?\)")

    def test_relative_markdown_links_resolve(self) -> None:
        for doc in GOVERNED_DOCS:
            path = ROOT / doc
            with self.subTest(doc=doc):
                for target in self.LINK_RE.findall(path.read_text(encoding="utf-8")):
                    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                        continue  # external URL: no network in this check
                    resolved = (path.parent / target).resolve()
                    self.assertTrue(
                        resolved.is_file(),
                        f"{doc}: link target {target!r} does not exist",
                    )


if __name__ == "__main__":
    unittest.main()
