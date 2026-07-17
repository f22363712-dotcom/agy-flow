"""Tests for agent_relay/quality_gate.py — Quality Gate v1."""

from agent_relay.errors import AgentRelayError
from agent_relay.state_machine import set_task_state
from agent_relay.quality_gate import evaluate_task_quality
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestQualityGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name).resolve()
        import agent_relay.config

        agent_relay.config.update_paths(cls.temp_path)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def _mock_runs(self, runs):
        """Patch list_runs to return given runs."""
        return patch("agent_relay.quality_gate.list_runs", return_value=runs)

    def test_approved_with_writer_and_reviewer_ready(self):
        """approved task + writer + reviewer -> ready."""
        set_task_state("task-qt1", "approved", reason="review ok")
        writer_run = {
            "run_id": "r1",
            "role": "writer",
            "agent": "claude",
            "parsed_output": {
                "status": "completed",
                "next_action": "review",
                "summary": "done",
            },
            "tests_run": ["pytest"],
            "files_touched": ["src/main.py"],
            "risks": [],
        }
        reviewer_run = {
            "run_id": "r2",
            "role": "reviewer",
            "agent": "deepseek",
            "parsed_output": {"status": "completed", "next_action": "submit"},
            "tests_run": [],
            "files_touched": [],
            "risks": [],
        }
        with self._mock_runs([reviewer_run, writer_run]):
            quality = evaluate_task_quality("task-qt1")
            self.assertTrue(quality["ready"])
            self.assertEqual(len(quality["blocking_issues"]), 0)
            self.assertEqual(quality["recommended_next_action"], "submit")

    def test_blocked_not_ready(self):
        set_task_state("task-qt2", "blocked", reason="blocked")
        with self._mock_runs([]):
            quality = evaluate_task_quality("task-qt2")
            self.assertFalse(quality["ready"])
            self.assertGreater(len(quality["blocking_issues"]), 0)

    def test_revision_requested_not_ready(self):
        set_task_state("task-qt3", "revision_requested", reason="revise")
        with self._mock_runs([]):
            quality = evaluate_task_quality("task-qt3")
            self.assertFalse(quality["ready"])
            blocking = " ".join(quality["blocking_issues"]).lower()
            self.assertIn("revision", blocking)

    def test_no_writer_run_not_ready(self):
        set_task_state("task-qt4", "planned")
        with self._mock_runs([]):
            quality = evaluate_task_quality("task-qt4")
            self.assertFalse(quality["ready"])
            blocking = " ".join(quality["blocking_issues"]).lower()
            self.assertIn("no writer run", blocking)

    def test_writer_needs_review_no_reviewer_not_ready(self):
        set_task_state("task-qt5", "needs_review")
        writer_run = {
            "run_id": "r1",
            "role": "writer",
            "parsed_output": {"status": "completed", "next_action": "review"},
        }
        with self._mock_runs([writer_run]):
            quality = evaluate_task_quality("task-qt5")
            self.assertFalse(quality["ready"])
            blocking = " ".join(quality["blocking_issues"]).lower()
            self.assertIn("review", blocking)

    def test_reviewer_revise_not_ready(self):
        set_task_state("task-qt6", "reviewing")
        writer_run = {
            "run_id": "r1",
            "role": "writer",
            "parsed_output": {"status": "completed", "next_action": "review"},
        }
        reviewer_run = {
            "run_id": "r2",
            "role": "reviewer",
            "parsed_output": {"status": "completed", "next_action": "revise"},
        }
        with self._mock_runs([reviewer_run, writer_run]):
            quality = evaluate_task_quality("task-qt6")
            self.assertFalse(quality["ready"])
            blocking = " ".join(quality["blocking_issues"]).lower()
            self.assertIn("revise", blocking)

    def test_missing_tests_warning(self):
        set_task_state("task-qt7", "approved")
        writer_run = {
            "run_id": "r1",
            "role": "writer",
            "parsed_output": {"status": "completed", "next_action": "submit"},
            "tests_run": [],
            "files_touched": ["src/main.py"],
            "risks": [],
        }
        with self._mock_runs([writer_run]):
            quality = evaluate_task_quality("task-qt7")
            self.assertTrue(quality["ready"])
            warnings = " ".join(quality["warnings"]).lower()
            self.assertIn("no tests_run", warnings)

    def test_nonempty_risks_warning(self):
        set_task_state("task-qt8", "approved")
        writer_run = {
            "run_id": "r1",
            "role": "writer",
            "parsed_output": {"status": "completed", "next_action": "submit"},
            "risks": ["Edge case in auth"],
            "files_touched": ["src/main.py"],
            "tests_run": ["pytest"],
        }
        with self._mock_runs([writer_run]):
            quality = evaluate_task_quality("task-qt8")
            self.assertTrue(quality["ready"])
            self.assertIn("Edge case in auth", quality["risks"])

    def test_no_files_touched_warning(self):
        set_task_state("task-qt9", "approved")
        writer_run = {
            "run_id": "r1",
            "role": "writer",
            "parsed_output": {"status": "completed", "next_action": "submit"},
            "files_touched": [],
            "tests_run": ["pytest"],
            "risks": [],
        }
        with self._mock_runs([writer_run]):
            quality = evaluate_task_quality("task-qt9")
            self.assertTrue(quality["ready"])
            warnings = " ".join(quality["warnings"]).lower()
            self.assertIn("no files_touched", warnings)

    def test_output_keys(self):
        set_task_state("task-qt10", "planned")
        with self._mock_runs([]):
            quality = evaluate_task_quality("task-qt10")
            expected_keys = {
                "task_id",
                "state",
                "ready",
                "blocking_issues",
                "warnings",
                "latest_writer_run",
                "latest_reviewer_run",
                "tests_run",
                "files_touched",
                "risks",
                "recommended_next_action",
            }
            for key in expected_keys:
                self.assertIn(key, quality, f"Missing key: {key}")


class TestQualityGateWithGatewayAPI(unittest.TestCase):
    """Integration tests using gateway."""

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
            title = "Quality test"
            agent = "codex"
            desc = "Testing quality gate"

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

    def test_quality_endpoint(self):
        status, data = self._fetch("/tasks/task-001/quality")
        self.assertEqual(status, 200)
        self.assertIn("ready", data)
        self.assertIn("blocking_issues", data)

    def test_finalize_dry_run_endpoint(self):
        status, data = self._fetch(
            "/tasks/task-001/finalize",
            method="POST",
            data=json.dumps({"dry_run": True}),
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "dry_run")
        self.assertIn("quality", data)

    def test_finalize_unknown_task(self):
        status, data = self._fetch(
            "/tasks/task-999/finalize",
            method="POST",
            data=json.dumps({"dry_run": True}),
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "dry_run")


if __name__ == "__main__":
    unittest.main()
