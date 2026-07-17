"""Tests for agent_relay/handoff.py — lease_writer and whoami."""

from agent_relay.errors import AgentRelayError
from agent_relay.handoff import lease_writer, whoami, assign_current_task_agent
import agent_relay.config
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestLeaseWriter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name).resolve()
        agent_relay.config.update_paths(cls.temp_path)
        agent_relay.config.AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def _write_guard(self, data):
        path = agent_relay.config.AGENTS_DIR / "current_task.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def test_lease_unchanged_when_same_writer(self):
        self._write_guard(
            {
                "writer": "claude",
                "agent": "claude",
                "role": "writer",
                "reviewers": ["Codex"],
                "mode": "handoff",
                "timestamp": "now",
            }
        )
        result = lease_writer("claude")
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["writer"], "claude")

    def test_lease_when_writer_empty(self):
        self._write_guard({"reviewers": [], "mode": "handoff"})

        result = lease_writer("codex")
        self.assertEqual(result["status"], "leased")
        self.assertEqual(result["writer"], "Codex")

        # Verify guard file was updated
        p2 = agent_relay.config.AGENTS_DIR / "current_task.json"
        guard = json.loads(p2.read_text(encoding="utf-8"))
        self.assertEqual(guard.get("writer"), "Codex")
        self.assertEqual(guard.get("role"), "writer")

    def test_lease_conflict_without_force(self):
        self._write_guard(
            {
                "writer": "claude",
                "agent": "claude",
                "role": "writer",
                "reviewers": [],
                "mode": "handoff",
                "timestamp": "now",
            }
        )
        result = lease_writer("codex")
        self.assertEqual(result["status"], "conflict")
        self.assertIn("suggested_command", result)
        self.assertEqual(result["writer"], "Codex")
        self.assertEqual(result["previous_writer"], "claude")

    def test_lease_forced(self):
        self._write_guard(
            {
                "writer": "claude",
                "agent": "claude",
                "role": "writer",
                "reviewers": ["Codex"],
                "mode": "handoff",
                "timestamp": "now",
            }
        )
        result = lease_writer("codex", force=True)
        self.assertEqual(result["status"], "forced")
        self.assertEqual(result["writer"], "Codex")

        # Verify guard
        path = agent_relay.config.AGENTS_DIR / "current_task.json"
        guard = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(guard.get("writer"), "Codex")

    def test_lease_preserves_reviewers(self):
        self._write_guard(
            {
                "writer": "claude",
                "agent": "claude",
                "role": "reviewer",
                "reviewers": ["Codex", "antigravity"],
                "mode": "review",
                "timestamp": "now",
            }
        )
        result = lease_writer("codex")
        self.assertEqual(result["status"], "leased")
        self.assertEqual(result["writer"], "Codex")
        self.assertIn("Codex", result["reviewers"])
        self.assertIn("antigravity", result["reviewers"])

    def test_lease_legacy_agent_preserved(self):
        self._write_guard(
            {
                "writer": "Codex",
                "agent": "Codex",
                "role": "writer",
                "reviewers": [],
                "mode": "handoff",
                "timestamp": "now",
            }
        )
        lease_writer("claude", force=True)
        path = agent_relay.config.AGENTS_DIR / "current_task.json"
        guard = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(guard.get("agent"), "claude")
        self.assertEqual(guard.get("writer"), "claude")

    def test_whoami_returns_guard(self):
        self._write_guard(
            {
                "writer": "claude",
                "agent": "claude",
                "role": "writer",
                "reviewers": ["Codex"],
                "mode": "handoff",
                "task_id": "task-001",
                "timestamp": "now",
            }
        )
        info = whoami()
        self.assertEqual(info["writer"], "claude")
        self.assertEqual(info["role"], "writer")
        self.assertIn("Codex", info["reviewers"])
        self.assertTrue(info["can_write"])

    def test_whoami_no_guard(self):
        guard_path = agent_relay.config.AGENTS_DIR / "current_task.json"
        if guard_path.exists():
            guard_path.unlink()
        info = whoami()
        self.assertIsNone(info["writer"])
        self.assertFalse(info["can_write"])

    def test_lease_with_reason(self):
        self._write_guard(
            {
                "writer": "Codex",
                "agent": "Codex",
                "role": "writer",
                "reviewers": [],
                "mode": "handoff",
            }
        )
        lease_writer("claude", force=True, reason="Need Claude for backend work")
        path = agent_relay.config.AGENTS_DIR / "current_task.json"
        guard = json.loads(path.read_text(encoding="utf-8"))
        # reason is in the result not the guard — check the function call
        # didn't fail
        self.assertEqual(guard.get("writer"), "claude")


class TestWhoamiWithGatewayAPI(unittest.TestCase):
    """Integration tests for whoami and lease via gateway."""

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

        # Patch internal module paths via the imported module
        import importlib

        cfg_mod = importlib.import_module("agent_relay.config")
        cfg_mod.update_paths(cls.temp_path)

        git_mod = importlib.import_module("agent_relay.git_ops")
        cls.old_git_root = git_mod.PROJECT_ROOT
        git_mod.PROJECT_ROOT = cls.temp_path

        class DummyArgs:
            pass

        cls.mod.init_project(DummyArgs())

        config_path = cls.temp_path / ".agents" / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            cfg["worktrees_dir"] = str(cls.temp_path / "worktrees")
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

        class DummyCreateArgs:
            title = "Handoff test"
            agent = "codex"
            desc = "Testing lease/whoami"

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
        import importlib

        importlib.import_module("agent_relay.config").update_paths(cls.old_root)
        importlib.import_module("agent_relay.git_ops").PROJECT_ROOT = cls.old_git_root
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def _fetch(self, path, method="GET", data=None):
        import urllib.request
        import urllib.error

        req = urllib.request.Request(
            f"{self.url}{path}",
            data=data.encode("utf-8") if data else None,
            headers={"Content-Type": "application/json"} if data else {},
            method=method,
        )
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_get_whoami_endpoint(self):
        status, data = self._fetch("/whoami")
        self.assertEqual(status, 200)
        self.assertIn("writer", data)
        self.assertIn("reviewers", data)

    def test_post_lease_endpoint(self):
        status, data = self._fetch(
            "/lease",
            method="POST",
            data=json.dumps({"agent": "claude", "force": True}),
        )
        self.assertEqual(status, 200)
        self.assertIn("status", data)
        self.assertIn("writer", data)


if __name__ == "__main__":
    unittest.main()
