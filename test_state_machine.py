"""Tests for agent_relay/state_machine.py — Task State Machine v1."""

from agent_relay.errors import AgentRelayError
from agent_relay.state_machine import (
    get_task_state,
    set_task_state,
    transition_task_state,
    infer_event_from_run,
    VALID_STATES,
)
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestStateMachine(unittest.TestCase):
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

    def test_initial_state_planned(self):
        state = get_task_state("task-new")
        self.assertEqual(state["state"], "planned")

    def test_set_state_persists(self):
        result = set_task_state("task-001", "dispatched", reason="Writer dispatched")
        self.assertEqual(result["state"], "dispatched")
        self.assertEqual(result["previous_state"], "planned")

        # Read back
        state = get_task_state("task-001")
        self.assertEqual(state["state"], "dispatched")
        self.assertEqual(len(state["history"]), 1)

    def test_transition_legal(self):
        set_task_state("task-002", "planned", reason="init")
        result = transition_task_state("task-002", "dispatched")
        self.assertEqual(result["state"], "dispatched")

    def test_transition_illegal_raises(self):
        set_task_state("task-003", "done", reason="init")
        with self.assertRaises(AgentRelayError):
            transition_task_state("task-003", "dispatched")

    def test_invalid_state_raises(self):
        with self.assertRaises(AgentRelayError):
            set_task_state("task-004", "nonexistent")

    def test_history_accumulates(self):
        set_task_state("task-005", "planned")
        transition_task_state("task-005", "dispatched")
        transition_task_state("task-005", "needs_review")
        state = get_task_state("task-005")
        self.assertEqual(len(state["history"]), 3)
        self.assertEqual(state["history"][-1]["to"], "needs_review")

    def test_infer_event_writer_completed_review(self):
        run = {
            "status": "success",
            "role": "writer",
            "parsed_output": {"status": "completed", "next_action": "review"},
        }
        self.assertEqual(infer_event_from_run(run), "needs_review")

    def test_infer_event_writer_completed_submit(self):
        run = {
            "status": "success",
            "role": "writer",
            "parsed_output": {"status": "completed", "next_action": "submit"},
        }
        self.assertEqual(infer_event_from_run(run), "submitted")

    def test_infer_event_reviewer_approved(self):
        run = {
            "status": "success",
            "role": "reviewer",
            "parsed_output": {"status": "completed", "next_action": "submit"},
        }
        self.assertEqual(infer_event_from_run(run), "approved")

    def test_infer_event_reviewer_revise(self):
        run = {
            "status": "success",
            "role": "reviewer",
            "parsed_output": {"status": "completed", "next_action": "revise"},
        }
        self.assertEqual(infer_event_from_run(run), "revision_requested")

    def test_infer_event_blocked(self):
        run = {"status": "unavailable", "role": "writer"}
        self.assertEqual(infer_event_from_run(run), "blocked")

    def test_infer_event_handoff(self):
        run = {"status": "handoff", "role": "writer"}
        self.assertEqual(infer_event_from_run(run), "in_progress")

    def test_infer_event_parsed_blocked(self):
        run = {
            "status": "success",
            "role": "writer",
            "parsed_output": {"status": "blocked", "next_action": "manual"},
        }
        self.assertEqual(infer_event_from_run(run), "blocked")


class TestStateMachineGatewayAPI(unittest.TestCase):
    """Integration tests using gateway endpoints."""

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
            title = "State machine test"
            agent = "codex"
            desc = "Testing state machine"

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

    def test_get_state_endpoint(self):
        status, data = self._fetch("/tasks/task-001/state")
        self.assertEqual(status, 200)
        self.assertIn("state", data)

    def test_post_state_endpoint(self):
        status, data = self._fetch(
            "/tasks/task-001/state",
            method="POST",
            data=json.dumps({"state": "blocked", "reason": "Test block"}),
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("state"), "blocked")

    def test_policy_endpoint(self):
        status, data = self._fetch("/tasks/task-001/policy")
        self.assertEqual(status, 200)
        self.assertIn("task_id", data)
        self.assertIn("state", data)
        self.assertIn("run_count", data)
        self.assertIn("can_dispatch_new", data)


if __name__ == "__main__":
    unittest.main()
