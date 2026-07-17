"""Tests for agy_flow/connectors.py — Agent Connector v0.

All tests mock PATH / environment variables so no real CLI or API keys
are required.
"""

from agy_flow.errors import AgyFlowError
from agy_flow.connectors import (
    DeepSeekConnector,
    ClaudeConnector,
    CodexConnector,
    AntigravityConnector,
    GeminiConnector,
    get_connector,
    get_all_connectors,
    probe_agent,
    probe_all,
    agents_report,
)
import json
import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestConnectorUnit(unittest.TestCase):
    """Unit tests for individual connectors with mocked environment."""

    def setUp(self):
        self._old_env = {}
        for k in ("DEEPSEEK_API_KEY", "LITELLM_API_KEY"):
            self._old_env[k] = os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._old_env.items():
            if v is not None:
                os.environ[k] = v
            elif k in os.environ:
                del os.environ[k]

    # ------------------------------------------------------------------
    # DeepSeek
    # ------------------------------------------------------------------

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=False)
    def test_deepseek_available_with_key(self):
        c = DeepSeekConnector()
        result = c.is_available()
        self.assertTrue(result["available"])
        self.assertIn("DEEPSEEK_API_KEY", result["reason"])

    @patch.dict(os.environ, {"LITELLM_API_KEY": "lt-test"}, clear=False)
    def test_deepseek_available_with_litellm_key(self):
        c = DeepSeekConnector()
        result = c.is_available()
        self.assertTrue(result["available"])
        self.assertIn("LITELLM_API_KEY", result["reason"])

    def test_deepseek_unavailable_without_key(self):
        c = DeepSeekConnector()
        result = c.is_available()
        self.assertFalse(result["available"])
        self.assertIn("API_KEY", result["reason"])

    def test_deepseek_kind(self):
        self.assertEqual(DeepSeekConnector().kind, "llm")

    # ------------------------------------------------------------------
    # Claude
    # ------------------------------------------------------------------

    @patch("shutil.which", return_value="/usr/bin/claude")
    def test_claude_available(self, mock_which):
        c = ClaudeConnector()
        result = c.is_available()
        self.assertTrue(result["available"])
        self.assertIn("found", result["reason"])

    @patch("shutil.which", return_value=None)
    def test_claude_unavailable(self, mock_which):
        c = ClaudeConnector()
        result = c.is_available()
        self.assertFalse(result["available"])
        self.assertIn("not found", result["reason"])

    def test_claude_kind(self):
        self.assertEqual(ClaudeConnector().kind, "cli")

    # ------------------------------------------------------------------
    # Codex
    # ------------------------------------------------------------------

    @patch("shutil.which", return_value="/usr/bin/codex")
    def test_codex_available(self, mock_which):
        c = CodexConnector()
        result = c.is_available()
        self.assertTrue(result["available"])

    @patch("shutil.which", return_value=None)
    def test_codex_fallback_available(self, mock_which):
        """Codex is always available via human handoff."""
        c = CodexConnector()
        result = c.is_available()
        self.assertTrue(result["available"])
        self.assertIn("human-in-loop", result["reason"])

    def test_codex_kind(self):
        self.assertEqual(CodexConnector().kind, "human")

    # ------------------------------------------------------------------
    # Antigravity
    # ------------------------------------------------------------------

    @patch("shutil.which", return_value=None)
    def test_antigravity_available_desktop(self, mock_which):
        """Antigravity is always available via desktop handoff."""
        c = AntigravityConnector()
        result = c.is_available()
        self.assertTrue(result["available"])
        self.assertIn("desktop", result["reason"])

    def test_antigravity_kind(self):
        self.assertEqual(AntigravityConnector().kind, "desktop")

    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------

    @patch("shutil.which", return_value="/usr/bin/gemini")
    def test_gemini_available(self, mock_which):
        c = GeminiConnector()
        result = c.is_available()
        self.assertTrue(result["available"])

    @patch("shutil.which", return_value=None)
    def test_gemini_unavailable(self, mock_which):
        c = GeminiConnector()
        result = c.is_available()
        self.assertFalse(result["available"])

    def test_gemini_kind(self):
        self.assertEqual(GeminiConnector().kind, "cli")

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    def test_get_connector_registered(self):
        self.assertIsInstance(get_connector("deepseek"), DeepSeekConnector)
        self.assertIsInstance(get_connector("claude"), ClaudeConnector)
        self.assertIsInstance(get_connector("codex"), CodexConnector)
        self.assertIsInstance(get_connector("antigravity"), AntigravityConnector)
        self.assertIsInstance(get_connector("gemini"), GeminiConnector)

    def test_get_connector_invalid(self):
        with self.assertRaises(AgyFlowError):
            get_connector("nonexistent")

    def test_get_all_connectors(self):
        all_c = get_all_connectors()
        self.assertIn("deepseek", all_c)
        self.assertIn("claude", all_c)
        self.assertEqual(len(all_c), 5)

    # ------------------------------------------------------------------
    # Probe utilities
    # ------------------------------------------------------------------

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=False)
    def test_probe_agent_deepseek(self):
        result = probe_agent("deepseek")
        self.assertEqual(result["name"], "deepseek")
        self.assertEqual(result["kind"], "llm")
        self.assertTrue(result["available"])
        self.assertIn("capabilities", result)
        self.assertIn("supports_worktree", result)
        self.assertIn("supports_review", result)
        self.assertIn("supports_write", result)

    @patch("shutil.which", return_value=None)
    def test_probe_agent_claude_unavailable(self, mock_which):
        result = probe_agent("claude")
        self.assertEqual(result["name"], "claude")
        self.assertFalse(result["available"])
        self.assertIn("not found", result["reason"])

    def test_probe_all(self):
        results = probe_all()
        names = [r["name"] for r in results]
        self.assertIn("deepseek", names)
        self.assertIn("claude", names)
        self.assertIn("codex", names)
        self.assertIn("antigravity", names)
        self.assertIn("gemini", names)
        for r in results:
            self.assertIn("name", r)
            self.assertIn("kind", r)
            self.assertIn("available", r)
            self.assertIn("reason", r)

    def test_agents_report_returns_dict(self):
        """agents_report must return a dict keyed by agent name."""
        report = agents_report()
        self.assertIsInstance(report, dict)
        self.assertIn("deepseek", report)
        self.assertIn("claude", report)
        for name, info in report.items():
            self.assertIn("available", info)
            self.assertIn("reason", info)
            self.assertIn("kind", info)
            self.assertIn("capabilities", info)


class TestConnectorCapabilities(unittest.TestCase):
    """Test capabilities metadata across all built-in connectors."""

    def test_all_have_capabilities(self):
        from agy_flow.connectors import AGENT_META

        for name in ("deepseek", "claude", "codex", "antigravity", "gemini"):
            self.assertIn(name, AGENT_META)
            meta = AGENT_META[name]
            self.assertIn("kind", meta, f"{name} missing kind")
            self.assertIn("capabilities", meta, f"{name} missing capabilities")
            self.assertIsInstance(meta["capabilities"], list)

    def test_prepare_dispatch(self):
        c = DeepSeekConnector()
        result = c.prepare_dispatch("task-001", role="reviewer")
        self.assertEqual(result["connector"], "deepseek")
        self.assertEqual(result["task_id"], "task-001")
        self.assertEqual(result["role"], "reviewer")
        self.assertIn("available", result)

    def test_capabilities_method(self):
        c = ClaudeConnector()
        caps = c.capabilities()
        self.assertIsInstance(caps, list)
        self.assertGreater(len(caps), 0)


if __name__ == "__main__":
    unittest.main()
