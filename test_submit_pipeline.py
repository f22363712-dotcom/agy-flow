"""Tests for agy_flow/submit_pipeline.py — Submit Pipeline v1."""

from agy_flow.state_machine import set_task_state, get_task_state
from agy_flow.submit_pipeline import finalize_task
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


class TestSubmitPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name).resolve()
        import agy_flow.config

        agy_flow.config.update_paths(cls.temp_path)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def _mock_quality(self, ready=True, blocking=None, warnings=None):
        """Patch evaluate_task_quality to return a controlled response."""
        if blocking is None:
            blocking = [] if ready else ["Mock blocking issue"]
        if warnings is None:
            warnings = []
        return patch(
            "agy_flow.submit_pipeline.evaluate_task_quality",
            return_value={
                "task_id": "task-test",
                "state": "approved",
                "ready": ready,
                "blocking_issues": blocking,
                "warnings": warnings,
                "latest_writer_run": {"run_id": "r1"},
                "latest_reviewer_run": {"run_id": "r2"},
                "tests_run": ["pytest"],
                "files_touched": ["src/main.py"],
                "risks": [],
                "recommended_next_action": "submit",
            },
        )

    def test_dry_run_returns_dry_run(self):
        with self._mock_quality(ready=True):
            result = finalize_task("task-test", dry_run=True)
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse(result["submitted"])
        self.assertIn("quality", result)

    def test_dry_run_blocked_shows_reason(self):
        with self._mock_quality(ready=False, blocking=["Mock issue"]):
            result = finalize_task("task-test", dry_run=True)
        self.assertEqual(result["status"], "dry_run")
        self.assertIn("blocked", result["reason"].lower())

    def test_ready_false_blocks_finalize(self):
        with self._mock_quality(ready=False):
            result = finalize_task("task-test", dry_run=False)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["submitted"])

    def test_ready_true_submits_and_sets_state(self):
        set_task_state("task-test", "approved", reason="review ok")
        with self._mock_quality(ready=True):
            result = finalize_task("task-test", dry_run=False)
        self.assertEqual(result["status"], "submitted")
        self.assertTrue(result["submitted"])
        # Check state was updated
        state = get_task_state("task-test")
        self.assertEqual(state["state"], "submitted")

    def test_finalize_returns_quality_in_result(self):
        with self._mock_quality(ready=True):
            result = finalize_task("task-test", dry_run=True)
        self.assertIn("quality", result)
        self.assertIn("ready", result["quality"])
        self.assertIn("blocking_issues", result["quality"])

    def test_ready_true_submitted_false_if_error(self):
        """If an unexpected error occurs, status=failed is returned."""
        set_task_state("task-fail", "approved")
        with patch(
            "agy_flow.submit_pipeline.evaluate_task_quality",
            side_effect=Exception("Unexpected"),
        ):
            result = finalize_task("task-fail", dry_run=False)
        # The exception is caught and returned as failed
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["submitted"])

    def test_result_has_required_keys(self):
        with self._mock_quality(ready=True):
            result = finalize_task("task-test", dry_run=True)
        required = ["task_id", "status", "quality", "submitted", "reason"]
        for key in required:
            self.assertIn(key, result, f"Missing key: {key}")
        self.assertIn("executed_at", result)


class TestSubmitPipelineWithGatewayAPI(unittest.TestCase):
    """Integration tests for finalize via gateway."""

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
            title = "Submit pipeline test"
            agent = "codex"
            desc = "Testing submit pipeline"

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

    def test_finalize_api_dry_run(self):
        status, data = self._fetch(
            "/tasks/task-001/finalize",
            method="POST",
            data=json.dumps({"dry_run": True}),
        )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "dry_run")

    def test_finalize_api_no_body(self):
        status, data = self._fetch(
            "/tasks/task-001/finalize",
            method="POST",
            data=json.dumps({}),
        )
        self.assertEqual(status, 200)
        self.assertIn(data.get("status"), ("dry_run", "blocked"))


if __name__ == "__main__":
    unittest.main()
