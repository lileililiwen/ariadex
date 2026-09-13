"""Tests for first-run init wizard, refusal, force reset, and start guard."""

import io
import sys
import tempfile
import unittest
from contextlib import chdir, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import yaml

from ariadex import cli, config, state


def run_cli(root: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with chdir(root), redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


def scripted(*answers: str):
    """read_answer stub replaying wizard answers in order."""
    it = iter(answers)
    return lambda prompt: next(it)


class FirstRunWizardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_blank_answers_store_program_defaults(self):
        self.assertEqual(
            cli.cmd_init(self.root, read_answer=scripted("", "", "", "")), 0
        )

        cfg = config.load(self.root)
        self.assertEqual(cfg.agent_provider, "opencode")
        self.assertEqual(cfg.first_prompt, config.DEFAULT_MANAGED_PROMPT)
        self.assertEqual(cfg.continuation_prompt, config.DEFAULT_MANAGED_PROMPT)
        self.assertEqual(cfg.confirmation_prompt, config.DEFAULT_CONFIRMATION_PROMPT)
        self.assertTrue((self.root / "HANDOFF.md").is_file())
        self.assertTrue(cli.is_initialized(self.root))

    def test_skip_words_select_defaults(self):
        self.assertEqual(
            cli.cmd_init(self.root, read_answer=scripted("skip", "-", "SKIP", "skip")),
            0,
        )
        cfg = config.load(self.root)
        self.assertEqual(cfg.agent_provider, "opencode")
        self.assertEqual(cfg.first_prompt, config.DEFAULT_MANAGED_PROMPT)

    def test_custom_answers_round_trip(self):
        code = cli.cmd_init(
            self.root,
            read_answer=scripted(
                "codex",
                "Implement the active spec.",
                "Next, do this.",
                "Finish the rest.",
            ),
        )
        self.assertEqual(code, 0)
        cfg = config.load(self.root)
        self.assertEqual(cfg.agent_provider, "codex")
        self.assertEqual(cfg.first_prompt, "Implement the active spec.")
        self.assertEqual(cfg.continuation_prompt, "Next, do this.")
        self.assertEqual(cfg.confirmation_prompt, "Finish the rest.")

    def test_prompt_with_yaml_special_chars_round_trips(self):
        tricky = "Do: the thing # now [brackets] 'quoted'"
        self.assertEqual(
            cli.cmd_init(self.root, read_answer=scripted("", tricky, "", "")), 0
        )
        cfg = config.load(self.root)
        self.assertEqual(cfg.first_prompt, tricky)

    def test_invalid_provider_reprompts_without_partial_init(self):
        answers = iter(["wat"])
        with redirect_stderr(io.StringIO()), self.assertRaises(StopIteration):
            cli.cmd_init(self.root, read_answer=lambda prompt: next(answers))
        self.assertFalse((self.root / ".ariadex").exists())

    def test_invalid_provider_then_valid_completes(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.cmd_init(
                self.root, read_answer=scripted("wat", "codebuddy", "", "", "")
            )
        self.assertEqual(code, 0)
        self.assertIn("unsupported provider `wat`", err.getvalue())
        self.assertEqual(config.load(self.root).agent_provider, "codebuddy")

    def test_headless_wizard_uses_defaults_without_blocking(self):
        fake_stdin = io.StringIO()
        self.assertFalse(fake_stdin.isatty())
        with mock.patch.object(sys, "stdin", fake_stdin):
            self.assertEqual(cli.cmd_init(self.root), 0)
        self.assertEqual(config.load(self.root).agent_provider, "opencode")

    def test_interactive_input_path_uses_typed_answers(self):
        fake_stdin = io.StringIO()
        fake_stdin.isatty = lambda: True  # type: ignore[method-assign]
        with (
            mock.patch.object(sys, "stdin", fake_stdin),
            mock.patch("builtins.input", side_effect=["codex", "", "", ""]),
        ):
            self.assertEqual(cli.cmd_init(self.root), 0)
        cfg = config.load(self.root)
        self.assertEqual(cfg.agent_provider, "codex")
        self.assertEqual(cfg.continuation_prompt, config.DEFAULT_MANAGED_PROMPT)

    def test_interactive_eof_falls_back_to_defaults(self):
        fake_stdin = io.StringIO()
        fake_stdin.isatty = lambda: True  # type: ignore[method-assign]
        with (
            mock.patch.object(sys, "stdin", fake_stdin),
            mock.patch("builtins.input", side_effect=EOFError),
        ):
            self.assertEqual(cli.cmd_init(self.root), 0)
        self.assertEqual(config.load(self.root).agent_provider, "opencode")

    def test_partial_init_completes_missing_files(self):
        cfg_path = self.root / config.CONFIG_REL_PATH
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text("agent_provider: codex\n", encoding="utf-8")
        handoff = self.root / "HANDOFF.md"
        handoff.write_text("human content\n", encoding="utf-8")
        self.assertFalse(cli.is_initialized(self.root))
        self.assertEqual(
            cli.cmd_init(self.root, read_answer=scripted("", "", "", "")), 0
        )
        text = cfg_path.read_text(encoding="utf-8")
        self.assertIn("agent_provider: codex", text)
        self.assertEqual(handoff.read_text(encoding="utf-8"), "human content\n")
        self.assertTrue(cli.is_initialized(self.root))


class RepeatedInitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.assertEqual(
            cli.cmd_init(self.root, read_answer=scripted("", "", "", "")), 0
        )

    def test_reinit_migrates_missing_prompt_keys(self):
        path = self.root / config.CONFIG_REL_PATH
        text = path.read_text(encoding="utf-8")
        path.write_text(
            "\n".join(
                line
                for line in text.splitlines()
                if not line.startswith(
                    (
                        "first_prompt:",
                        "continuation_prompt:",
                        "confirmation_prompt:",
                    )
                )
            )
            + "\n",
            encoding="utf-8",
        )
        code, _, err = run_cli(self.root, "init")
        self.assertEqual(code, 0)
        self.assertNotIn("init --force", err)
        migrated = path.read_text(encoding="utf-8")
        self.assertIn("first_prompt:", migrated)
        self.assertIn("continuation_prompt:", migrated)
        self.assertIn("confirmation_prompt:", migrated)
        self.assertEqual(
            config.load(self.root).confirmation_prompt,
            config.DEFAULT_CONFIRMATION_PROMPT,
        )

    def test_plain_reinit_refuses_without_changing_state(self):
        before_cfg = (self.root / config.CONFIG_REL_PATH).read_text(encoding="utf-8")
        before_session = state.read(self.root).session_id
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.cmd_init(self.root, read_answer=scripted("codex", "x", "y"))
        self.assertNotEqual(code, 0)
        self.assertIn("init --force", err.getvalue())
        self.assertEqual(
            (self.root / config.CONFIG_REL_PATH).read_text(encoding="utf-8"), before_cfg
        )
        self.assertEqual(state.read(self.root).session_id, before_session)

    def test_reinit_refusal_sends_no_prompts(self):
        calls: list[str] = []
        code = cli.cmd_init(
            self.root, read_answer=lambda prompt: calls.append(prompt) or ""
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(calls, [])

    def test_cli_reinit_names_force(self):
        code, _, err = run_cli(self.root, "init")
        self.assertNotEqual(code, 0)
        self.assertIn("init --force", err)


class ForceResetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.assertEqual(
            cli.cmd_init(
                self.root,
                read_answer=scripted("codex", "first-one", "cont-one", "conf-one"),
            ),
            0,
        )
        # Representative runtime state that a scoped reset must remove.
        (self.root / ".ariadex" / "daemon.json").write_text("{}", encoding="utf-8")
        (self.root / ".ariadex" / "runs").mkdir(exist_ok=True)
        (self.root / ".ariadex" / "runs" / "r.log").write_text("x", encoding="utf-8")
        (self.root / "HANDOFF.md").write_text("human handoff\n", encoding="utf-8")
        (self.root / "openspec" / "changes").mkdir(parents=True, exist_ok=True)
        (self.root / "src").mkdir(exist_ok=True)
        (self.root / "src" / "keep.py").write_text("print(1)\n", encoding="utf-8")

    def test_confirmed_reset_recreates_ariadex_and_preserves_project(self):
        code = cli.cmd_init(
            self.root,
            force=True,
            confirmed=True,
            read_answer=scripted("opencode", "", "", ""),
        )
        self.assertEqual(code, 0)
        cfg = config.load(self.root)
        self.assertEqual(cfg.agent_provider, "opencode")
        self.assertFalse((self.root / ".ariadex" / "daemon.json").exists())
        self.assertFalse((self.root / ".ariadex" / "runs").exists())
        self.assertTrue(cli.is_initialized(self.root))
        self.assertEqual(
            (self.root / "HANDOFF.md").read_text(encoding="utf-8"), "human handoff\n"
        )
        self.assertTrue((self.root / "openspec" / "changes").is_dir())
        self.assertEqual(
            (self.root / "src" / "keep.py").read_text(encoding="utf-8"), "print(1)\n"
        )

    def test_headless_reset_without_yes_declines_and_changes_nothing(self):
        before_cfg = (self.root / config.CONFIG_REL_PATH).read_text(encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.cmd_init(
                self.root,
                force=True,
                confirmed=False,
                read_answer=scripted("opencode", "", "", ""),
            )
        self.assertNotEqual(code, 0)
        self.assertIn("--yes", err.getvalue())
        self.assertTrue((self.root / ".ariadex" / "daemon.json").exists())
        self.assertEqual(
            (self.root / config.CONFIG_REL_PATH).read_text(encoding="utf-8"), before_cfg
        )

    def test_interactive_decline_changes_nothing(self):
        fake_stdin = io.StringIO()
        fake_stdin.isatty = lambda: True  # type: ignore[method-assign]
        with (
            mock.patch.object(sys, "stdin", fake_stdin),
            mock.patch("builtins.input", return_value="n"),
        ):
            code = cli.cmd_init(
                self.root,
                force=True,
                confirmed=False,
                read_answer=scripted("opencode", "", "", ""),
            )
        self.assertNotEqual(code, 0)
        self.assertTrue((self.root / ".ariadex" / "daemon.json").exists())
        self.assertEqual(config.load(self.root).agent_provider, "codex")

    def test_interactive_confirm_resets(self):
        fake_stdin = io.StringIO()
        fake_stdin.isatty = lambda: True  # type: ignore[method-assign]
        with (
            mock.patch.object(sys, "stdin", fake_stdin),
            mock.patch("builtins.input", return_value="yes"),
        ):
            code = cli.cmd_init(
                self.root,
                force=True,
                confirmed=False,
                read_answer=scripted("opencode", "", "", ""),
            )
        self.assertEqual(code, 0)
        self.assertEqual(config.load(self.root).agent_provider, "opencode")

    def test_cli_force_yes_resets(self):
        code, out, _ = run_cli(self.root, "init", "--force", "--yes")
        self.assertEqual(code, 0)
        self.assertIn("created", out)
        self.assertTrue(cli.is_initialized(self.root))

    def test_reset_refuses_non_directory_state(self):
        import shutil

        shutil.rmtree(self.root / ".ariadex")
        (self.root / ".ariadex").write_text("not a dir", encoding="utf-8")
        code = cli.cmd_init(
            self.root,
            force=True,
            confirmed=True,
            read_answer=scripted("", "", "", ""),
        )
        self.assertNotEqual(code, 0)


class StartGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_start_refuses_uninitialized_project(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.cmd_start(self.root)
        self.assertNotEqual(code, 0)
        self.assertIn("ariadex init", err.getvalue())
        self.assertFalse((self.root / ".ariadex").exists())

    def test_cli_start_refuses_uninitialized_project(self):
        code, _, err = run_cli(self.root, "start")
        self.assertNotEqual(code, 0)
        self.assertIn("ariadex init", err)
        self.assertFalse((self.root / ".ariadex").exists())

    def test_start_passes_guard_once_initialized(self):
        self.assertEqual(
            cli.cmd_init(self.root, read_answer=scripted("", "", "", "")), 0
        )
        report = cli.prerequisites_mod.CoordinatorReport(
            results=[
                cli.prerequisites_mod.PrerequisiteResult("runtime", "present", "ok"),
                cli.prerequisites_mod.PrerequisiteResult("provider", "present", "ok"),
                cli.prerequisites_mod.PrerequisiteResult("tmux", "present", "ok"),
                cli.prerequisites_mod.PrerequisiteResult("widget", "present", "ok"),
            ],
            ready=True,
        )
        with (
            mock.patch.object(cli.prerequisites_mod, "coordinate", return_value=report),
            mock.patch("ariadex.cli.daemon_mod.read_record", return_value=None),
            mock.patch(
                "ariadex.cli.concurrency_mod.diagnose",
                return_value={"state": "active", "owner": {"pid": 1, "hostname": "h"}},
            ),
        ):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = cli.cmd_start(self.root)
        # Refused for the live-lease reason, not the init reason: the guard passed.
        self.assertNotEqual(code, 0)
        self.assertIn("live lease", err.getvalue())
        self.assertNotIn("ariadex init", err.getvalue())


class InitConfigValidationTest(unittest.TestCase):
    def test_defaults_carry_managed_prompts(self):
        cfg = config.defaults()
        self.assertEqual(cfg.first_prompt, config.DEFAULT_MANAGED_PROMPT)
        self.assertEqual(cfg.continuation_prompt, config.DEFAULT_MANAGED_PROMPT)
        self.assertEqual(cfg.confirmation_prompt, config.DEFAULT_CONFIRMATION_PROMPT)
        self.assertNotEqual(cfg.first_prompt.strip(), "")
        self.assertNotEqual(cfg.confirmation_prompt.strip(), "")
        self.assertNotEqual(cfg.confirmation_prompt, cfg.continuation_prompt)

    def test_missing_prompt_keys_receive_defaults(self):
        cfg = config.validate({"agent_provider": "codex"}, source="test")
        self.assertEqual(cfg.first_prompt, config.DEFAULT_MANAGED_PROMPT)
        self.assertEqual(cfg.continuation_prompt, config.DEFAULT_MANAGED_PROMPT)
        self.assertEqual(cfg.confirmation_prompt, config.DEFAULT_CONFIRMATION_PROMPT)

    def test_blank_prompts_rejected(self):
        for key in ("first_prompt", "continuation_prompt", "confirmation_prompt"):
            with self.assertRaises(config.ConfigError, msg=key):
                config.validate({key: "  "}, source="test")

    def test_non_string_prompts_rejected(self):
        with self.assertRaises(config.ConfigError):
            config.validate({"first_prompt": ["x"]}, source="test")
        with self.assertRaises(config.ConfigError):
            config.validate({"confirmation_prompt": {"x": 1}}, source="test")

    def test_default_config_text_loads_with_prompts(self):
        cfg = config.validate(
            yaml.safe_load(config.default_config_text()), source="test"
        )
        self.assertEqual(cfg.first_prompt, config.DEFAULT_MANAGED_PROMPT)
        self.assertEqual(cfg.continuation_prompt, config.DEFAULT_MANAGED_PROMPT)
        self.assertEqual(cfg.confirmation_prompt, config.DEFAULT_CONFIRMATION_PROMPT)


if __name__ == "__main__":
    unittest.main()
