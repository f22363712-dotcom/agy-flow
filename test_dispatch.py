"""Tests for agent_relay/adapter.py — Agent Adapter v1 dispatch.

All tests run in an isolated temporary directory to avoid polluting the
real repository.
"""

from agent_relay.config import update_paths
from agent_relay.errors import AgentRelayError
from agent_relay.adapter import (
    dispatch,
    get_adapter,
    DeepSeekAdapter,
    HumanInLoopAdapter,
    _new_run_id,
    _ensure_runs_dir,
    _ADAPTERS,
)
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure the project root is on sys.path
project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class TestAdapterUnit(unittest.TestCase):
    """Unit tests for adapter internals (no project init needed)."""

    def test_new_run_id_format(self):
        run_id = _new_run_id()
        self.assertTrue(run_id.startswith("run-"))
        self.assertEqual(len(run_id), 16)  # "run-" + 12 hex chars

    def test_get_adapter_registered(self):
        deepseek = get_adapter("deepseek")
        self.assertIsInstance(deepseek, DeepSeekAdapter)

        codex = get_adapter("codex")
        self.assertIsInstance(codex, HumanInLoopAdapter)
        self.assertEqual(codex.agent_name, "codex")

        antigravity = get_adapter("antigravity")
        self.assertIsInstance(antigravity, HumanInLoopAdapter)
        self.assertEqual(antigravity.agent_name, "antigravity")

    def test_get_adapter_case_insensitive(self):
        self.assertEqual(get_adapter("DeepSeek").agent_name, "deepseek")
        self.assertEqual(get_adapter("CODEX").agent_name, "codex")

    def test_get_adapter_invalid(self):
        with self.assertRaises(AgentRelayError):
            get_adapter("nonexistent")

    def test_register_adapter_overrides(self):
        """Registering a new adapter for an existing name should replace it."""

        class FakeAdapter:
            agent_name = "deepseek"

            def dispatch(self, task_id, **kwargs):
                return {"agent": "fake"}

        fake = FakeAdapter()
        _ADAPTERS["deepseek"] = fake
        # Restore real adapter
        from agent_relay.adapter import register_adapter

        register_adapter(DeepSeekAdapter)
        restored = get_adapter("deepseek")
        self.assertIsInstance(restored, DeepSeekAdapter)


class TestAdapterDispatchIsolated(unittest.TestCase):
    """Integration tests for dispatch in an isolated temporary project."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name).resolve()

        # Prevent VS Code launch
        os.environ["AGY_FLOW_TESTING"] = "1"

        # Save original module paths
        import agent_relay.config
        import agent_relay.tasks

        # Point config at temp dir
        agent_relay.config._orig_paths = (
            agent_relay.config.PROJECT_ROOT,
            agent_relay.config.AGENTS_DIR,
            agent_relay.config.TASKS_DIR,
            agent_relay.config.RUNS_DIR,
        )
        agent_relay.config.PROJECT_ROOT = cls.temp_path
        agent_relay.config.AGENTS_DIR = cls.temp_path / ".agents"
        agent_relay.config.TASKS_DIR = agent_relay.config.AGENTS_DIR / "tasks"
        agent_relay.config.RUNS_DIR = agent_relay.config.AGENTS_DIR / "runs"
        agent_relay.config.update_paths(cls.temp_path)

        # Also patch agent_relay.tasks module references
        agent_relay.tasks.PROJECT_ROOT = cls.temp_path
        agent_relay.tasks.AGENTS_DIR = agent_relay.config.AGENTS_DIR
        agent_relay.tasks.TASKS_DIR = agent_relay.config.TASKS_DIR

        # Sync adapter module paths
        import agent_relay.adapter

        agent_relay.adapter.RUNS_DIR = agent_relay.config.RUNS_DIR

        # Init project in temp dir
        from agent_relay.tasks import init_project

        class DummyArgs:
            pass

        init_project(DummyArgs())

        # Patch git_ops module path AFTER init_project (init_project writes
        # back to config but does not touch git_ops)
        import agent_relay.git_ops

        cls._orig_gitops_root = agent_relay.git_ops.PROJECT_ROOT
        agent_relay.git_ops.PROJECT_ROOT = cls.temp_path

        # Overwrite worktrees_dir in temp config
        config_path = cls.temp_path / ".agents" / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            cfg["worktrees_dir"] = str(cls.temp_path / "worktrees")
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        # Restore module paths
        import agent_relay.config
        import agent_relay.tasks
        import agent_relay.adapter
        import agent_relay.git_ops

        if hasattr(agent_relay.config, "_orig_paths"):
            agent_relay.config.PROJECT_ROOT = agent_relay.config._orig_paths[0]
            agent_relay.config.AGENTS_DIR = agent_relay.config._orig_paths[1]
            agent_relay.config.TASKS_DIR = agent_relay.config._orig_paths[2]
            agent_relay.config.RUNS_DIR = agent_relay.config._orig_paths[3]

        if hasattr(cls, "_orig_gitops_root"):
            agent_relay.git_ops.PROJECT_ROOT = cls._orig_gitops_root

        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def _create_task(self, title="Test Task", agent="claude"):
        """Helper: create a task in the temp project and return its task_id."""
        from agent_relay.tasks import create_task

        class DummyArgs:
            pass

        args = DummyArgs()
        args.title = title
        args.agent = agent
        args.desc = "Test task for dispatch"
        result = create_task(args)
        return result["task_id"]

    def _start_task(self, task_id):
        """Helper: start a task to create a worktree."""
        from agent_relay.tasks import start_task

        class DummyArgs:
            pass

        args = DummyArgs()
        args.task_id = task_id
        args.launch_editor = False
        start_task(args)

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_dispatch_deepseek_mock(self):
        task_id = self._create_task()
        record = dispatch(task_id, "deepseek", mock=True)

        self.assertEqual(record["task_id"], task_id)
        self.assertEqual(record["agent"], "deepseek")
        self.assertEqual(record["status"], "success")
        self.assertIn("run_id", record)
        self.assertIn("started_at", record)
        self.assertIn("ended_at", record)
        self.assertIn("result", record)
        self.assertEqual(record["result"].get("review_source"), "mock")
        self.assertIn("_record_path", record)

        # Verify run file was persisted
        run_path = Path(record["_record_path"])
        self.assertTrue(run_path.exists())
        persisted = json.loads(run_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["run_id"], record["run_id"])

    def test_dispatch_deepseek_mock_includes_summary(self):
        task_id = self._create_task()
        record = dispatch(task_id, "deepseek", mock=True)

        self.assertIn("summary", record["result"])
        self.assertIn("full_review", record["result"])

    def test_dispatch_deepseek_no_task_raises(self):
        with self.assertRaises(AgentRelayError):
            dispatch("task-999", "deepseek", mock=True)

    def test_dispatch_codex_no_worktree_raises(self):
        task_id = self._create_task()
        with self.assertRaises(AgentRelayError) as ctx:
            dispatch(task_id, "codex")
        self.assertIn("has no worktree", str(ctx.exception))

    def test_dispatch_codex_with_worktree(self):
        task_id = self._create_task()
        self._start_task(task_id)

        record = dispatch(task_id, "codex")
        self.assertEqual(record["status"], "handoff")
        self.assertEqual(record["agent"], "codex")
        self.assertIn("instruction", record.get("result", {}))
        self.assertIn("worktree", record.get("result", {}))
        self.assertIn("Codex", record["result"]["instruction"])

        # Verify run file was persisted
        run_path = Path(record["_record_path"])
        self.assertTrue(run_path.exists())

    def test_dispatch_antigravity_in_progress(self):
        task_id = self._create_task()
        self._start_task(task_id)

        record = dispatch(task_id, "antigravity")
        self.assertEqual(record["status"], "handoff")
        self.assertEqual(record["agent"], "antigravity")
        self.assertIn("Antigravity", record["result"]["instruction"])

    def test_dispatch_task_not_in_progress_raises(self):
        task_id = self._create_task()
        # Create a worktree-less "Todo" task — start creates worktree but
        # we can test the "not in progress" case by calling before start
        with self.assertRaises(AgentRelayError) as ctx:
            dispatch(task_id, "codex")
        self.assertIn("has no worktree", str(ctx.exception))

    def test_dispatch_codex_updates_guard_file(self):
        task_id = self._create_task()
        self._start_task(task_id)

        dispatch(task_id, "codex")

        # Check guard file in worktree
        from agent_relay.config import PROJECT_ROOT, AGENTS_DIR

        guard_path = AGENTS_DIR / "current_task.json"
        self.assertTrue(guard_path.exists())
        guard = json.loads(guard_path.read_text(encoding="utf-8"))
        self.assertEqual(guard.get("agent"), "Codex")
        self.assertEqual(guard.get("writer"), "Codex")
        self.assertIsInstance(guard.get("reviewers"), list)
        self.assertIsNotNone(guard.get("timestamp"))

    def test_dispatch_run_record_full_structure(self):
        """Verify the persisted run record contains all required fields."""
        task_id = self._create_task()
        record = dispatch(task_id, "deepseek", mock=True)

        required = [
            "run_id",
            "task_id",
            "agent",
            "role",
            "status",
            "started_at",
            "ended_at",
            "result",
            "error",
        ]
        for key in required:
            self.assertIn(key, record, f"Missing required field: {key}")

        self.assertEqual(record["role"], "writer")  # default

    def test_dispatch_deepseek_unavailable_without_key(self):
        """Without DEEPSEEK_API_KEY, dispatch should return unavailable."""
        task_id = self._create_task()
        self._start_task(task_id)

        # Temporarily remove DEEPSEEK_API_KEY if present
        old_key = os.environ.pop("DEEPSEEK_API_KEY", None)
        old_lt = os.environ.pop("LITELLM_API_KEY", None)
        try:
            record = dispatch(task_id, "deepseek", mock=False)
            self.assertEqual(record["status"], "unavailable")
            self.assertIn("API key", record.get("error", ""))
        finally:
            if old_key is not None:
                os.environ["DEEPSEEK_API_KEY"] = old_key
            if old_lt is not None:
                os.environ["LITELLM_API_KEY"] = old_lt

    def test_runs_dir_created(self):
        """Calling dispatch should create the .agents/runs/ directory."""
        runs_dir = _ensure_runs_dir()
        self.assertTrue(runs_dir.exists())
        self.assertTrue(runs_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
