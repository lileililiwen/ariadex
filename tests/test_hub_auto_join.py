"""Regression coverage for hub auto-join on `start`."""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))


def install_fake_tk(test: unittest.TestCase):
    from test_robot_hub import FakeTkRoot, FakeTkWidget

    tk_mod = types.ModuleType("tkinter")
    tk_mod.Tk = FakeTkRoot  # type: ignore[attr-defined]
    tk_mod.Frame = FakeTkWidget  # type: ignore[attr-defined]
    tk_mod.Label = FakeTkWidget  # type: ignore[attr-defined]
    tk_mod.Button = FakeTkWidget  # type: ignore[attr-defined]
    tk_mod.Text = FakeTkWidget  # type: ignore[attr-defined]
    saved = sys.modules.get("tkinter")
    sys.modules["tkinter"] = tk_mod

    def restore():
        if saved is None:
            sys.modules.pop("tkinter", None)
        else:
            sys.modules["tkinter"] = saved

    test.addCleanup(restore)


class HubPathsTest(unittest.TestCase):
    def test_socket_lives_under_user_share(self):
        import os

        from ariadex import hub as hub_mod

        with mock.patch.object(os.path, "expanduser", return_value="/tmp/fakehome"):
            self.assertEqual(
                hub_mod.hub_socket_path(),
                Path("/tmp/fakehome/.local/share/ariadex/hub.sock"),
            )


class HubProtocolTest(unittest.TestCase):
    def setUp(self):
        from ariadex import hub as hub_mod

        self.hub_mod = hub_mod
        self.server = hub_mod.HubWindowServer()

    def test_ping_ok(self):
        self.assertEqual(self.server.handle("ping", {}), {"ok": True})

    def test_tabs_empty(self):
        self.assertEqual(self.server.handle("tabs", {}), {"ok": True, "tabs": []})

    def test_register_needs_project(self):
        response = self.server.handle("register", {})
        self.assertFalse(response["ok"])
        self.assertIn("project", response["error"])

    def test_register_missing_dir_refused(self):
        response = self.server.handle(
            "register", {"project": "/nonexistent-ariadex-hub-probe"}
        )
        self.assertFalse(response["ok"])
        self.assertIn("not a directory", response["error"])

    def test_register_uninitialized_dir_refused(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            response = self.server.handle("register", {"project": tmp})
        self.assertFalse(response["ok"])
        self.assertIn("not initialized", response["error"])

    def test_unregister_unknown_is_ok(self):
        self.assertEqual(
            self.server.handle("unregister", {"project": "/tmp/x"}),
            {"ok": True},
        )

    def test_unknown_request_rejected(self):
        with self.assertRaises(self.hub_mod.HubError):
            self.hub_mod._parse_request('{"type": "nope"}\n')

    def test_malformed_json_rejected(self):
        with self.assertRaises(self.hub_mod.HubError):
            self.hub_mod._parse_request("not json\n")

    def test_oversize_message_rejected(self):
        with self.assertRaises(self.hub_mod.HubError):
            self.hub_mod._encode({"type": "ping", "pad": "x" * 70000})


class DaemonMappingTest(unittest.TestCase):
    def test_mode_maps_to_phase(self):
        from ariadex import hub as hub_mod

        cases = {
            "AUTO": "working",
            "PAUSE": "paused",
            "MANUAL": "waiting",
            "unknown": "unknown",
        }
        for mode, phase in cases.items():
            with self.subTest(mode=mode):
                view = hub_mod._daemon_status_view(
                    {"mode": mode, "session": "s", "next_action": "run x"},
                    "opencode",
                )
                self.assertEqual(view["phase"], phase)
                self.assertEqual(view["provider"], "opencode")

    def test_latest_carries_spec_and_next_action(self):
        from ariadex import hub as hub_mod

        view = hub_mod._daemon_status_view(
            {
                "mode": "AUTO",
                "session": "s",
                "next_action": "run target",
                "diagnostic_context": {"current_spec": "my-change"},
            },
            "codex",
        )
        self.assertIn("my-change", view["latest_event"]["message"])
        self.assertIn("run target", view["latest_event"]["message"])

    def test_missing_context_falls_back_to_mode(self):
        from ariadex import hub as hub_mod

        view = hub_mod._daemon_status_view({"mode": "AUTO"}, "opencode")
        self.assertIn("AUTO", view["latest_event"]["message"])


class DaemonTabTest(unittest.TestCase):
    def _init_project(self, root: Path) -> Path:
        from contextlib import chdir

        from ariadex import cli as cli_mod

        root.mkdir(parents=True, exist_ok=True)
        with chdir(root):
            self.assertEqual(cli_mod.main(["init"]), 0)
        return root

    def test_register_resolves_label_and_queue(self):
        import tempfile

        from ariadex import hub as hub_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_project(Path(tmp) / "a")
            server = hub_mod.HubWindowServer()
            response = server.handle("register", {"project": str(root)})
            self.assertTrue(response["ok"], response)
            self.assertIn("[opencode]", response["label"])
            self.assertEqual(len(server.tabs), 1)
            again = server.handle("register", {"project": str(root)})
            self.assertTrue(again["ok"])
            self.assertEqual(len(server.tabs), 1)
            listed = server.handle("tabs", {})
            self.assertEqual(listed["tabs"], [response["label"]])
            server.remove_project(str(root))
            self.assertEqual(server.tabs, {})

    def test_tab_status_unreachable_without_daemon(self):
        import tempfile

        from ariadex import hub as hub_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_project(Path(tmp) / "a")
            server = hub_mod.HubWindowServer()
            server.handle("register", {"project": str(root)})
            tab = next(iter(server.tabs.values()))
            with self.assertRaises(RuntimeError):
                tab.status_fn()

    def test_tab_status_maps_daemon_view(self):
        import tempfile

        from ariadex import hub as hub_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_project(Path(tmp) / "a")
            server = hub_mod.HubWindowServer()
            server.handle("register", {"project": str(root)})
            tab = next(iter(server.tabs.values()))
            state = {
                "mode": "PAUSE",
                "session": "s",
                "next_action": "none",
                "diagnostic_context": {"current_spec": "c"},
            }
            from ariadex import daemon as daemon_mod

            with mock.patch.object(
                daemon_mod,
                "send_request",
                return_value={"ok": True, "state": state},
            ):
                status = tab.status_fn()
            self.assertEqual(status["phase"], "paused")
            self.assertTrue(status["paused"])
            self.assertIn("c", status["latest_event"]["message"])

    def test_tab_pause_resume_drive_daemon(self):
        import tempfile

        from ariadex import hub as hub_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_project(Path(tmp) / "a")
            server = hub_mod.HubWindowServer()
            server.handle("register", {"project": str(root)})
            tab = next(iter(server.tabs.values()))
            calls = []
            from ariadex import daemon as daemon_mod

            def fake_send(project_dir, request_type, **kwargs):
                calls.append(request_type)
                return {"ok": True, "state": {}}

            with mock.patch.object(daemon_mod, "send_request", side_effect=fake_send):
                self.assertEqual(tab.on_pause(), "paused")
                self.assertEqual(tab.on_resume(), "resumed")
            self.assertEqual(calls, ["pause", "resume"])

    def test_tab_pause_refusal_reported(self):
        import tempfile

        from ariadex import hub as hub_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = self._init_project(Path(tmp) / "a")
            server = hub_mod.HubWindowServer()
            server.handle("register", {"project": str(root)})
            tab = next(iter(server.tabs.values()))
            from ariadex import daemon as daemon_mod

            with mock.patch.object(
                daemon_mod,
                "send_request",
                return_value={"ok": False, "error": "nope"},
            ):
                self.assertIn("nope", tab.on_pause())

    def test_tab_quit_unregisters_only_that_tab(self):
        import tempfile

        from ariadex import hub as hub_mod

        with tempfile.TemporaryDirectory() as tmp:
            root_a = self._init_project(Path(tmp) / "a")
            root_b = self._init_project(Path(tmp) / "b")
            server = hub_mod.HubWindowServer()
            server.handle("register", {"project": str(root_a)})
            server.handle("register", {"project": str(root_b)})
            tab_a = server.tabs[str(root_a.resolve())]
            tab_a.on_quit()
            self.assertEqual(len(server.tabs), 1)


class HubClientTest(unittest.TestCase):
    def test_alive_false_without_socket(self):
        from ariadex import hub as hub_mod

        with mock.patch.object(
            hub_mod, "hub_socket_path", return_value=Path("/nonexistent-hub.sock")
        ):
            self.assertFalse(hub_mod.hub_alive())

    def test_ensure_reuses_running_hub(self):
        from ariadex import hub as hub_mod

        with (
            mock.patch.object(hub_mod, "hub_alive", return_value=True),
            mock.patch.object(hub_mod, "_spawn_hub_process") as spawn,
        ):
            ready, _ = hub_mod.ensure_hub()
        self.assertTrue(ready)
        spawn.assert_not_called()

    def test_ensure_spawns_then_ready(self):
        from ariadex import hub as hub_mod

        with (
            mock.patch.object(hub_mod, "hub_alive", side_effect=[False, True]),
            mock.patch.object(hub_mod, "_spawn_hub_process") as spawn,
        ):
            ready, reason = hub_mod.ensure_hub()
        self.assertTrue(ready)
        self.assertEqual(reason, "")
        spawn.assert_called_once()

    def test_ensure_reports_spawn_failure(self):
        from ariadex import hub as hub_mod

        with (
            mock.patch.object(hub_mod, "hub_alive", return_value=False),
            mock.patch.object(
                hub_mod,
                "_spawn_hub_process",
                side_effect=hub_mod.HubError("no display"),
            ),
        ):
            ready, reason = hub_mod.ensure_hub()
        self.assertFalse(ready)
        self.assertIn("no display", reason)

    def test_register_round_trip(self):
        from ariadex import hub as hub_mod

        with mock.patch.object(
            hub_mod, "_send_round_trip", return_value={"ok": True, "label": "a [x]"}
        ):
            self.assertEqual(hub_mod.register_project(Path("/tmp/a")), (True, "a [x]"))
        with mock.patch.object(
            hub_mod,
            "_send_round_trip",
            return_value={"ok": False, "error": "bad"},
        ):
            self.assertEqual(hub_mod.register_project(Path("/tmp/a")), (False, "bad"))
        with mock.patch.object(
            hub_mod,
            "_send_round_trip",
            side_effect=hub_mod.HubError("down"),
        ):
            ok, reason = hub_mod.register_project(Path("/tmp/a"))
            self.assertFalse(ok)
            self.assertIn("down", reason)

    def test_unregister_never_raises(self):
        from ariadex import hub as hub_mod

        with mock.patch.object(
            hub_mod,
            "_send_round_trip",
            side_effect=hub_mod.HubError("down"),
        ):
            hub_mod.unregister_project(Path("/tmp/a"))


class HubServerSocketTest(unittest.TestCase):
    def test_listen_register_ping_round_trip(self):
        import json
        import socket
        import tempfile

        from ariadex import hub as hub_mod

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(hub_mod, "hub_dir", return_value=Path(tmp)),
        ):
            server = hub_mod.HubWindowServer()
            server.listen()
            try:
                self.assertTrue(server._server is not None)
                conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                conn.settimeout(5)
                conn.connect(str(Path(tmp) / "hub.sock"))
                conn.sendall(b'{"type": "ping"}\n')
                server.poll_socket()
                raw = b""
                while b"\n" not in raw:
                    raw += conn.recv(4096)
                conn.close()
                self.assertEqual(json.loads(raw.decode()), {"ok": True})
                self.assertTrue(
                    (Path(tmp) / "hub.sock").exists() or server._server is not None
                )
            finally:
                server.close()
            self.assertFalse((Path(tmp) / "hub.sock").exists())


class StartHubWiringTest(unittest.TestCase):
    def test_hub_tab_skips_single_widget(self):
        import tempfile

        from test_managed_start import Harness, make_project

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            harness = Harness(root)
            rc = harness.run(hub_register_fn=lambda project: "a [opencode]")
        self.assertEqual(rc, 0)
        self.assertNotIn("spawn_widget", harness.calls)

    def test_hub_unavailable_falls_back_to_widget(self):
        import tempfile

        from test_managed_start import Harness, make_project

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            harness = Harness(root)
            rc = harness.run(hub_register_fn=lambda project: None)
        self.assertEqual(rc, 0)
        self.assertIn("spawn_widget", harness.calls)

    def test_hub_error_falls_back_to_widget(self):
        import tempfile

        from test_managed_start import Harness, make_project

        def boom(project):
            raise RuntimeError("hub down")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            harness = Harness(root)
            rc = harness.run(hub_register_fn=boom)
        self.assertEqual(rc, 0)
        self.assertIn("spawn_widget", harness.calls)


class StopUnregisterTest(unittest.TestCase):
    def test_stop_unregisters_best_effort(self):
        import tempfile
        from contextlib import chdir

        from ariadex import cli as cli_mod
        from ariadex import hub as hub_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with chdir(root):
                self.assertEqual(cli_mod.main(["init"]), 0)
            with mock.patch.object(hub_mod, "unregister_project") as unregister:
                self.assertEqual(cli_mod.cmd_stop(root), 0)
            unregister.assert_called_once_with(root)


class HubWindowCommandTest(unittest.TestCase):
    def test_hub_error_is_exit_error(self):
        from ariadex import cli as cli_mod
        from ariadex import hub as hub_mod

        with mock.patch.object(
            hub_mod, "run_hub_window", side_effect=hub_mod.HubError("no display")
        ):
            self.assertNotEqual(cli_mod.cmd_hub_window(), 0)

    def test_hub_window_refuses_headless(self):
        from ariadex import companion as companion_mod
        from ariadex import hub as hub_mod

        with (
            mock.patch.object(
                companion_mod,
                "detect_desktop",
                return_value=companion_mod.DesktopInfo("headless", False, "no display"),
            ),
            self.assertRaises(hub_mod.HubError),
        ):
            hub_mod.run_hub_window()


class HubWindowTabsTest(unittest.TestCase):
    def setUp(self):
        install_fake_tk(self)

    def test_server_register_adds_window_tab(self):
        import tempfile

        from test_robot_hub import FakeTkRoot, make_tab

        from ariadex import companion as companion_mod
        from ariadex import hub as hub_mod

        with tempfile.TemporaryDirectory() as tmp:
            root = FakeTkRoot()
            window = companion_mod.RobotHubWindow(root, [])
            server = hub_mod.HubWindowServer()
            server.window = window
            tab, _ = make_tab(str(Path(tmp) / "a"))
            server.tabs[str(Path(tmp) / "a")] = tab
            window.add_tab(tab)
            self.assertEqual(len(window.tabs), 1)
            self.assertEqual(len(window.tab_buttons), 1)
            window.remove_project(str(Path(tmp) / "a"))
            self.assertEqual(window.tabs, [])


if __name__ == "__main__":
    unittest.main()
