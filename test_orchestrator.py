"""Tests for agent_relay/orchestrator.py — Auto Dispatch Loop v1.

All tests use mocked connector availability to avoid real CLIs/API keys.
"""

from agent_relay.errors import AgentRelayError
from agent_relay.orchestrator import auto_dispatch_task
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


# ---------------------------------------------------------------------------
# Common mock data
# ---------------------------------------------------------------------------


def _mock_report(overrides=None):
    default = {
        "deepseek": {
            "available": False,
            "kind": "llm",
            "reason": "No API key",
            "supports_worktree": False,
            "supports_review": True,
            "supports_write": False,
        },
        "claude": {
            "available": True,
            "kind": "cli",
            "reason": "claude CLI found",
            "supports_worktree": True,
            "supports_review": True,
            "supports_write": True,
        },
        "codex": {
            "available": True,
            "kind": "human",
            "reason": "human handoff",
            "supports_worktree": True,
            "supports_review": True,
            "supports_write": True,
        },
        "antigravity": {
            "available": True,
            "kind": "desktop",
            "reason": "desktop handoff",
            "supports_worktree": True,
            "supports_review": True,
            "supports_write": True,
        },
        "gemini": {
            "available": False,
            "kind": "cli",
            "reason": "not found",
            "supports_worktree": False,
            "supports_review": True,
            "supports_write": False,
        },
    }
    if overrides:
        for name, updates in overrides.items():
            if name in default:
                default[name].update(updates)
    return default


def _make_task(task_id="task-001", title="Test task", agent="claude", status="Todo"):
    """Simulated board row."""
    return {
        "id": task_id,
        "title": title,
        "agent": agent,
        "status": status,
        "branch": "",
        "worktree": "",
    }


class TestAutoDispatch(unittest.TestCase):
    """Tests for auto_dispatch_task with mocked route + adapter."""

    # Patch the internal functions that auto_dispatch_task calls
    @patch(
        "agent_relay.orchestrator.adapter_dispatch",
        return_value={
            "status": "success",
            "run_id": "run-test",
            "result": {"summary": "ok"},
        },
    )
    @patch("agent_relay.orchestrator.route_task_by_id")
    def test_auto_dispatch_success(self, mock_route, mock_adapter):
        """Happy path: route -> adapter_dispatch succeeds."""
        mock_route.return_value = {
            "primary": "claude",
            "fallbacks": ["codex"],
            "reviewers": ["codex"],
            "mode": "write",
            "reason": "claude available",
            "task_id": "task-001",
            "title": "Test",
        }
        result = auto_dispatch_task("task-001")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["selected_agent"], "claude")
        self.assertEqual(len(result["attempts"]), 1)
        mock_adapter.assert_called_once_with(
            "task-001", "claude", mock=False, role="writer"
        )

    @patch(
        "agent_relay.orchestrator.adapter_dispatch",
        side_effect=AgentRelayError("Not available"),
    )
    @patch("agent_relay.orchestrator.route_task_by_id")
    def test_auto_dispatch_fallback(self, mock_route, mock_adapter):
        """When primary fails, fallback to next candidate."""
        mock_route.return_value = {
            "primary": "claude",
            "fallbacks": ["codex", "antigravity"],
            "reviewers": [],
            "mode": "write",
            "reason": "claude preferred",
            "task_id": "task-001",
            "title": "Test",
        }

        # Second call succeeds
        def adapter_dispatch_side_effect(*args, **kwargs):
            if args[1] == "codex":
                return {
                    "status": "handoff",
                    "run_id": "run-codex",
                    "result": {"instruction": "hand off"},
                }
            raise AgentRelayError("Not available")

        mock_adapter.side_effect = adapter_dispatch_side_effect

        result = auto_dispatch_task("task-001")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["selected_agent"], "codex")
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(result["attempts"][0]["agent"], "claude")
        self.assertEqual(result["attempts"][1]["agent"], "codex")

    @patch(
        "agent_relay.orchestrator.adapter_dispatch", side_effect=AgentRelayError("All fail")
    )
    @patch("agent_relay.orchestrator.route_task_by_id")
    def test_auto_dispatch_all_fail(self, mock_route, mock_adapter):
        """When all candidates fail, return failed status."""
        mock_route.return_value = {
            "primary": "claude",
            "fallbacks": ["codex"],
            "reviewers": [],
            "mode": "write",
            "reason": "test",
            "task_id": "task-001",
            "title": "Test",
        }
        result = auto_dispatch_task("task-001")
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["selected_agent"])
        self.assertEqual(len(result["attempts"]), 2)

    @patch("agent_relay.orchestrator.route_task_by_id")
    def test_auto_dispatch_dry_run(self, mock_route):
        """Dry run should not call adapter_dispatch."""
        mock_route.return_value = {
            "primary": "claude",
            "fallbacks": ["codex"],
            "reviewers": [],
            "mode": "write",
            "reason": "test",
            "task_id": "task-001",
            "title": "Test",
        }
        result = auto_dispatch_task("task-001", dry_run=True)
        self.assertEqual(result["status"], "dry_run")
        self.assertIn("would dispatch", result["reason"])
        self.assertEqual(len(result["attempts"]), 2)
        for attempt in result["attempts"]:
            self.assertEqual(attempt["status"], "dry_run")

    @patch("agent_relay.orchestrator.adapter_dispatch")
    @patch("agent_relay.orchestrator.route_task_by_id")
    def test_auto_dispatch_mock_deepseek(self, mock_route, mock_adapter):
        """Mock mode passes through to adapter."""
        mock_adapter.return_value = {
            "status": "success",
            "run_id": "run-mock",
            "result": {"review_source": "mock", "summary": "Mock review"},
        }
        mock_route.return_value = {
            "primary": "deepseek",
            "fallbacks": ["codex"],
            "reviewers": [],
            "mode": "review",
            "reason": "review task",
            "task_id": "task-001",
            "title": "Review",
        }
        result = auto_dispatch_task("task-001", mock=True)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["selected_agent"], "deepseek")
        mock_adapter.assert_called_once_with(
            "task-001", "deepseek", mock=True, role="reviewer"
        )

    @patch(
        "agent_relay.orchestrator.adapter_dispatch",
        return_value={
            "status": "handoff",
            "run_id": "run-handoff",
            "result": {"instruction": "Open worktree in Codex"},
        },
    )
    @patch("agent_relay.orchestrator.route_task_by_id")
    def test_auto_dispatch_codex_human(self, mock_route, mock_adapter):
        """Human-in-loop codex dispatch returns handoff status."""
        mock_route.return_value = {
            "primary": "codex",
            "fallbacks": ["antigravity"],
            "reviewers": [],
            "mode": "handoff",
            "reason": "manual task",
            "task_id": "task-001",
            "title": "Manual config",
        }
        result = auto_dispatch_task("task-001")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["selected_agent"], "codex")
        self.assertEqual(result["attempts"][0]["status"], "handoff")

    @patch("agent_relay.orchestrator.route_task_by_id")
    def test_auto_dispatch_result_has_all_keys(self, mock_route):
        """Orchestration record must contain all required fields."""
        mock_route.return_value = {
            "primary": "claude",
            "fallbacks": [],
            "reviewers": [],
            "mode": "write",
            "reason": "test",
            "task_id": "task-001",
            "title": "Test",
        }
        result = auto_dispatch_task("task-001", dry_run=True)
        required = [
            "task_id",
            "route",
            "selected_agent",
            "attempts",
            "status",
            "reason",
        ]
        for key in required:
            self.assertIn(key, result, f"Missing required key: {key}")
        self.assertIn("executed_at", result)


class TestAutoDispatchWithGatewayAPI(unittest.TestCase):
    """Integration tests for POST /tasks/{id}/auto-dispatch via gateway."""

    @classmethod
    def setUpClass(cls):
        import threading
        import urllib.error
        import socket
        import importlib.util
        from http.server import HTTPServer

        os.environ["AGY_FLOW_TESTING"] = "1"
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name).resolve()

        # Import module
        spec = importlib.util.spec_from_file_location(
            "agent_relay_main", project_root / "agent-relay.py"
        )
        cls.mod = importlib.util.module_from_spec(spec)
        sys.modules["agent_relay_main"] = cls.mod
        spec.loader.exec_module(cls.mod)

        # Patch paths
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
            title = "Auto-dispatch test"
            agent = "codex"
            desc = "Testing auto-dispatch"

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

    def test_auto_dispatch_dry_run_via_gateway(self):
        status, data = self._fetch(
            "/tasks/task-001/auto-dispatch",
            method="POST",
            data=json.dumps({"dry_run": True}),
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "dry_run")
        self.assertIn("attempts", data)
        self.assertIn("route", data)
        self.assertIn("would dispatch", data.get("reason", ""))

    def test_auto_dispatch_mock_deepseek_via_gateway(self):
        status, data = self._fetch(
            "/tasks/task-001/auto-dispatch",
            method="POST",
            data=json.dumps({"mock": True, "dry_run": True}),
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "dry_run")

    def test_auto_dispatch_unknown_task(self):
        status, data = self._fetch(
            "/tasks/task-999/auto-dispatch",
            method="POST",
            data=json.dumps({"dry_run": True}),
        )
        self.assertEqual(status, 400)
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()
