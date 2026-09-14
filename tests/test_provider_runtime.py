"""Regression tests for provider backend ownership and stale cleanup."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ariadex import provider_runtime


class ProviderRuntimeRecordTests(unittest.TestCase):
    def test_record_round_trip_is_atomic_and_project_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = provider_runtime.ProviderRuntimeRecord(
                provider="opencode",
                project=str(root.resolve()),
                session_id="session-1",
                tmux_session="ariadex-session-1",
                endpoint="http://127.0.0.1:43123",
                port=43123,
                pid=1234,
                process_start_ticks=5678,
                generation="generation-1",
            )
            self.assertEqual(provider_runtime.write_record(root, record), record)
            self.assertEqual(provider_runtime.read_record(root), record)

    def test_record_is_valid_only_when_process_identity_and_endpoint_match(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = provider_runtime.ProviderRuntimeRecord(
                provider="opencode",
                project=str(root.resolve()),
                session_id="session-1",
                tmux_session="ariadex-session-1",
                endpoint="http://127.0.0.1:43123",
                port=43123,
                pid=1234,
                process_start_ticks=5678,
                generation="generation-1",
            )
            provider_runtime.write_record(root, record)
            with mock.patch.object(
                provider_runtime,
                "process_identity",
                return_value=(1234, 5678),
            ), mock.patch.object(
                provider_runtime,
                "endpoint_is_responsive",
                return_value=True,
            ):
                self.assertTrue(provider_runtime.is_reusable(root, record))

            with mock.patch.object(
                provider_runtime,
                "process_identity",
                return_value=(1234, 9999),
            ), mock.patch.object(
                provider_runtime,
                "endpoint_is_responsive",
                return_value=True,
            ):
                self.assertFalse(provider_runtime.is_reusable(root, record))

    def test_unknown_process_is_never_owned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = provider_runtime.ProviderRuntimeRecord(
                provider="opencode",
                project=str(root.resolve()),
                session_id="session-1",
                tmux_session="ariadex-session-1",
                endpoint="http://127.0.0.1:43123",
                port=43123,
                pid=1234,
                process_start_ticks=5678,
                generation="generation-1",
            )
            with mock.patch.object(
                provider_runtime,
                "process_identity",
                return_value=(1234, 5678),
            ), mock.patch.object(
                provider_runtime,
                "endpoint_is_responsive",
                return_value=False,
            ):
                self.assertFalse(provider_runtime.is_reusable(root, record))

    def test_missing_process_record_is_not_reusable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = provider_runtime.ProviderRuntimeRecord(
                provider="opencode",
                project=str(root.resolve()),
                session_id="session-1",
                tmux_session="ariadex-session-1",
                endpoint="http://127.0.0.1:43123",
                port=43123,
                pid=1234,
                process_start_ticks=5678,
                generation="generation-1",
            )
            with mock.patch.object(
                provider_runtime,
                "process_identity",
                side_effect=provider_runtime.psutil.NoSuchProcess(1234),
            ):
                self.assertFalse(provider_runtime.is_reusable(root, record))


if __name__ == "__main__":
    unittest.main()
