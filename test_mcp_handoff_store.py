"""Direct unit tests for agent_relay.mcp_handoff_store — HandoffStore.

Tests the store in isolation with a temporary directory, no project init
required.  Covers write / read / ack / history / current_all / restart
recovery / corrupt JSON.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from agent_relay.mcp_handoff_store import HandoffStore, HandoffContext, AckResult


class TestHandoffStoreBasics(unittest.TestCase):
    """Core CRUD — write, read, ack, history, current_all."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.agents_dir = Path(self.temp.name) / ".agents"
        self.agents_dir.mkdir(parents=True)
        self.store = HandoffStore(self.agents_dir)

    def tearDown(self):
        try:
            self.temp.cleanup()
        except Exception:
            pass

    def _sample(self, **overrides) -> HandoffContext:
        ctx = HandoffContext(
            handoff_id=overrides.pop("handoff_id", ""),
            task_id=overrides.pop("task_id", "task-001"),
            from_agent=overrides.pop("from_agent", "claude"),
            to_agent=overrides.pop("to_agent", "codex"),
            summary=overrides.pop("summary", "Unit test handoff"),
            context=overrides.pop("context", "Test context data."),
        )
        for k, v in overrides.items():
            object.__setattr__(ctx, k, v)
        return ctx

    # -- write / read -------------------------------------------------------

    def test_write_generates_handoff_id(self):
        ctx = self._sample(handoff_id="")
        saved = self.store.write(ctx)
        self.assertTrue(len(saved.handoff_id) >= 16)

    def test_write_preserves_explicit_id(self):
        ctx = self._sample(handoff_id="aabbccdd11223344aabbccdd")
        saved = self.store.write(ctx)
        self.assertEqual(saved.handoff_id, "aabbccdd11223344aabbccdd")

    def test_write_then_read(self):
        ctx = self._sample(task_id="task-001", summary="Hello handoff")
        self.store.write(ctx)
        read = self.store.read("task-001")
        self.assertIsNotNone(read)
        self.assertEqual(read.summary, "Hello handoff")
        self.assertEqual(read.from_agent, "claude")

    def test_write_overwrites_current_per_task(self):
        ctx1 = self._sample(task_id="task-001", summary="First")
        self.store.write(ctx1)
        ctx2 = self._sample(task_id="task-001", summary="Second")
        self.store.write(ctx2)
        read = self.store.read("task-001")
        self.assertEqual(read.summary, "Second")

    def test_read_nonexistent_returns_none(self):
        self.assertIsNone(self.store.read("task-999"))

    # -- ack ----------------------------------------------------------------

    def test_ack_success(self):
        self.store.write(self._sample(task_id="task-001"))
        result = self.store.ack("task-001", "codex")
        self.assertEqual(result.status, "acknowledged")
        self.assertEqual(result.acked_by, "codex")

    def test_ack_updates_current_file(self):
        self.store.write(self._sample(task_id="task-001"))
        self.store.ack("task-001", "codex")
        ctx = self.store.read("task-001")
        self.assertTrue(ctx.acked)
        self.assertEqual(ctx.acked_by, "codex")
        self.assertIsNotNone(ctx.acked_at)

    def test_ack_idempotent(self):
        self.store.write(self._sample(task_id="task-001"))
        r1 = self.store.ack("task-001", "codex")
        self.assertEqual(r1.status, "acknowledged")
        r2 = self.store.ack("task-001", "codex")
        self.assertEqual(r2.status, "already_acked")

    def test_ack_not_found(self):
        result = self.store.ack("task-999", "claude")
        self.assertEqual(result.status, "not_found")

    # -- history ------------------------------------------------------------

    def test_history_includes_all_writes(self):
        for i in range(3):
            self.store.write(self._sample(task_id="task-001", summary=f"Write {i}"))
        hist = self.store.history()
        self.assertGreaterEqual(len(hist), 1)  # at least 1
        summaries = {e.summary for e in hist}
        self.assertIn("Write 2", summaries)

    def test_history_respects_limit(self):
        for i in range(5):
            self.store.write(self._sample(task_id="task-001", summary=f"W{i}"))
        hist = self.store.history(limit=2)
        self.assertEqual(len(hist), 2)

    def test_history_filters_by_task_id(self):
        self.store.write(self._sample(task_id="task-001", summary="A"))
        self.store.write(self._sample(task_id="task-002", summary="B"))
        hist = self.store.history(task_id="task-001", limit=10)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0].summary, "A")

    # -- current_all --------------------------------------------------------

    def test_current_all_empty_when_no_writes(self):
        self.assertEqual(len(self.store.current_all()), 0)

    def test_current_all_returns_all_tasks(self):
        self.store.write(self._sample(task_id="task-001", summary="A"))
        self.store.write(self._sample(task_id="task-002", summary="B"))
        all_ = self.store.current_all()
        self.assertEqual(len(all_), 2)
        self.assertEqual(all_["task-001"].summary, "A")
        self.assertEqual(all_["task-002"].summary, "B")

    # -- restart recovery ---------------------------------------------------

    def test_restore_from_disk_after_new_store(self):
        self.store.write(self._sample(task_id="task-001", summary="Persistent"))
        store2 = HandoffStore(self.agents_dir)
        ctx = store2.read("task-001")
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.summary, "Persistent")

    def test_history_survives_restart(self):
        self.store.write(self._sample(task_id="task-001", summary="Survive"))
        store2 = HandoffStore(self.agents_dir)
        # history reads from disk archives
        hist = store2.history(task_id="task-001")
        # The handoff was written via the first store, so history
        # should have at least one entry for task-001.
        self.assertGreaterEqual(len(hist), 1)
        self.assertEqual(hist[0].summary, "Survive")

    def test_ack_syncs_to_history(self):
        """After ack, the history entry should also have acked=True."""
        self.store.write(
            self._sample(
                task_id="task-001",
                summary="Ack sync test",
            )
        )
        history_before = self.store.history(task_id="task-001")
        self.assertFalse(history_before[0].acked)

        self.store.ack("task-001", "codex")

        # Read history from a fresh store
        store2 = HandoffStore(self.agents_dir)
        hist_after = store2.history(task_id="task-001")
        self.assertTrue(hist_after[0].acked)
        self.assertEqual(hist_after[0].acked_by, "codex")

    # -- corrupt JSON -------------------------------------------------------

    def test_read_returns_none_on_corrupt_current(self):
        self.store.write(self._sample(task_id="task-001"))
        path = self.store._current_path("task-001")
        path.write_text("not-json", encoding="utf-8")
        self.assertIsNone(self.store.read("task-001"))

    def test_current_all_skips_corrupt_files(self):
        self.store.write(self._sample(task_id="task-001"))
        # Write a second file manually with corrupt content
        (self.store._current_dir / "task-999.json").write_text(
            "{{{bad", encoding="utf-8"
        )
        all_ = self.store.current_all()
        self.assertIn("task-001", all_)
        self.assertNotIn("task-999", all_)

    def test_history_skips_corrupt_files(self):
        self.store.write(self._sample(task_id="task-001"))
        # inject a corrupt history file
        (self.store._history_dir / "corrupt_task-001.json").write_text(
            "{{{bad", encoding="utf-8"
        )
        hist = self.store.history(task_id="task-001")
        self.assertGreaterEqual(len(hist), 1)
        self.assertEqual(hist[0].summary, "Unit test handoff")


if __name__ == "__main__":
    unittest.main()
