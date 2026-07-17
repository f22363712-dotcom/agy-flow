"""Tests for agy_flow/workspaces.py — Workspace Registry."""

from agy_flow.errors import AgyFlowError
from agy_flow.workspaces import (
    list_workspaces,
    get_workspace,
    add_workspace,
    remove_workspace,
    set_default,
    resolve_workspace,
)
import agy_flow.config
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestWorkspaces(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self._tp = Path(self._td.name).resolve()
        agy_flow.config.update_paths(self._tp)
        agy_flow.config.AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        try:
            self._td.cleanup()
        except Exception:
            pass

    def test_empty_registry(self):
        ws = list_workspaces()
        self.assertEqual(ws, {})

    def test_add_workspace(self):
        wp = str(self._tp / "my-project")
        result = add_workspace("my-project", wp, description="Test project")
        self.assertEqual(result["name"], "my-project")
        self.assertEqual(result["path"], str(Path(wp).resolve()))

    def test_add_and_list(self):
        wp = str(self._tp / "another-project")
        add_workspace("another", wp)
        ws = list_workspaces()
        self.assertIn("another", ws)

    def test_get_workspace(self):
        wp = str(self._tp / "test-get")
        add_workspace("test-get", wp)
        result = get_workspace("test-get")
        self.assertEqual(result["name"], "test-get")

    def test_get_unknown_raises(self):
        with self.assertRaises(AgyFlowError):
            get_workspace("nonexistent")

    def test_remove_workspace(self):
        add_workspace("to-remove", str(self._tp / "remove"))
        remove_workspace("to-remove")
        with self.assertRaises(AgyFlowError):
            get_workspace("to-remove")

    def test_remove_unknown_raises(self):
        with self.assertRaises(AgyFlowError):
            remove_workspace("nonexistent")

    def test_set_default(self):
        add_workspace("default-ws", str(self._tp / "default"))
        set_default("default-ws")
        name, _ = resolve_workspace()
        self.assertEqual(name, "default-ws")

    def test_resolve_without_default(self):
        ws = list_workspaces()
        for name in list(ws.keys()):
            remove_workspace(name)
        name, _ = resolve_workspace()
        self.assertIsNone(name)

    def test_add_with_spaces_raises(self):
        with self.assertRaises(AgyFlowError):
            add_workspace("bad name", str(self._tp / "bad"))


class TestWorkspacesWithGatewayAPI(unittest.TestCase):
    """Integration tests for workspace endpoints."""

    @classmethod
    def setUpClass(cls):
        import threading
        import socket
        import importlib.util
        from http.server import HTTPServer

        os.environ["AGY_FLOW_TESTING"] = "1"
        cls._temp_dir = tempfile.TemporaryDirectory()
        cls._temp_path = Path(cls._temp_dir.name).resolve()

        spec = importlib.util.spec_from_file_location(
            "agy_flow_main", project_root / "agy-flow.py"
        )
        cls.mod = importlib.util.module_from_spec(spec)
        sys.modules["agy_flow_main"] = cls.mod
        spec.loader.exec_module(cls.mod)

        cls.old_root = cls.mod.PROJECT_ROOT
        cls.mod.PROJECT_ROOT = cls._temp_path
        cls.mod.AGENTS_DIR = cls._temp_path / ".agents"
        cls.mod.TASKS_DIR = cls.mod.AGENTS_DIR / "tasks"
        cls.mod.BOARD_FILE = cls.mod.TASKS_DIR / "board.md"

        import agy_flow.config as cfg_mod

        cfg_mod.update_paths(cls._temp_path)

        import agy_flow.git_ops

        cls.old_git_root = agy_flow.git_ops.PROJECT_ROOT
        agy_flow.git_ops.PROJECT_ROOT = cls._temp_path

        class DummyArgs:
            pass

        cls.mod.init_project(DummyArgs())

        config_path = cls._temp_path / ".agents" / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            cfg["worktrees_dir"] = str(cls._temp_path / "worktrees")
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

        class DummyCreateArgs:
            title = "Workspace test"
            agent = "codex"
            desc = "Testing workspace"

        cls.mod.create_task(DummyCreateArgs())

        def free_port():
            s = socket.socket()
            s.bind(("", 0))
            p = s.getsockname()[1]
            s.close()
            return p

        cls.port = free_port()
        cls.server = HTTPServer(("127.0.0.1", cls.port), cls.mod.AgyFlowHTTPHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.mod.PROJECT_ROOT = cls.old_root
        import agy_flow.config as cfg_mod

        cfg_mod.update_paths(cls.old_root)
        import agy_flow.git_ops

        agy_flow.git_ops.PROJECT_ROOT = cls.old_git_root
        try:
            cls._temp_dir.cleanup()
        except Exception:
            pass

    def _fetch(self, path):
        import urllib.request

        with urllib.request.urlopen(f"{self.url}{path}") as res:
            return res.status, json.loads(res.read().decode("utf-8"))

    def test_workspaces_endpoint(self):
        status, data = self._fetch("/workspaces")
        self.assertEqual(status, 200)
        self.assertIsInstance(data, dict)

    def test_workspace_default_endpoint(self):
        status, data = self._fetch("/workspaces/default")
        self.assertEqual(status, 200)
        self.assertIn("default", data)


if __name__ == "__main__":
    unittest.main()
