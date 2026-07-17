"""Tests for agy_flow/executors.py — CLI Agent Execution v1.

All subprocess calls are mocked so no real CLI is required.
"""

from agy_flow.errors import AgyFlowError
from agy_flow.executors import run_cli_agent, build_agent_prompt
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


class TestRunCliAgent(unittest.TestCase):
    """Test run_cli_agent with mocked subprocess.run."""

    @patch("agy_flow.executors.shutil.which", return_value="/usr/bin/claude")
    @patch("agy_flow.executors.subprocess.run")
    def test_success(self, mock_run, mock_which):
        """Success path returns stdout and status=success."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Task complete.", stderr="", args=[]
        )
        result = run_cli_agent(
            "claude", ["claude", "-p", "do the thing"], "do the thing"
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["stdout"], "Task complete.")
        self.assertGreaterEqual(result["duration_ms"], 0)
        self.assertTrue(result["stderr"] is not None or result["stderr"] == "")
        self.assertEqual(result["error"], "")

    @patch("agy_flow.executors.shutil.which", return_value=None)
    def test_command_not_found(self, mock_which):
        """When the CLI binary is not on PATH, return unavailable."""
        result = run_cli_agent("claude", ["claude", "-p", "hi"], "hi")
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["returncode"])
        self.assertIn("not found", result["error"])

    @patch("agy_flow.executors.shutil.which", return_value="/usr/bin/claude")
    @patch("agy_flow.executors.subprocess.run")
    def test_nonzero_returncode(self, mock_run, mock_which):
        """Non-zero return code yields status=error with stderr."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Error: file not found", args=[]
        )
        result = run_cli_agent("claude", ["claude", "-p", "test"], "test")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["returncode"], 1)
        self.assertIn("file not found", result["error"])

    @patch("agy_flow.executors.shutil.which", return_value="/usr/bin/claude")
    @patch("agy_flow.executors.subprocess.run")
    def test_timeout(self, mock_run, mock_which):
        """Timeout should return status=timeout."""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=5)

        result = run_cli_agent("claude", ["claude", "-p", "slow"], "slow", timeout=5)
        self.assertEqual(result["status"], "timeout")
        self.assertIn("timed out", result["error"])

    @patch("agy_flow.executors.shutil.which", return_value="/usr/bin/claude")
    @patch("agy_flow.executors.subprocess.run")
    def test_stderr_stdout_in_result(self, mock_run, mock_which):
        """Both stdout and stderr should be captured in the result."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Main output line\nAnother line",
            stderr="Warning: deprecation",
            args=[],
        )
        result = run_cli_agent("claude", ["claude", "-p", "go"], "go")
        self.assertIn("Main output", result["stdout"])
        self.assertIn("deprecation", result["stderr"])

    @patch("agy_flow.executors.shutil.which", return_value="/usr/bin/claude")
    @patch("agy_flow.executors.subprocess.run")
    def test_duration_ms_nonzero(self, mock_run, mock_which):
        """duration_ms should be > 0 for a successful run."""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="", args=[])
        result = run_cli_agent("claude", ["claude", "-p", "go"], "go")
        self.assertGreaterEqual(result["duration_ms"], 0)
        self.assertIn("ok", result["stdout"])


class TestBuildAgentPrompt(unittest.TestCase):
    """Test the prompt construction."""

    def test_basic_prompt_writer(self):
        prompt = build_agent_prompt(
            task_id="task-001",
            title="Test task",
            role="writer",
        )
        self.assertIn("task-001", prompt)
        self.assertIn("Test task", prompt)
        self.assertIn("writer", prompt)
        self.assertIn("worktree", prompt)
        self.assertIn("agy-flow submit task-001", prompt)

    def test_basic_prompt_reviewer(self):
        prompt = build_agent_prompt(
            task_id="task-002",
            title="Code review",
            role="reviewer",
        )
        self.assertIn("reviewer", prompt)
        self.assertIn("must NOT modify files", prompt)

    def test_prompt_includes_spec(self):
        prompt = build_agent_prompt(
            task_id="task-003",
            title="With spec",
            task_spec="## Requirements\n- Item 1\n- Item 2",
            role="writer",
        )
        self.assertIn("Item 1", prompt)
        self.assertIn("Requirements", prompt)

    def test_prompt_includes_plan(self):
        prompt = build_agent_prompt(
            task_id="task-004",
            title="With plan",
            plan_text='{"pipeline": ["claude", "deepseek"]}',
            role="reviewer",
        )
        self.assertIn("pipeline", prompt)

    def test_prompt_includes_route(self):
        route = {"task_id": "task-005", "role": "reviewer", "agent": "deepseek"}
        prompt = build_agent_prompt(
            task_id="task-005",
            title="Route test",
            route=route,
            role="reviewer",
        )
        self.assertIn("task-005", prompt)
        self.assertIn("deepseek", prompt)

    def test_prompt_contains_literal_task_id(self):
        """The prompt includes the task_id literally (no shell=True, so safe)."""
        prompt = build_agent_prompt(
            task_id="task-012",
            title="Safe literal",
            role="writer",
        )
        self.assertIn("task-012", prompt)
        self.assertIn("Safe literal", prompt)
        self.assertNotIn("shell=True", prompt)
        self.assertNotIn("subprocess", prompt)


class TestCliAgentAdapterWithGateway(unittest.TestCase):
    """Integration test for CliAgentAdapter via the gateway dispatch endpoint.

    Uses temp directory isolation.
    """

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

        spec = importlib.util.spec_from_file_location(
            "agy_flow_main", project_root / "agy-flow.py"
        )
        cls.mod = importlib.util.module_from_spec(spec)
        sys.modules["agy_flow_main"] = cls.mod
        spec.loader.exec_module(cls.mod)

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

        class DummyArgs:
            pass

        cls.mod.init_project(DummyArgs())

        config_path = cls.temp_path / ".agents" / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            cfg["worktrees_dir"] = str(cls.temp_path / "worktrees")
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

        class DummyCreateArgs:
            title = "Executor test"
            agent = "codex"
            desc = "Testing CLI executor"

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

    def test_dispatch_claude_unavailable(self):
        """Dispatching to claude when CLI is not installed should return unavailable."""
        status, data = self._fetch(
            "/tasks/task-001/dispatch",
            method="POST",
            data=json.dumps({"agent": "claude"}),
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "unavailable")
        self.assertIn("not found", data.get("error", ""))
        self.assertEqual(data.get("agent"), "claude")
        self.assertIn("run_id", data)

    def test_dispatch_gemini_unavailable(self):
        """Dispatching to gemini unavailable should not crash."""
        status, data = self._fetch(
            "/tasks/task-001/dispatch",
            method="POST",
            data=json.dumps({"agent": "gemini"}),
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "unavailable")


if __name__ == "__main__":
    unittest.main()
