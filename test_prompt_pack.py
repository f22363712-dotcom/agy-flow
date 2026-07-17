"""Tests for agent_relay/prompt_pack.py — Handoff Prompt Pack."""

from agent_relay.errors import AgentRelayError
from agent_relay.prompt_pack import build_handoff_prompt
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestHandoffPrompt(unittest.TestCase):
    @patch("agent_relay.prompt_pack.whoami")
    @patch("agent_relay.prompt_pack.get_task_state")
    @patch("agent_relay.prompt_pack.list_runs")
    @patch("agent_relay.prompt_pack.evaluate_task_quality")
    def test_prompt_contains_guard_info(
        self, mock_quality, mock_runs, mock_state, mock_whoami
    ):
        mock_whoami.return_value = {
            "writer": "claude",
            "reviewers": ["Codex", "antigravity"],
            "role": "writer",
            "mode": "handoff",
        }
        mock_state.return_value = {"state": "approved"}
        mock_runs.return_value = []
        mock_quality.return_value = {
            "ready": True,
            "blocking_issues": [],
            "warnings": [],
        }

        result = build_handoff_prompt("codex")
        prompt = result["prompt"]
        self.assertIn("claude", prompt)
        self.assertIn("Codex", prompt)
        self.assertIn("antigravity", prompt)

    @patch("agent_relay.prompt_pack.whoami")
    @patch("agent_relay.prompt_pack.get_task_state")
    @patch("agent_relay.prompt_pack.list_runs")
    @patch("agent_relay.prompt_pack.evaluate_task_quality")
    def test_prompt_contains_objective(
        self, mock_quality, mock_runs, mock_state, mock_whoami
    ):
        mock_whoami.return_value = {"writer": "claude", "reviewers": []}
        mock_state.return_value = {"state": "approved"}
        mock_runs.return_value = []
        mock_quality.return_value = {"ready": True}

        result = build_handoff_prompt("codex", objective="Add dark mode toggle")
        self.assertIn("dark mode toggle", result["prompt"])

    @patch("agent_relay.prompt_pack.whoami")
    @patch("agent_relay.prompt_pack.get_task_state")
    @patch("agent_relay.prompt_pack.list_runs")
    @patch("agent_relay.prompt_pack.evaluate_task_quality")
    def test_prompt_contains_safety_constraints(
        self, mock_quality, mock_runs, mock_state, mock_whoami
    ):
        mock_whoami.return_value = {"writer": "claude", "reviewers": []}
        mock_state.return_value = {"state": "approved"}
        mock_runs.return_value = []
        mock_quality.return_value = {"ready": True}

        result = build_handoff_prompt("claude")
        prompt = result["prompt"]
        self.assertIn("API keys", prompt)
        self.assertIn("GUI", prompt)
        self.assertIn("worktree", prompt)

    @patch("agent_relay.prompt_pack.whoami")
    @patch("agent_relay.prompt_pack.get_task_state")
    @patch("agent_relay.prompt_pack.list_runs")
    @patch("agent_relay.prompt_pack.evaluate_task_quality")
    def test_prompt_has_agent_specific_instructions(
        self, mock_quality, mock_runs, mock_state, mock_whoami
    ):
        mock_whoami.return_value = {"writer": "claude", "reviewers": []}
        mock_state.return_value = {"state": "approved"}
        mock_runs.return_value = []
        mock_quality.return_value = {"ready": True}

        result = build_handoff_prompt("claude")
        self.assertIn("claude", result["prompt"])

        result2 = build_handoff_prompt("codex")
        self.assertIn("VS Code", result2["prompt"])

    @patch("agent_relay.prompt_pack.whoami")
    @patch("agent_relay.prompt_pack.get_task_state")
    @patch("agent_relay.prompt_pack.list_runs")
    @patch("agent_relay.prompt_pack.evaluate_task_quality")
    def test_result_has_all_keys(
        self, mock_quality, mock_runs, mock_state, mock_whoami
    ):
        mock_whoami.return_value = {"writer": "claude", "reviewers": []}
        mock_state.return_value = {"state": "approved"}
        mock_runs.return_value = []
        mock_quality.return_value = {"ready": True}

        result = build_handoff_prompt("antigravity")
        self.assertIn("target_agent", result)
        self.assertIn("prompt", result)
        self.assertIn("context_files", result)
        self.assertIn("warnings", result)

    def test_unknown_agent_raises(self):
        with self.assertRaises(AgentRelayError):
            build_handoff_prompt("nonexistent")


if __name__ == "__main__":
    unittest.main()
