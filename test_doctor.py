"""Tests for agent_relay/doctor.py — Doctor and Status."""

from agent_relay.state_machine import set_task_state
from agent_relay.doctor import doctor, task_status
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestDoctor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name).resolve()
        import agent_relay.config

        agent_relay.config.update_paths(cls.temp_path)

        # Init the project so config exists
        from agent_relay.tasks import init_project

        class DummyArgs:
            pass

        init_project(DummyArgs())

        # Fix worktrees_dir in temp config
        config_path = cls.temp_path / ".agents" / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            cfg["worktrees_dir"] = str(cls.temp_path / "worktrees")
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def test_doctor_returns_dict(self):
        result = doctor()
        self.assertIsInstance(result, dict)
        self.assertIn("healthy", result)
        self.assertIn("checks", result)
        self.assertIn("warnings", result)
        self.assertIn("timestamp", result)

    def test_doctor_has_check_details(self):
        result = doctor()
        for check in result.get("checks", []):
            self.assertIn("check", check)
            self.assertIn("status", check)
            self.assertIn("detail", check)

    def test_task_status_returns_summary(self):
        set_task_state("task-status-test", "approved", reason="test")
        info = task_status("task-status-test")
        self.assertEqual(info["task_id"], "task-status-test")
        self.assertIn("state", info)
        self.assertIn("run_count", info)
        self.assertIn("quality_ready", info)
        self.assertIn("policy_run_count", info)
        self.assertIn("timestamp", info)


class TestDoctorWithGatewayAPI(unittest.TestCase):
    """Integration tests for GET /doctor and GET /tasks/{id}/status."""

    @classmethod
    def setUpClass(cls):
        import threading
        import socket
        import importlib.util
        from http.server import HTTPServer

        os.environ["AGY_FLOW_TESTING"] = "1"
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name).resolve()

        spec = importlib.util.spec_from_file_location(
            "agent_relay_main", project_root / "agent-relay.py"
        )
        cls.mod = importlib.util.module_from_spec(spec)
        sys.modules["agent_relay_main"] = cls.mod
        spec.loader.exec_module(cls.mod)

        cls.old_root = cls.mod.PROJECT_ROOT
        cls.mod.PROJECT_ROOT = cls.temp_path
        cls.mod.AGENTS_DIR = cls.temp_path / ".agents"
        cls.mod.TASKS_DIR = cls.mod.AGENTS_DIR / "tasks"
        cls.mod.BOARD_FILE = cls.mod.TASKS_DIR / "board.md"

        import agent_relay.config

        agent_relay.config.update_paths(cls.temp_path)

        import agent_relay.git_ops

        cls.old_git_root = agent_relay.git_ops.PROJECT_ROOT
        agent_relay.git_ops.PROJECT_ROOT = cls.temp_path

        class DummyArgs:
            pass

        cls.mod.init_project(DummyArgs())

        config_path = cls.temp_path / ".agents" / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            cfg["worktrees_dir"] = str(cls.temp_path / "worktrees")
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

        class DummyCreateArgs:
            title = "Doctor test"
            agent = "codex"
            desc = "Testing doctor/status"

        cls.mod.create_task(DummyCreateArgs())

        def free_port():
            s = socket.socket()
            s.bind(("", 0))
            p = s.getsockname()[1]
            s.close()
            return p

        cls.port = free_port()
        cls.server = HTTPServer(("127.0.0.1", cls.port), cls.mod.AgentRelayHTTPHandler)
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
        import agent_relay.config

        agent_relay.config.update_paths(cls.old_root)
        import agent_relay.git_ops

        agent_relay.git_ops.PROJECT_ROOT = cls.old_git_root
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def _fetch(self, path):
        import urllib.request

        with urllib.request.urlopen(f"{self.url}{path}") as res:
            return res.status, json.loads(res.read().decode("utf-8"))

    def test_doctor_endpoint(self):
        status, data = self._fetch("/doctor")
        self.assertEqual(status, 200)
        self.assertIn("healthy", data)
        self.assertIn("checks", data)

    def test_task_status_endpoint(self):
        status, data = self._fetch("/tasks/task-001/status")
        self.assertEqual(status, 200)
        self.assertEqual(data.get("task_id"), "task-001")
        self.assertIn("state", data)
        self.assertIn("quality_ready", data)
        self.assertIn("policy_run_count", data)


if __name__ == "__main__":
    unittest.main()
