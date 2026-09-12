"""Tests for configuration defaults, loading, and validation."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ariadex import config


def write_config(directory: Path, text: str) -> Path:
    path = directory / config.CONFIG_REL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class DefaultsTest(unittest.TestCase):
    def test_defaults_cover_all_required_settings(self):
        cfg = config.defaults()
        self.assertEqual(cfg.agent_provider, "opencode")
        self.assertEqual(cfg.terminal_driver, "tmux")
        self.assertTrue(cfg.context_strategy)
        self.assertIn(cfg.reset_mode, config.RESET_MODES)
        self.assertTrue(cfg.spec_dir)
        self.assertTrue(cfg.handoff_file)
        self.assertIsInstance(cfg.verification_commands, list)
        self.assertGreaterEqual(cfg.retry_limit, 0)
        self.assertTrue(cfg.blocker_policy)

    def test_default_text_loads_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_config(Path(tmp), config.default_config_text())
            cfg = config.load(Path(tmp))
        self.assertEqual(cfg, config.defaults())


class ValidationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def load_text(self, text: str) -> config.Config:
        write_config(self.root, text)
        return config.load(self.root)

    def test_invalid_reset_mode_rejected(self):
        with self.assertRaises(config.ConfigError) as ctx:
            self.load_text("reset_mode: turbo\n")
        self.assertIn("reset_mode", str(ctx.exception))

    def test_each_supported_reset_mode_accepted(self):
        for mode in ("soft", "hard", "auto"):
            cfg = self.load_text(f"reset_mode: {mode}\n")
            self.assertEqual(cfg.reset_mode, mode)

    def test_negative_retry_limit_rejected(self):
        with self.assertRaises(config.ConfigError) as ctx:
            self.load_text("retry_limit: -1\n")
        self.assertIn("retry_limit", str(ctx.exception))

    def test_non_integer_retry_limit_rejected(self):
        with self.assertRaises(config.ConfigError):
            self.load_text("retry_limit: many\n")

    def test_missing_required_path_rejected(self):
        with self.assertRaises(config.ConfigError):
            self.load_text("spec_dir: ''\n")

    def test_unknown_provider_loads_for_run_to_report(self):
        cfg = self.load_text("agent_provider: wat\n")
        self.assertEqual(cfg.agent_provider, "wat")

    def test_unknown_keys_warn_and_continue(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cfg = self.load_text("future_option: 1\n")
        self.assertIn("future_option", buf.getvalue())
        self.assertEqual(cfg, config.defaults())

    def test_missing_file_reports_init(self):
        with self.assertRaises(config.ConfigError) as ctx:
            config.load(self.root)
        self.assertIn("ariadex init", str(ctx.exception))

    def test_malformed_yaml_rejected(self):
        with self.assertRaises(config.ConfigError):
            self.load_text("agent_provider: [unclosed\n")

    def test_non_mapping_rejected(self):
        with self.assertRaises(config.ConfigError):
            self.load_text("- just\n- a\n- list\n")

    def test_non_string_verification_commands_rejected(self):
        with self.assertRaises(config.ConfigError):
            self.load_text("verification_commands: [ok, 42]\n")

    def test_context_strategy_enum_enforced(self):
        cfg = self.load_text("context_strategy: per-task\n")
        self.assertEqual(cfg.context_strategy, "per-task")
        with self.assertRaises(config.ConfigError):
            self.load_text("context_strategy: vibes\n")

    def test_blocker_policy_enum_enforced(self):
        cfg = self.load_text("blocker_policy: record-and-continue\n")
        self.assertEqual(cfg.blocker_policy, "record-and-continue")
        with self.assertRaises(config.ConfigError):
            self.load_text("blocker_policy: panic\n")

    def test_legacy_values_coerced_with_warning(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cfg = self.load_text(
                "context_strategy: fresh-session\nblocker_policy: record-and-stop\n"
            )
        self.assertEqual(cfg.context_strategy, "per-spec")
        self.assertEqual(cfg.blocker_policy, "stop-on-blocker")
        self.assertIn("legacy", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
