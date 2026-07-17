"""Tests for agy_flow/trial_recorder.py — Value Trial Recorder."""

from agy_flow.errors import AgyFlowError
from agy_flow.trial_recorder import trial_start, trial_event, trial_stop, trial_export
import agy_flow.config
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestTrialRecorder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name).resolve()
        agy_flow.config.update_paths(cls.temp_path)
        agy_flow.config.AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def test_start_creates_trial(self):
        record = trial_start("test-trial", task_title="Test task", track="agy-flow")
        self.assertEqual(record["trial_id"], "test-trial")
        self.assertEqual(record["track"], "track_b")
        self.assertIsNotNone(record["started_at"])
        self.assertIsNone(record["ended_at"])
        self.assertIn("counters", record)

    def test_start_manual_track(self):
        record = trial_start("test-manual", task_title="Manual", track="manual")
        self.assertEqual(record["track"], "track_a")

    def test_start_twice_raises(self):
        trial_start("test-dup", task_title="Test")
        with self.assertRaises(AgyFlowError):
            trial_start("test-dup", task_title="Test")

    def test_event_increments_counter(self):
        trial_start("test-events", task_title="Event test")
        trial_event("test-events", "copy", count=3)
        trial_event("test-events", "decision", note="Decided to use Claude")
        trial_event("test-events", "error_caught", note="Found X API bug")

        record = trial_export("test-events")
        counters = record.get("track_b", {})
        self.assertEqual(counters.get("context_copy_count"), 3)
        self.assertEqual(counters.get("manual_decision_count"), 1)
        self.assertEqual(counters.get("errors_caught"), 1)

        # Events list
        trail = json.loads(
            (agy_flow.config.AGENTS_DIR / "trials" / "test-events.json").read_text()
        )
        self.assertEqual(len(trail["events"]), 3)

    def test_stop_sets_ended_at(self):
        trial_start("test-stop", task_title="Stop test")
        stopped = trial_stop("test-stop")
        self.assertIsNotNone(stopped["ended_at"])

    def test_export_value_report_compatible(self):
        trial_start("test-export", task_title="Export test", track="manual")
        trial_event("test-export", "copy", count=5)
        trial_event("test-export", "decision", count=3)
        trial_event("test-export", "artifact", count=2)

        exported = trial_export("test-export")
        self.assertEqual(exported["trial_id"], "test-export")
        self.assertIn("track_a", exported)
        self.assertEqual(exported["track_a"]["context_copy_count"], 5)
        self.assertEqual(exported["track_a"]["manual_decision_count"], 3)
        self.assertEqual(exported["track_a"]["artifacts_generated"], 2)

    def test_export_to_file(self):
        trial_start("test-file", task_title="File export", track="agy-flow")
        trial_event("test-file", "copy", count=2)

        output_path = str(self.temp_path / "exported.json")
        trial_export("test-file", output_path=output_path)
        self.assertTrue(Path(output_path).exists())

        with open(output_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["trial_id"], "test-file")
        self.assertEqual(data["track_b"]["context_copy_count"], 2)

    def test_missing_trial_raises(self):
        with self.assertRaises(AgyFlowError):
            trial_event("nonexistent", "copy")

    def test_invalid_event_type_raises(self):
        trial_start("test-invalid-event", task_title="X")
        with self.assertRaises(AgyFlowError):
            trial_event("test-invalid-event", "invalid_type")

    def test_notes_increment(self):
        trial_start("test-notes", task_title="Notes")
        trial_event("test-notes", "note", count=10)
        record = trial_export("test-notes")
        counters = record.get("track_b", {})
        self.assertEqual(counters.get("notes_taken_lines"), 10)


if __name__ == "__main__":
    unittest.main()
