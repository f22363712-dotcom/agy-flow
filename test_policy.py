"""Tests for agy_flow/policy.py — Policy Guard v1."""

from agy_flow.errors import AgyFlowError
from agy_flow.state_machine import set_task_state
from agy_flow.policy import can_dispatch, can_continue, get_policy_info
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


class TestPolicyGuard(unittest.TestCase):
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

    def setUp(self):
        # Reset task state to planned for each test
        set_task_state("task-policy", "planned", reason="test init")

    def test_can_dispatch_planned(self):
        result = can_dispatch("task-policy", "claude")
        self.assertTrue(result["allowed"])

    def test_cannot_dispatch_blocked(self):
        set_task_state("task-policy", "blocked", reason="blocked")
        result = can_dispatch("task-policy", "claude")
        self.assertFalse(result["allowed"])

    def test_cannot_dispatch_done(self):
        set_task_state("task-policy", "done", reason="done")
        result = can_dispatch("task-policy", "claude")
        self.assertFalse(result["allowed"])

    def test_cannot_dispatch_submitted(self):
        set_task_state("task-policy", "submitted", reason="done")
        result = can_dispatch("task-policy", "claude")
        self.assertFalse(result["allowed"])

    def test_approved_has_warning(self):
        set_task_state("task-policy", "approved", reason="review ok")
        result = can_dispatch("task-policy", "claude")
        self.assertTrue(result["allowed"])
        self.assertTrue(len(result.get("warnings", [])) > 0)

    @patch(
        "agy_flow.policy.list_runs",
        return_value=[{"run_id": "r1"}, {"run_id": "r2"}, {"run_id": "r3"}],
    )
    def test_max_loop_blocks_dispatch(self, mock_runs):
        result = can_dispatch("task-policy", "codex", role="reviewer")
        self.assertFalse(result["allowed"])
        self.assertIn("max", result["reason"].lower())

    def test_can_continue_blocked_state(self):
        set_task_state("task-policy", "blocked", reason="blocked")
        with patch(
            "agy_flow.policy.get_run",
            return_value={
                "run_id": "r1",
                "task_id": "task-policy",
                "agent": "claude",
                "role": "writer",
                "parsed_output": {"status": "completed", "next_action": "review"},
            },
        ):
            result = can_continue("r1")
            self.assertFalse(result["allowed"])

    def test_can_continue_blocked_parsed(self):
        with patch(
            "agy_flow.policy.get_run",
            return_value={
                "run_id": "r1",
                "task_id": "task-policy",
                "agent": "claude",
                "role": "writer",
                "parsed_output": {"status": "blocked", "next_action": "manual"},
            },
        ):
            result = can_continue("r1")
            self.assertFalse(result["allowed"])

    def test_can_continue_non_writer(self):
        with patch(
            "agy_flow.policy.get_run",
            return_value={
                "run_id": "r1",
                "task_id": "task-policy",
                "agent": "claude",
                "role": "reviewer",
                "parsed_output": {"status": "completed", "next_action": "review"},
            },
        ):
            result = can_continue("r1")
            self.assertFalse(result["allowed"])

    def test_can_continue_allowed(self):
        with patch(
            "agy_flow.policy.get_run",
            return_value={
                "run_id": "r1",
                "task_id": "task-policy",
                "agent": "claude",
                "role": "writer",
                "parsed_output": {"status": "completed", "next_action": "review"},
            },
        ):
            with patch("agy_flow.policy.list_runs", return_value=[{"run_id": "r1"}]):
                result = can_continue("r1")
                self.assertTrue(result["allowed"])

    def test_get_policy_info_returns_keys(self):
        info = get_policy_info("task-policy")
        self.assertIn("task_id", info)
        self.assertIn("state", info)
        self.assertIn("run_count", info)
        self.assertIn("max_auto_loop", info)
        self.assertIn("can_dispatch_new", info)

    def test_can_continue_missing_run(self):
        with patch("agy_flow.policy.get_run", return_value=None):
            result = can_continue("run-nonexistent")
            self.assertFalse(result["allowed"])


if __name__ == "__main__":
    unittest.main()
