"""Documentation consistency: purposes, queue agreement, links.

Guards the canonical-spec-governance capability: durable documentation must
stay complete and internally consistent without live tmux or provider access.
All checks are pure functions over a repository root, so both the empty
queue and fixture-built active queues are exercised without skips.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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


def changes_dir(root: Path | str) -> Path:
    return Path(root) / "openspec" / "changes"


def specs_dir(root: Path | str) -> Path:
    return Path(root) / "openspec" / "specs"


def active_changes(root: Path | str = ROOT) -> list[str]:
    """Top-level change directories excluding the archive and hidden names."""
    return sorted(
        entry.name
        for entry in changes_dir(root).iterdir()
        if entry.is_dir()
        and entry.name != ARCHIVE_DIRNAME
        and not entry.name.startswith(".")
    )


def purpose_body(spec_path: Path) -> str:
    """Text under `## Purpose` up to the next Markdown heading."""
    text = Path(spec_path).read_text(encoding="utf-8")
    match = re.search(r"^## Purpose\s*\n(?P<body>.*?)(?=^#|\Z)", text, re.S | re.M)
    if match is None:
        raise AssertionError(f"{spec_path}: no `## Purpose` section")
    return match.group("body")


def purpose_problems(body: str) -> list[str]:
    """Placeholder/empty Purpose findings (empty list means complete)."""
    problems = []
    if not body.strip():
        problems.append("empty Purpose")
    for marker in PURPOSE_PLACEHOLDERS:
        if marker in body:
            problems.append(f"placeholder {marker!r}")
    if re.search(r"<[A-Za-z]", body):
        problems.append("angle-bracket placeholder")
    return problems


def _next_change_section(handoff_text: str) -> str:
    return handoff_text.split("## Next change", 1)[1].split("## ", 1)[0]


def next_change_problems(handoff_text: str, active: list[str]) -> list[str]:
    """Next-change queue agreement findings."""
    named = re.findall(r"`([a-z0-9][a-z0-9-]*)`", _next_change_section(handoff_text))
    named = [name for name in named if "-" in name]
    if active:
        problems = [
            f"Next change names absent change {name!r}"
            for name in named
            if name not in active
        ]
        if not named:
            problems.append("active changes exist but Next change names none")
        return problems
    return ["no active changes but Next change names work"] if named else []


def idle_claim_problems(docs: dict[str, str], active: list[str]) -> list[str]:
    """Contradictory idle-claim findings (`doc: claim` strings)."""
    if not active:
        return []
    problems = []
    for doc, body in docs.items():
        current = (
            body.partition(HISTORICAL_BOUNDARY)[0]
            if doc.startswith("HANDOFF")
            else body
        )
        for claim in IDLE_CLAIMS:
            if claim in current:
                problems.append(f"{doc}: contradicts active queue ({claim!r})")
    return problems


def governed_docs(root: Path | str) -> dict[str, str]:
    """Current-state bodies of the governed documents."""
    docs = {}
    for doc in GOVERNED_DOCS:
        docs[doc] = (Path(root) / doc).read_text(encoding="utf-8")
    docs["HANDOFF.md (current)"] = docs.pop("HANDOFF.md").partition(
        HISTORICAL_BOUNDARY
    )[0]
    return docs


class CanonicalPurposeTest(unittest.TestCase):
    def test_every_canonical_purpose_is_complete(self) -> None:
        specs = sorted(specs_dir(ROOT).glob("*/spec.md"))
        self.assertTrue(specs, "no canonical specs found")
        for spec in specs:
            with self.subTest(spec=spec.parent.name):
                problems = purpose_problems(purpose_body(spec))
                self.assertEqual(problems, [], f"{spec}: {problems}")

    def test_fixture_purpose_problems_detected(self) -> None:
        self.assertEqual(purpose_problems("Real purpose, no markers."), [])
        self.assertNotEqual(purpose_problems("TBD - fill in after archive."), [])
        self.assertNotEqual(purpose_problems("   "), [])


class HandoffQueueAgreementTest(unittest.TestCase):
    def test_next_change_agrees_with_real_tree(self) -> None:
        handoff = (ROOT / "HANDOFF.md").read_text(encoding="utf-8")
        self.assertEqual(next_change_problems(handoff, active_changes(ROOT)), [])

    def test_every_active_change_is_tracked_in_handoff(self) -> None:
        handoff = (ROOT / "HANDOFF.md").read_text(encoding="utf-8")
        for name in active_changes(ROOT):
            with self.subTest(change=name):
                self.assertIn(name, handoff, f"active change {name!r} untracked")

    def test_real_tree_has_no_contradictory_idle_claims(self) -> None:
        self.assertEqual(
            idle_claim_problems(governed_docs(ROOT), active_changes(ROOT)), []
        )


class FixtureQueueTest(unittest.TestCase):
    """Both queue states exercised against fixture repositories (no skips)."""

    def _fixture(
        self, tmp: str, active: list[str], handoff_current: str, readme: str = ""
    ) -> Path:
        root = Path(tmp)
        changes = changes_dir(root)
        changes.mkdir(parents=True)
        for name in active:
            (changes / name).mkdir()
        (changes / ARCHIVE_DIRNAME).mkdir()
        (root / "HANDOFF.md").write_text(
            "# Handoff\n\n## Current state\n\n"
            + handoff_current
            + "\n\n## Historical evidence\n\nNo active changes remain.\n"
            "\n## Next change\n\n"
            + (
                f"Select `{active[0]}` next." if active else "No active changes remain."
            ),
            encoding="utf-8",
        )
        (root / "README.md").write_text(
            readme or "No active changes remain.\n", encoding="utf-8"
        )
        (root / "ROADMAP.md").write_text("", encoding="utf-8")
        (root / "AGENTS.md").write_text("", encoding="utf-8")
        return root

    def test_empty_queue_with_idle_claims_is_consistent(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = self._fixture(tmp, [], "Nothing in flight.")
            active = active_changes(root)
            self.assertEqual(active, [])
            handoff = (root / "HANDOFF.md").read_text(encoding="utf-8")
            self.assertEqual(next_change_problems(handoff, active), [])
            self.assertEqual(idle_claim_problems(governed_docs(root), active), [])

    def test_active_fixture_with_idle_claim_fails(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = self._fixture(tmp, ["demo-change"], "No active changes remain.")
            active = active_changes(root)
            self.assertEqual(active, ["demo-change"])
            handoff = (root / "HANDOFF.md").read_text(encoding="utf-8")
            self.assertEqual(next_change_problems(handoff, active), [])
            problems = idle_claim_problems(governed_docs(root), active)
            self.assertTrue(any(p.startswith("HANDOFF") for p in problems), problems)
            self.assertTrue(any(p.startswith("README") for p in problems), problems)

    def test_active_fixture_consistent_docs_pass(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = self._fixture(
                tmp,
                ["demo-change"],
                "Working on `demo-change`.",
                readme="Active: `demo-change`.\n",
            )
            active = active_changes(root)
            handoff = (root / "HANDOFF.md").read_text(encoding="utf-8")
            self.assertEqual(next_change_problems(handoff, active), [])
            self.assertEqual(idle_claim_problems(governed_docs(root), active), [])

    def test_next_change_naming_absent_change_fails(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = self._fixture(tmp, ["demo-change"], "Working.")
            handoff = (root / "HANDOFF.md").read_text(encoding="utf-8")
            handoff = handoff.replace("`demo-change`", "`ghost-change`", 1)
            problems = next_change_problems(handoff, ["demo-change"])
            self.assertEqual(len(problems), 1)
            self.assertIn("ghost-change", problems[0])


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
