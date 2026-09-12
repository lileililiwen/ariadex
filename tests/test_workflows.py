"""CI/release workflow structure and action-pinning checks (no network).

Validates workflow YAML structure and requires third-party actions to be
SHA-pinned or covered by a reviewed exception with a justification. New
mutable references fail the gate until they are pinned or explicitly
approved here.
"""

import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

SHA_PIN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")

# Mutable action reference -> why it is accepted for now. Keep each entry
# justified and current; unused entries fail so approvals never go stale.
REVIEWED_MUTABLE_REFS = {
    "actions/checkout@v5": (
        "major-version tag of the first-party checkout action; the source "
        "tree already comes from this action. Full SHA pinning deferred "
        "until automated updates are configured."
    ),
    "actions/setup-python@v6": (
        "major-version tag of the first-party Python installer; runs no "
        "project code. Full SHA pinning deferred until automated updates "
        "are configured."
    ),
    "actions/setup-node@v6": (
        "major-version tag of the first-party Node installer; runs no "
        "project code. Full SHA pinning deferred until automated updates "
        "are configured."
    ),
    "actions/upload-artifact@v5": (
        "major-version tag of the first-party artifact uploader; only "
        "uploads already-verified build outputs."
    ),
    "pypa/gh-action-pypi-publish@release/v1": (
        "release-branch tag of the official PyPI publisher; the step runs "
        "only after every gate in the tag-triggered, environment-protected "
        "release job, and only after the trusted publisher is configured "
        "on PyPI (release-publication-and-remote-verification task 2.1)."
    ),
}


def triggers_of(workflow: dict):
    """`on:` parses as boolean True under YAML 1.1; accept either key."""
    return workflow.get("on", workflow.get(True))


def load_workflows() -> dict[str, dict]:
    workflows = {}
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        with path.open(encoding="utf-8") as handle:
            workflows[path.name] = yaml.safe_load(handle)
    assert workflows, "no workflows found"
    return workflows


def action_refs(workflow: dict) -> list[str]:
    refs = []
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []) or []:
            uses = step.get("uses")
            if uses:
                refs.append(uses)
    return refs


class WorkflowStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = load_workflows()

    def test_required_workflows_present(self):
        self.assertIn("ci.yml", self.workflows)
        self.assertIn("release.yml", self.workflows)

    def test_jobs_have_runners_and_steps(self):
        for name, workflow in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertTrue(workflow.get("name"), "workflow has no name")
                self.assertTrue(triggers_of(workflow), "workflow has no triggers")
                jobs = workflow.get("jobs", {})
                self.assertTrue(jobs, "workflow has no jobs")
                for job_name, job in jobs.items():
                    with self.subTest(job=job_name):
                        self.assertTrue(job.get("runs-on"), "job has no runner")
                        steps = job.get("steps", [])
                        self.assertTrue(steps, "job has no steps")
                        for step in steps:
                            self.assertTrue(
                                step.get("run") or step.get("uses"),
                                f"step has neither run nor uses: {step!r}",
                            )

    def test_ci_has_required_gates(self):
        jobs = self.workflows["ci.yml"]["jobs"]
        for required in (
            "unit",
            "openspec",
            "quality",
            "security",
            "live",
            "clean-install",
        ):
            self.assertIn(required, jobs, f"CI gate `{required}` missing")
        quality_runs = " ".join(
            str(step.get("run", "")) for step in jobs["quality"]["steps"]
        )
        for gate in ("ruff check", "ruff format", "mypy", "coverage"):
            self.assertIn(gate, quality_runs, f"quality gate `{gate}` missing")

    def test_release_is_tag_gated_and_protected(self):
        release = self.workflows["release.yml"]
        triggers = triggers_of(release)
        self.assertIn("tags", str(triggers), "release is not tag-triggered")
        jobs = release["jobs"]
        self.assertTrue(
            any(job.get("environment") for job in jobs.values()),
            "no release job has environment protection",
        )

    def test_release_triggers_only_on_version_tags(self):
        release = self.workflows["release.yml"]
        triggers = triggers_of(release)
        push = triggers.get("push", {})
        self.assertEqual(
            push.get("tags"),
            ["ariadex-v*"],
            "release must trigger only on `ariadex-v*` tags",
        )
        self.assertNotIn("branches", push, "branch pushes must never publish")

    def test_ci_never_publishes(self):
        ci = self.workflows["ci.yml"]
        for job in ci.get("jobs", {}).values():
            for step in job.get("steps", []) or []:
                uses = step.get("uses", "")
                run = str(step.get("run", ""))
                self.assertNotIn(
                    "pypa/gh-action-pypi-publish",
                    uses,
                    "CI must never publish to PyPI",
                )
                self.assertNotIn("twine upload", run, "CI must never upload")


class ActionPinningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = load_workflows()

    def test_actions_pinned_or_reviewed(self):
        used_exceptions = set()
        for name, workflow in self.workflows.items():
            for ref in action_refs(workflow):
                with self.subTest(workflow=name, ref=ref):
                    if SHA_PIN.match(ref):
                        continue
                    self.assertIn(
                        ref,
                        REVIEWED_MUTABLE_REFS,
                        f"unreviewed mutable action `{ref}`; pin to a SHA "
                        "or record a reviewed exception",
                    )
                    justification = REVIEWED_MUTABLE_REFS[ref]
                    self.assertTrue(
                        justification.strip(),
                        f"empty justification for `{ref}`",
                    )
                    used_exceptions.add(ref)
        stale = set(REVIEWED_MUTABLE_REFS) - used_exceptions
        self.assertEqual(stale, set(), f"stale approvals for pinned refs: {stale}")


if __name__ == "__main__":
    unittest.main()
