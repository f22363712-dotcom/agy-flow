"""Tests for agent_relay/review_loop.py — Review Loop v1.

Uses mocked adapter dispatch to avoid real CLI/API calls.
"""

from agent_relay.errors import AgentRelayError
from agent_relay.review_loop import continue_after_run
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def _make_run(
    parsed_status="completed",
    next_action="review",
    agent="claude",
    task_id="task-001",
    run_id="run-test",
):
    """Helper: build a fake run record."""
    return {
        "run_id": run_id,
        "task_id": task_id,
        "agent": agent,
        "role": "writer",
        "status": "success",
        "parsed_output": {
            "status": parsed_status,
            "summary": "Done.",
            "next_action": next_action,
        },
        "result": {},
    }


class TestReviewLoop(unittest.TestCase):
    # Patch review_loop.get_run and the adapter dispatch
    @patch("agent_relay.review_loop.get_run")
    @patch("agent_relay.review_loop.adapter_dispatch")
    @patch("agent_relay.review_loop.route_task_by_id")
    def test_completed_dispatches_reviewer(self, mock_route, mock_dispatch, mock_get):
        """completed status should dispatch a reviewer."""
        mock_get.return_value = _make_run("completed", "review")
        mock_route.return_value = {
            "reviewers": ["codex", "antigravity"],
            "primary": "claude",
        }
        mock_dispatch.return_value = {
            "status": "success",
            "run_id": "run-review",
            "agent": "codex",
        }

        result = continue_after_run("run-test")
        self.assertEqual(result["status"], "continued")
        self.assertEqual(result["selected_reviewer"], "codex")
        self.assertEqual(result["previous_agent"], "claude")
        self.assertIn("review_run", result)
        mock_dispatch.assert_called_once()

    @patch("agent_relay.review_loop.get_run")
    @patch("agent_relay.review_loop.adapter_dispatch")
    @patch("agent_relay.review_loop.route_task_by_id")
    def test_needs_review_dispatches_reviewer(
        self, mock_route, mock_dispatch, mock_get
    ):
        """needs_review status should dispatch a reviewer."""
        mock_get.return_value = _make_run("needs_review", "review")
        mock_route.return_value = {
            "reviewers": ["antigravity", "codex"],
            "primary": "claude",
        }
        mock_dispatch.return_value = {
            "status": "handoff",
            "run_id": "run-review2",
            "agent": "antigravity",
        }

        result = continue_after_run("run-test")
        self.assertEqual(result["status"], "continued")
        self.assertEqual(result["selected_reviewer"], "antigravity")

    @patch("agent_relay.review_loop.get_run")
    def test_blocked_does_not_continue(self, mock_get):
        mock_get.return_value = _make_run("blocked", "manual")
        result = continue_after_run("run-test")
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["selected_reviewer"])

    @patch("agent_relay.review_loop.get_run")
    def test_failed_does_not_continue(self, mock_get):
        mock_get.return_value = _make_run("failed", "manual")
        result = continue_after_run("run-test")
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["selected_reviewer"])

    @patch("agent_relay.review_loop.get_run")
    def test_no_action_no_review(self, mock_get):
        mock_get.return_value = _make_run("completed", "submit")
        result = continue_after_run("run-test")
        self.assertEqual(result["status"], "no_action")
        self.assertIsNone(result["selected_reviewer"])

    def test_missing_run_raises(self):
        with patch("agent_relay.review_loop.get_run", return_value=None):
            with self.assertRaises(AgentRelayError):
                continue_after_run("run-nonexistent")

    @patch("agent_relay.review_loop.get_run")
    @patch("agent_relay.review_loop.adapter_dispatch")
    @patch("agent_relay.review_loop.route_task_by_id")
    def test_reviewer_not_writer(self, mock_route, mock_dispatch, mock_get):
        """Reviewer must not be the same agent as the writer."""
        mock_get.return_value = _make_run("completed", "review", agent="codex")
        mock_route.return_value = {
            "reviewers": ["codex", "antigravity"],
            "primary": "codex",
        }
        mock_dispatch.return_value = {
            "status": "handoff",
            "run_id": "run-review3",
            "agent": "antigravity",
        }

        result = continue_after_run("run-test")
        self.assertEqual(result["selected_reviewer"], "antigravity")
        self.assertNotEqual(result["selected_reviewer"], "codex")

    @patch("agent_relay.review_loop.get_run")
    @patch("agent_relay.review_loop.adapter_dispatch")
    @patch("agent_relay.review_loop.route_task_by_id")
    def test_deepseek_mock_reviewer_available(
        self, mock_route, mock_dispatch, mock_get
    ):
        """DeepSeek mock review should be available as reviewer."""
        mock_get.return_value = _make_run("completed", "review", agent="claude")
        mock_route.return_value = {
            "reviewers": ["deepseek", "codex"],
            "primary": "claude",
        }
        mock_dispatch.return_value = {
            "status": "success",
            "run_id": "run-ds-review",
            "agent": "deepseek",
        }

        result = continue_after_run("run-test", mock=True)
        self.assertEqual(result["selected_reviewer"], "deepseek")
        mock_dispatch.assert_called_once()
        # Check mock was passed through
        args, kwargs = mock_dispatch.call_args
        self.assertIn("mock", kwargs)
        self.assertTrue(kwargs["mock"])

    @patch("agent_relay.review_loop.get_run")
    @patch("agent_relay.review_loop.adapter_dispatch")
    @patch("agent_relay.review_loop.route_task_by_id")
    def test_codex_reviewer_handoff(self, mock_route, mock_dispatch, mock_get):
        """Codex reviewer dispatch should return handoff, not launch GUI."""
        mock_get.return_value = _make_run("completed", "review", agent="claude")
        mock_route.return_value = {
            "reviewers": ["codex"],
            "primary": "claude",
        }
        mock_dispatch.return_value = {
            "status": "handoff",
            "run_id": "run-codex-review",
            "agent": "codex",
            "result": {"instruction": "Handoff to Codex"},
        }

        result = continue_after_run("run-test")
        self.assertEqual(result["selected_reviewer"], "codex")
        self.assertEqual(result["status"], "continued")


if __name__ == "__main__":
    unittest.main()
