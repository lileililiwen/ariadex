"""Tests for the standalone widget theme module and build identity."""

import unittest

from ariadex import theme as theme_mod
from ariadex import upgrade as upgrade_mod


class ThemeRegistryTest(unittest.TestCase):
    def test_three_themes_available(self):
        self.assertEqual(theme_mod.theme_names(), ["contrast", "dark", "light"])

    def test_default_is_dark(self):
        self.assertEqual(theme_mod.DEFAULT_THEME_NAME, "dark")
        self.assertEqual(theme_mod.get_theme("dark").name, "dark")

    def test_unknown_names_fall_back_to_dark(self):
        for bad in ("", "nope", None, 7, " DARK "[:0]):
            self.assertEqual(theme_mod.get_theme(bad).name, "dark")

    def test_case_insensitive_lookup(self):
        self.assertEqual(theme_mod.get_theme("Light").name, "light")

    def test_every_role_resolves_for_every_theme(self):
        for name in theme_mod.theme_names():
            theme = theme_mod.get_theme(name)
            for role in theme_mod.ROLES:
                opts = theme_mod.options(theme, role)
                self.assertTrue(opts, f"{name}/{role}")
                if role in ("label", "button", "text_input", "text_log"):
                    self.assertIn("background", opts)
                    self.assertIn("foreground", opts)

    def test_unknown_role_fails_loudly(self):
        with self.assertRaises(KeyError):
            theme_mod.options(theme_mod.DARK, "wat")

    def test_dark_preserves_historical_values(self):
        dark = theme_mod.DARK
        self.assertEqual(dark.window_bg, "#20242b")
        self.assertEqual(dark.log_bg, "#14171c")
        self.assertEqual(dark.button_bg, "#2b313a")

    def test_backgrounds_stay_inside_their_own_theme(self):
        for name in theme_mod.theme_names():
            theme = theme_mod.get_theme(name)
            surfaces = {
                theme.window_bg,
                theme.input_bg,
                theme.button_bg,
                theme.log_bg,
                theme.trough_bg,
                theme.selection_bg,
                theme.press_bg,
                theme.press_active_bg,
                theme.success_bg,
                theme.success_active_bg,
                theme.button_active_bg,
            }
            for role in theme_mod.ROLES:
                for key, value in theme_mod.options(theme, role).items():
                    if key in ("background", "troughcolor", "selectbackground"):
                        self.assertIn(value, surfaces, f"{name}/{role}/{key}")


class DescribeBuildTest(unittest.TestCase):
    def test_clean_checkout_appends_sha(self):
        def fake(argv, cwd):
            return "abc1234" if argv[0] == "rev-parse" else ""

        text = upgrade_mod.describe_build("/repo", _git=fake)
        self.assertTrue(text.startswith(upgrade_mod.running_version() + "+gabc1234"))
        self.assertNotIn("dirty", text)

    def test_dirty_checkout_marks_dirty(self):
        def fake(argv, cwd):
            if argv[0] == "rev-parse":
                return "abc1234"
            return " M src/ariadex/cli.py\n"

        self.assertTrue(
            upgrade_mod.describe_build("/repo", _git=fake).endswith("-dirty")
        )

    def test_missing_git_falls_back_to_version(self):
        def empty(argv, cwd):
            return ""

        def missing(argv, cwd):
            return None

        self.assertEqual(
            upgrade_mod.describe_build("/repo", _git=empty),
            upgrade_mod.running_version(),
        )
        self.assertEqual(
            upgrade_mod.describe_build("/repo", _git=missing),
            upgrade_mod.running_version(),
        )

    def test_git_errors_never_raise(self):
        def boom(argv, cwd):
            raise OSError("no git")

        self.assertEqual(
            upgrade_mod.describe_build("/repo", _git=boom),
            upgrade_mod.running_version(),
        )


if __name__ == "__main__":
    unittest.main()
