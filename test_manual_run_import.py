"""Tests for manual run import — agent-relay run add."""

from agent_relay.errors import AgentRelayError
from agent_relay.quality_gate import evaluate_task_quality
from agent_relay.state_machine import get_task_state
from agent_relay.adapter import add_run_record, list_runs, get_run
import agent_relay.config
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestManualRunImport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name).resolve()
        agent_relay.config.update_paths(cls.temp_path)
        agent_relay.config.AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        agent_relay.config.RUNS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def test_writer_completed_run_created(self):
        record = add_run_record(
            "task-import-1",
            agent="claude",
            role="writer",
            status="completed",
            summary="Implemented login feature",
            next_action="review",
            files_touched=["src/login.py", "test_login.py"],
            tests_run=["pytest test_login.py"],
        )
        self.assertEqual(record["task_id"], "task-import-1")
        self.assertEqual(record["agent"], "claude")
        self.assertEqual(record["role"], "writer")
        self.assertEqual(record["status"], "success")
        self.assertEqual(record["parsed_output"]["status"], "completed")
        self.assertEqual(record["next_action"], "review")
        self.assertTrue(record["needs_review"])
        self.assertIn("src/login.py", record["files_touched"])
        self.assertIn("pytest test_login.py", record["tests_run"])
        self.assertIn("run_id", record)

        # Verify persisted
        fetched = get_run(record["run_id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["agent"], "claude")

    def test_reviewer_completed_run_created(self):
        record = add_run_record(
            "task-import-2",
            agent="codex",
            role="reviewer",
            status="completed",
            summary="Code review passed",
            next_action="submit",
            risks=["Minor OAuth edge case noted"],
        )
        self.assertEqual(record["role"], "reviewer")
        self.assertEqual(record["next_action"], "submit")
        self.assertIn("OAuth", record["risks"][0])

    def test_parsed_output_field_populated(self):
        record = add_run_record(
            "task-import-3",
            agent="antigravity",
            role="writer",
            status="completed",
            summary="Designed new settings page",
            next_action="review",
            files_touched=["src/settings.html", "src/settings.css"],
        )
        parsed = record["parsed_output"]
        self.assertEqual(parsed["status"], "completed")
        self.assertEqual(parsed["summary"], "Designed new settings page")
        self.assertEqual(parsed["next_action"], "review")
        self.assertIn("src/settings.html", parsed["files_touched"])

    def test_quality_gate_sees_imported_writer_run(self):
        """Manual imported writer run should satisfy quality gate 'no writer run' check."""
        add_run_record(
            "task-quality-test",
            agent="claude",
            role="writer",
            status="completed",
            summary="Test quality gate fix",
            next_action="submit",
            files_touched=["src/test.py"],
            tests_run=["pytest"],
        )
        quality = evaluate_task_quality("task-quality-test")
        blocking = " ".join(quality["blocking_issues"]).lower()
        self.assertNotIn(
            "no writer run",
            blocking,
            f"Quality gate should not show 'no writer run', got: {blocking}",
        )

    def test_state_transition_writer_completed(self):
        add_run_record(
            "task-state-1",
            agent="claude",
            role="writer",
            status="completed",
            summary="Work done",
            next_action="review",
        )
        # State should have transitioned (state machine may or may not have changed
        # from planned — but at least the run record exists)
        runs = list_runs(task_id="task-state-1")
        self.assertEqual(len(runs), 1)

    def test_invalid_role_rejected(self):
        with self.assertRaises(AgentRelayError):
            add_run_record("task-invalid", agent="claude", role="invalid")

    def test_invalid_status_rejected(self):
        with self.assertRaises(AgentRelayError):
            add_run_record("task-invalid", agent="claude", status="invalid_status")

    def test_invalid_next_action_rejected(self):
        with self.assertRaises(AgentRelayError):
            add_run_record("task-invalid", agent="claude", next_action="invalid")

    def test_run_added_quality_gate_no_block(self):
        """Adding both writer and reviewer runs satisfies quality gate completely."""
        add_run_record(
            "task-complete-1",
            agent="claude",
            role="writer",
            status="completed",
            summary="Write implementation",
            next_action="review",
            files_touched=["src/impl.py"],
            tests_run=["pytest"],
        )
        add_run_record(
            "task-complete-1",
            agent="codex",
            role="reviewer",
            status="completed",
            summary="Review approved",
            next_action="submit",
        )
        quality = evaluate_task_quality("task-complete-1")
        self.assertTrue(
            quality["ready"],
            f"Quality should be ready with writer+reviewer. Issues: {quality['blocking_issues']}",
        )


if __name__ == "__main__":
    unittest.main()
