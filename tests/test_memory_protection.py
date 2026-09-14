"""Regression checks for the host memory protection operator script."""

from pathlib import Path
import subprocess
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "setup-memory-protection.sh"


class MemoryProtectionTests(unittest.TestCase):
    def test_memory_protection_script_is_valid_bash(self) -> None:
        result = subprocess.run(["bash", "-n", str(SCRIPT)], check=False)
        self.assertEqual(result.returncode, 0)

    def test_memory_protection_script_is_idempotent_and_safe(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", text)
        self.assertIn("SWAPFILE=/swapfile-ariadex", text)
        self.assertIn('grep -Fqx "$FSTAB_ENTRY" /etc/fstab', text)
        self.assertNotIn("swapoff -a", text)
        self.assertIn("--prefer '^(chrome|chromium|firefox)$'", text)
        self.assertNotIn("--avoid '^opencode$'", text)
