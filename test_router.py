"""Tests for agy_flow/router.py — Capability-Aware Routing v1.

Uses mock connector availability so tests don't depend on real CLIs or
API keys.
"""

from agy_flow.errors import AgyFlowError
from agy_flow.router import route_task, route_task_by_id
import json
import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestCapabilityAwareRouting(unittest.TestCase):
    """Route selection based on mocked connector availability."""

    maxDiff = None

    def _mock_report(self, overrides=None):
        """Return a mock agents_report() dict.

        Default: deepseek=unavailable, claude=available, codex=available,
        antigravity=available, gemini=unavailable.
        """
        default = {
            "deepseek": {
                "name": "deepseek",
                "kind": "llm",
                "available": False,
                "reason": "No API key",
                "capabilities": ["review"],
                "supports_worktree": False,
                "supports_review": True,
                "supports_write": False,
            },
            "claude": {
                "name": "claude",
                "kind": "cli",
                "available": True,
                "reason": "claude CLI found",
                "capabilities": ["code_edit", "review"],
                "supports_worktree": True,
                "supports_review": True,
                "supports_write": True,
            },
            "codex": {
                "name": "codex",
                "kind": "human",
                "available": True,
                "reason": "human handoff",
                "capabilities": ["code_edit", "review"],
                "supports_worktree": True,
                "supports_review": True,
                "supports_write": True,
            },
            "antigravity": {
                "name": "antigravity",
                "kind": "desktop",
                "available": True,
                "reason": "desktop handoff",
                "capabilities": ["vision", "ui_review"],
                "supports_worktree": True,
                "supports_review": True,
                "supports_write": True,
            },
            "gemini": {
                "name": "gemini",
                "kind": "cli",
                "available": False,
                "reason": "gemini CLI not found",
                "capabilities": ["analysis"],
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

    @patch("agy_flow.router._get_agents_status")
    def test_write_routes_to_available_claude(self, mock_status):
        """Write task should route to claude when claude is available."""
        mock_status.return_value = self._mock_report()
        route = route_task("Implement user login API")
        self.assertEqual(route["primary"], "claude")
        self.assertEqual(route["mode"], "write")
        self.assertIn("codex", route["fallbacks"])
        self.assertIn("antigravity", route["fallbacks"])

    @patch("agy_flow.router._get_agents_status")
    def test_write_fallback_when_classifier_unavailable(self, mock_status):
        """If classifier-preferred agent is unavailable, fallback to next write-capable."""
        mock_status.return_value = self._mock_report(
            {
                "claude": {"available": False, "reason": "Not installed"},
            }
        )
        route = route_task("Implement user login API")
        # Should fallback to antigravity (next in write priority that is
        # available)
        self.assertIn(route["primary"], ["antigravity", "codex"])
        self.assertEqual(route["mode"], "write")

    @patch("agy_flow.router._get_agents_status")
    def test_write_all_unavailable_fallback_codex(self, mock_status):
        """When no write-capable agent is available, fallback to codex human."""
        mock_status.return_value = self._mock_report(
            {
                "claude": {"available": False},
                "antigravity": {"available": False},
            }
        )
        route = route_task("Fix button styling")
        self.assertEqual(route["primary"], "codex")
        self.assertIn("human", route["reason"].lower())

    @patch("agy_flow.router._get_agents_status")
    def test_review_deepseek_available(self, mock_status):
        """Review tasks should prefer deepseek when API key is set."""
        mock_status.return_value = self._mock_report(
            {
                "deepseek": {"available": True, "reason": "DEEPSEEK_API_KEY set"},
            }
        )
        route = route_task("Code Review", context={"mode": "review"})
        self.assertEqual(route["primary"], "deepseek")
        self.assertEqual(route["mode"], "review")

    @patch("agy_flow.router._get_agents_status")
    def test_review_deepseek_unavailable_fallback(self, mock_status):
        """Review tasks should fallback to claude when deepseek unavailable."""
        mock_status.return_value = self._mock_report()
        route = route_task("Code Review", context={"mode": "review"})
        self.assertEqual(route["primary"], "claude")
        self.assertEqual(route["mode"], "review")

    @patch("agy_flow.router._get_agents_status")
    def test_review_all_unavailable_fallback_codex(self, mock_status):
        """Review should fallback to codex when no review-capable CLI/LLM is available."""
        mock_status.return_value = self._mock_report(
            {
                "deepseek": {"available": False},
                "claude": {"available": False},
                "antigravity": {"available": False},
            }
        )
        route = route_task("Code Review", context={"mode": "review"})
        self.assertEqual(route["primary"], "codex")

    @patch("agy_flow.router._get_agents_status")
    def test_handoff_routes_to_codex(self, mock_status):
        """Handoff mode should prefer codex."""
        mock_status.return_value = self._mock_report()
        route = route_task("Manual DB config", context={"mode": "handoff"})
        self.assertEqual(route["primary"], "codex")
        self.assertEqual(route["mode"], "handoff")

    @patch("agy_flow.router._get_agents_status")
    def test_reviewers_include_all_review_capable(self, mock_status):
        """Reviewers list should contain all available review-capable agents except primary."""
        mock_status.return_value = self._mock_report(
            {
                "deepseek": {"available": True},
            }
        )
        route = route_task("Write unit tests")
        self.assertIn("codex", route["reviewers"])
        self.assertIn("antigravity", route["reviewers"])

    @patch("agy_flow.router._get_agents_status")
    def test_warnings_empty_when_all_available(self, mock_status):
        """When all relevant agents are available, warnings should be empty."""
        mock_status.return_value = self._mock_report(
            {
                "gemini": {"available": True},
            }
        )
        route = route_task("Implement login API")
        warnings_text = " ".join(route.get("capability_warnings", []))
        self.assertEqual(warnings_text, "")

    @patch("agy_flow.router._get_agents_status")
    def test_route_available_deepseek_routes_to_deepseek_for_review(self, mock_status):
        """Review mode should prefer deepseek when API key is set."""
        mock_status.return_value = self._mock_report(
            {
                "deepseek": {"available": True, "reason": "DEEPSEEK_API_KEY set"},
            }
        )
        route = route_task("Code Review", context={"mode": "review"})
        self.assertEqual(route["primary"], "deepseek")
        self.assertEqual(route["mode"], "review")

    @patch("agy_flow.router._get_agents_status")
    def test_route_output_contains_required_keys(self, mock_status):
        """Route result must have all required keys."""
        mock_status.return_value = self._mock_report()
        route = route_task("Any task")
        required = [
            "primary",
            "fallbacks",
            "reviewers",
            "mode",
            "reason",
            "capability_warnings",
            "task_type",
            "base_plan",
        ]
        for key in required:
            self.assertIn(key, route, f"Missing required key: {key}")

    @patch("agy_flow.router._get_agents_status")
    def test_route_task_by_id_no_board_raises(self, mock_status):
        """route_task_by_id should raise for non-existent tasks."""
        with patch("agy_flow.tasks.parse_board_rows", return_value=[]):
            with self.assertRaises(AgyFlowError):
                route_task_by_id("task-999")


class TestRouteWithGatewayAPI(unittest.TestCase):
    """Test the /route endpoint through the gateway.

    Uses the same temp-directory isolation pattern as test_serve.py.
    """

    @classmethod
    def setUpClass(cls):
        import importlib.util
        import threading
        import urllib.request
        import urllib.error
        import socket
        import tempfile
        from http.server import HTTPServer

        os.environ["AGY_FLOW_TESTING"] = "1"
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name).resolve()

        # Import the module
        spec = importlib.util.spec_from_file_location(
            "agy_flow_main", project_root / "agy-flow.py"
        )
        cls.mod = importlib.util.module_from_spec(spec)
        sys.modules["agy_flow_main"] = cls.mod
        spec.loader.exec_module(cls.mod)

        # Patch paths
        cls.old_root = cls.mod.PROJECT_ROOT
        cls.mod.PROJECT_ROOT = cls.temp_path
        cls.mod.AGENTS_DIR = cls.temp_path / ".agents"
        cls.mod.TASKS_DIR = cls.mod.AGENTS_DIR / "tasks"
        cls.mod.BOARD_FILE = cls.mod.TASKS_DIR / "board.md"

        import agy_flow.config

        agy_flow.config.update_paths(cls.temp_path)

        import agy_flow.git_ops

        cls.old_git_root = agy_flow.git_ops.PROJECT_ROOT
        agy_flow.git_ops.PROJECT_ROOT = cls.temp_path

        # Init
        class DummyArgs:
            pass

        cls.mod.init_project(DummyArgs())

        # Fix worktrees_dir
        config_path = cls.temp_path / ".agents" / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            cfg["worktrees_dir"] = str(cls.temp_path / "worktrees")
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

        # Create a task
        class DummyCreateArgs:
            title = "Test task for routing"
            agent = "codex"
            desc = "Testing route endpoint"

        cls.mod.create_task(DummyCreateArgs())

        # Start server
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

        import agy_flow.config

        agy_flow.config.update_paths(cls.old_root)

        import agy_flow.git_ops

        agy_flow.git_ops.PROJECT_ROOT = cls.old_git_root

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

    def test_post_route_endpoint(self):
        status, data = self._fetch(
            "/route", method="POST", data=json.dumps({"title": "Design login page"})
        )
        self.assertEqual(status, 200)
        self.assertIn("primary", data)
        self.assertIn("fallbacks", data)
        self.assertIn("reviewers", data)
        self.assertIn("mode", data)

    def test_post_route_missing_title(self):
        status, data = self._fetch("/route", method="POST", data=json.dumps({}))
        self.assertEqual(status, 400)

    def test_task_route_endpoint(self):
        status, data = self._fetch("/tasks/task-001/route")
        self.assertEqual(status, 200)
        self.assertEqual(data.get("task_id"), "task-001")
        self.assertIn("primary", data)
        self.assertIn("fallbacks", data)
        self.assertIn("reviewers", data)
        self.assertIn("mode", data)
        self.assertIn("board_status", data)

    def test_task_route_unknown_task(self):
        status, data = self._fetch("/tasks/task-999/route")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
