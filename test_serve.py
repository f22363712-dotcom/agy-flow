import unittest
import threading
import json
import urllib.request
import urllib.error
import importlib.util
from http.server import HTTPServer
from pathlib import Path
import sys
import tempfile
import os
import socket


def get_free_port():
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# Dynamically import agy-flow.py due to hyphen in filename
project_root = Path(__file__).parent.resolve()
spec = importlib.util.spec_from_file_location(
    "agy_flow_main", project_root / "agy-flow.py"
)
agy_flow_mod = importlib.util.module_from_spec(spec)
sys.modules["agy_flow_main"] = agy_flow_mod
spec.loader.exec_module(agy_flow_mod)


class TestAgyFlowServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Prevent any VS Code launch during tests
        os.environ["AGY_FLOW_TESTING"] = "1"

        # Setup temporary directories to avoid polluting main repository
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name).resolve()

        # Change current directory
        cls.old_cwd = os.getcwd()
        os.chdir(cls.temp_path)

        # Patch paths inside the imported agy-flow module
        cls.old_project_root = agy_flow_mod.PROJECT_ROOT
        agy_flow_mod.PROJECT_ROOT = cls.temp_path
        agy_flow_mod.AGENTS_DIR = cls.temp_path / ".agents"
        agy_flow_mod.TASKS_DIR = agy_flow_mod.AGENTS_DIR / "tasks"
        agy_flow_mod.TEMPLATES_DIR = agy_flow_mod.AGENTS_DIR / "templates"
        agy_flow_mod.LOGS_DIR = agy_flow_mod.AGENTS_DIR / "logs"
        agy_flow_mod.CONFIG_FILE = agy_flow_mod.AGENTS_DIR / "config.json"
        agy_flow_mod.BOARD_FILE = agy_flow_mod.TASKS_DIR / "board.md"
        agy_flow_mod.COSTS_FILE = agy_flow_mod.AGENTS_DIR / "costs.json"

        # Patch paths inside agy_flow.config module too
        import agy_flow.config

        agy_flow.config.update_paths(cls.temp_path)

        # Patch path inside agy_flow.git_ops module
        import agy_flow.git_ops

        agy_flow.git_ops.PROJECT_ROOT = cls.temp_path

        # Initialize the project in the temp directory
        class DummyArgs:
            pass

        agy_flow_mod.init_project(DummyArgs())

        # Overwrite worktrees_dir in the temp config to avoid directory
        # collisions
        config_path = cls.temp_path / ".agents" / "config.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["worktrees_dir"] = str(cls.temp_path / "worktrees")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)

        # Create a dummy task inside the temp environment for details/handoff
        # tests
        class DummyCreateArgs:
            title = "API Gateway Integration Test Task"
            agent = "codex"
            desc = "Testing write API"

        agy_flow_mod.create_task(DummyCreateArgs())

        class Args:
            host = "127.0.0.1"
            port = get_free_port()

        cls.server = HTTPServer((Args.host, Args.port), agy_flow_mod.AgyFlowHTTPHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{Args.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join()

        # Restore directory and cleanup
        os.chdir(cls.old_cwd)
        agy_flow_mod.PROJECT_ROOT = cls.old_project_root
        agy_flow_mod.AGENTS_DIR = cls.old_project_root / ".agents"
        agy_flow_mod.TASKS_DIR = agy_flow_mod.AGENTS_DIR / "tasks"
        agy_flow_mod.TEMPLATES_DIR = agy_flow_mod.AGENTS_DIR / "templates"
        agy_flow_mod.LOGS_DIR = agy_flow_mod.AGENTS_DIR / "logs"
        agy_flow_mod.CONFIG_FILE = agy_flow_mod.AGENTS_DIR / "config.json"
        agy_flow_mod.BOARD_FILE = agy_flow_mod.TASKS_DIR / "board.md"
        agy_flow_mod.COSTS_FILE = agy_flow_mod.AGENTS_DIR / "costs.json"

        # Restore agy_flow.config module paths too
        import agy_flow.config

        agy_flow.config.update_paths(cls.old_project_root)

        # Restore agy_flow.git_ops module paths too
        import agy_flow.git_ops

        agy_flow.git_ops.PROJECT_ROOT = cls.old_project_root

        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def test_health(self):
        req = urllib.request.Request(f"{self.base_url}/health")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertIn("project_root", data)

    def test_tasks(self):
        req = urllib.request.Request(f"{self.base_url}/tasks")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertIsInstance(data, list)
            if len(data) > 0:
                self.assertIn("id", data[0])
                self.assertIn("title", data[0])
                self.assertIn("agent", data[0])
                self.assertIn("status", data[0])

    def test_task_detail(self):
        req_tasks = urllib.request.Request(f"{self.base_url}/tasks")
        with urllib.request.urlopen(req_tasks) as res_tasks:
            tasks = json.loads(res_tasks.read().decode("utf-8"))

        if not tasks:
            self.skipTest("No tasks found in board.md to test detail endpoint.")

        target_id = tasks[0]["id"]
        req = urllib.request.Request(f"{self.base_url}/tasks/{target_id}")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertEqual(data.get("id"), target_id)
            self.assertIn("title", data)
            self.assertIn("agent", data)
            self.assertIn("status", data)
            self.assertIn("plan", data)
            self.assertIn("content", data)

    def test_task_handoff_plan(self):
        req_tasks = urllib.request.Request(f"{self.base_url}/tasks")
        with urllib.request.urlopen(req_tasks) as res_tasks:
            tasks = json.loads(res_tasks.read().decode("utf-8"))

        if not tasks:
            self.skipTest("No tasks found in board.md to test handoff-plan endpoint.")

        target_id = tasks[0]["id"]
        req = urllib.request.Request(f"{self.base_url}/tasks/{target_id}/handoff-plan")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertEqual(data.get("task_id"), target_id)
            self.assertIn("active_agent", data)
            self.assertIn("handoff_steps", data)
            self.assertIn("next_step", data)

    def test_plan_post(self):
        payload = json.dumps({"title": "设计用户登录页面并在后台验证"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/plan",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertIn("legacy_agent", data)
            self.assertIn("recommended_pipeline", data)
            self.assertIn("task_type", data)

    def test_plan_post_invalid(self):
        # 1. Empty body
        req = urllib.request.Request(
            f"{self.base_url}/plan",
            data=b"",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)
        err_data = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertIn("error", err_data)

        # 2. Missing title
        payload = json.dumps({"wrong_key": "some value"}).encode("utf-8")
        req2 = urllib.request.Request(
            f"{self.base_url}/plan",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req2)
        self.assertEqual(ctx.exception.code, 400)
        err_data2 = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertIn("error", err_data2)

    def test_not_found(self):
        req = urllib.request.Request(f"{self.base_url}/invalid-route-abc")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 404)
        err_data = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertIn("error", err_data)

    def test_cors_headers(self):
        # Test OPTIONS preflight
        req = urllib.request.Request(f"{self.base_url}/health", method="OPTIONS")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 204)
            self.assertEqual(res.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertEqual(
                res.headers.get("Access-Control-Allow-Methods"), "GET, POST, OPTIONS"
            )
            self.assertEqual(
                res.headers.get("Access-Control-Allow-Headers"), "Content-Type"
            )

        # Test normal GET headers
        req_get = urllib.request.Request(f"{self.base_url}/health")
        with urllib.request.urlopen(req_get) as res:
            self.assertEqual(res.headers.get("Access-Control-Allow-Origin"), "*")

    def test_create_task_post(self):
        payload = json.dumps(
            {
                "title": "API Gateway Integration Test Task",
                "agent": "codex",
                "desc": "Testing POST /tasks write API",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/tasks",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 201)
            data = json.loads(res.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "created")
            self.assertTrue(data.get("task_id").startswith("task-"))
            self.assertIn("task_file", data)
            self.assertIn("plan_file", data)
            self.assertEqual(data.get("agent"), "codex")

    def test_start_and_submit_task_post_fail_if_no_worktree(self):
        # Test start task with a non-existent task_id should raise SystemExit
        # handled code 400
        req = urllib.request.Request(
            f"{self.base_url}/tasks/task-999/start", data=b"", method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)
        err_data = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertIn("error", err_data)

        # Test submit task with a non-existent task_id should raise SystemExit
        # handled code 400
        req_submit = urllib.request.Request(
            f"{self.base_url}/tasks/task-999/submit", data=b"", method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_submit)
        self.assertEqual(ctx.exception.code, 400)
        err_data_sub = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertIn("error", err_data_sub)

    def test_dashboard_endpoint(self):
        # Test GET /
        req = urllib.request.Request(f"{self.base_url}/")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            self.assertIn("text/html", res.headers.get("Content-Type"))
            html_content = res.read().decode("utf-8")
            self.assertIn("agy-flow | 协同看板", html_content)

        # Test GET /dashboard
        req_dash = urllib.request.Request(f"{self.base_url}/dashboard")
        with urllib.request.urlopen(req_dash) as res:
            self.assertEqual(res.status, 200)
            self.assertIn("text/html", res.headers.get("Content-Type"))

    def test_assign_endpoint(self):
        payload = json.dumps({"agent": "antigravity", "task_id": "task-001"}).encode(
            "utf-8"
        )
        req = urllib.request.Request(
            f"{self.base_url}/assign",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "success")
            self.assertEqual(data.get("agent"), "antigravity")
            self.assertEqual(data.get("writer"), "antigravity")
            self.assertEqual(data.get("mode"), "handoff")
            self.assertEqual(data.get("role"), "writer")
            self.assertEqual(data.get("task_id"), "task-001")
            self.assertIn("timestamp", data.get("metadata", {}))
            self.assertEqual(data["metadata"].get("writer"), "antigravity")
            self.assertIsInstance(data["metadata"].get("reviewers"), list)

    def test_assign_reviewer_endpoint(self):
        payload = json.dumps(
            {
                "agent": "codex",
                "task_id": "task-001",
                "role": "reviewer",
                "mode": "review",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/assign",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "success")
            self.assertEqual(data.get("agent"), "Codex")
            self.assertEqual(data.get("role"), "reviewer")
            self.assertEqual(data.get("mode"), "review")
            self.assertIn("Codex", data.get("reviewers", []))

    def test_assign_writer_with_reviewers(self):
        payload = json.dumps(
            {
                "agent": "claude",
                "task_id": "task-001",
                "role": "writer",
                "reviewers": ["antigravity", "codex"],
                "mode": "handoff",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/assign",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "success")
            self.assertEqual(data.get("writer"), "claude")
            self.assertEqual(data.get("role"), "writer")
            self.assertIn("antigravity", data.get("reviewers", []))
            self.assertIn("Codex", data.get("reviewers", []))
            self.assertNotIn("claude", data.get("reviewers", []))
            self.assertEqual(data.get("task_id"), "task-001")

    def test_assign_legacy_agent_preserved(self):
        """The legacy agent field must always be present for backward compat."""
        # Assign as reviewer first — writer stays, agent becomes the reviewer
        payload = json.dumps(
            {
                "agent": "codex",
                "task_id": "task-001",
                "role": "reviewer",
                "mode": "review",
                "reviewers": ["antigravity"],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/assign",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            # Legacy agent field must exist
            self.assertIn("agent", data.get("metadata", {}))
            # Writer is preserved from prior assignment (not overwritten by
            # reviewer)
            self.assertIsNotNone(data["metadata"].get("writer"))
            self.assertIn("writer", data["metadata"])
            # The legacy agent field reflects the current reviewer agent
            self.assertEqual(data["metadata"].get("agent"), "Codex")
            # Reviewers list includes both the specified reviewer and the
            # inherited ones
            self.assertIn("Codex", data["metadata"].get("reviewers", []))
            self.assertIn("antigravity", data["metadata"].get("reviewers", []))

    def test_agent_registry_endpoint(self):
        req = urllib.request.Request(f"{self.base_url}/config/agent-registry")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertIn("claude", data)
            self.assertIn("antigravity", data)
            self.assertIn("codex", data)
            self.assertIn("deepseek", data)

            # Assert no raw api keys present (only api_key_env names are
            # allowed)
            for agent_name, agent_cfg in data.items():
                for k, v in agent_cfg.items():
                    if k != "api_key_env":
                        self.assertNotIn("api_key", k.lower())
                        self.assertNotIn("secret", k.lower())
                        self.assertNotIn("token", k.lower())

    def test_ask_deepseek_missing_key(self):
        old_ds_key = os.environ.get("DEEPSEEK_API_KEY")
        old_lt_key = os.environ.get("LITELLM_API_KEY")
        if "DEEPSEEK_API_KEY" in os.environ:
            del os.environ["DEEPSEEK_API_KEY"]
        if "LITELLM_API_KEY" in os.environ:
            del os.environ["LITELLM_API_KEY"]

        try:
            payload = json.dumps({"prompt": "Hello DeepSeek"}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/ask/deepseek",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.code, 400)
            data = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "unavailable")
            self.assertEqual(data.get("review_source"), "unavailable")
            self.assertIn("error", data)
        finally:
            if old_ds_key is not None:
                os.environ["DEEPSEEK_API_KEY"] = old_ds_key
            if old_lt_key is not None:
                os.environ["LITELLM_API_KEY"] = old_lt_key

    def test_ask_deepseek_mock_explicit(self):
        old_ds_key = os.environ.get("DEEPSEEK_API_KEY")
        old_lt_key = os.environ.get("LITELLM_API_KEY")
        if "DEEPSEEK_API_KEY" in os.environ:
            del os.environ["DEEPSEEK_API_KEY"]
        if "LITELLM_API_KEY" in os.environ:
            del os.environ["LITELLM_API_KEY"]

        try:
            payload = json.dumps(
                {"prompt": "Hello DeepSeek mock test", "mock": True}
            ).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/ask/deepseek",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as res:
                self.assertEqual(res.status, 200)
                data = json.loads(res.read().decode("utf-8"))
                self.assertEqual(data.get("status"), "success")
                self.assertEqual(data.get("review_source"), "mock")
                self.assertIn("response", data)
                self.assertIn("Mock Answer", data.get("response"))
        finally:
            if old_ds_key is not None:
                os.environ["DEEPSEEK_API_KEY"] = old_ds_key
            if old_lt_key is not None:
                os.environ["LITELLM_API_KEY"] = old_lt_key

    def test_review_missing_key(self):
        old_ds_key = os.environ.get("DEEPSEEK_API_KEY")
        old_lt_key = os.environ.get("LITELLM_API_KEY")
        if "DEEPSEEK_API_KEY" in os.environ:
            del os.environ["DEEPSEEK_API_KEY"]
        if "LITELLM_API_KEY" in os.environ:
            del os.environ["LITELLM_API_KEY"]

        req_start = urllib.request.Request(
            f"{self.base_url}/tasks/task-001/start", data=b"", method="POST"
        )
        try:
            with urllib.request.urlopen(req_start) as r:
                pass
        except urllib.error.HTTPError:
            pass

        try:
            payload = json.dumps({"mock": False}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/tasks/task-001/review",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req)
            self.assertEqual(ctx.exception.code, 400)
            data = json.loads(ctx.exception.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "missing_api_key")
            self.assertEqual(data.get("review_source"), "unavailable")
            self.assertIn("review", data)
        finally:
            if old_ds_key is not None:
                os.environ["DEEPSEEK_API_KEY"] = old_ds_key
            if old_lt_key is not None:
                os.environ["LITELLM_API_KEY"] = old_lt_key

    def test_review_mock_explicit(self):
        old_ds_key = os.environ.get("DEEPSEEK_API_KEY")
        old_lt_key = os.environ.get("LITELLM_API_KEY")
        if "DEEPSEEK_API_KEY" in os.environ:
            del os.environ["DEEPSEEK_API_KEY"]
        if "LITELLM_API_KEY" in os.environ:
            del os.environ["LITELLM_API_KEY"]

        req_start = urllib.request.Request(
            f"{self.base_url}/tasks/task-001/start", data=b"", method="POST"
        )
        try:
            with urllib.request.urlopen(req_start) as r:
                pass
        except Exception:
            pass

        try:
            payload = json.dumps({"mock": True}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/tasks/task-001/review",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as res:
                self.assertEqual(res.status, 200)
                data = json.loads(res.read().decode("utf-8"))
                self.assertEqual(data.get("status"), "success")
                self.assertEqual(data.get("review_source"), "mock")
                self.assertIn("review", data)
                self.assertIn("Mock Review", data.get("review"))
        finally:
            if old_ds_key is not None:
                os.environ["DEEPSEEK_API_KEY"] = old_ds_key
            if old_lt_key is not None:
                os.environ["LITELLM_API_KEY"] = old_lt_key

    # ------------------------------------------------------------------
    # Agent Adapter v1 — Dispatch & Runs endpoint tests
    # ------------------------------------------------------------------

    def test_dispatch_endpoint_deepseek_mock(self):
        payload = json.dumps({"agent": "deepseek", "mock": True}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/tasks/task-001/dispatch",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "success")
            self.assertEqual(data.get("agent"), "deepseek")
            self.assertEqual(data.get("task_id"), "task-001")
            self.assertIn("run_id", data)
            self.assertIn("started_at", data)
            self.assertIn("ended_at", data)
            self.assertEqual(data.get("result", {}).get("review_source"), "mock")

    def test_dispatch_endpoint_deepseek_missing_agent_400(self):
        payload = json.dumps({"mock": True}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/tasks/task-001/dispatch",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_dispatch_endpoint_human_in_loop_codex(self):
        # Start task-001 so it has a worktree
        start_req = urllib.request.Request(
            f"{self.base_url}/tasks/task-001/start", data=b"", method="POST"
        )
        try:
            urllib.request.urlopen(start_req)
        except urllib.error.HTTPError:
            pass

        payload = json.dumps({"agent": "codex", "role": "reviewer"}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/tasks/task-001/dispatch",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertIn("run_id", data)
            self.assertEqual(data.get("agent"), "codex")
            self.assertEqual(data.get("status"), "handoff")
            self.assertIn("instruction", data.get("result", {}))

    def test_dispatch_endpoint_task_not_found_400(self):
        payload = json.dumps({"agent": "deepseek", "mock": True}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/tasks/task-999/dispatch",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_runs_endpoint(self):
        # First create a run by dispatching a mock deepseek
        payload = json.dumps({"agent": "deepseek", "mock": True}).encode("utf-8")
        dispatch_req = urllib.request.Request(
            f"{self.base_url}/tasks/task-001/dispatch",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(dispatch_req)
        except urllib.error.HTTPError:
            pass

        req = urllib.request.Request(f"{self.base_url}/runs")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertIsInstance(data, list)
            self.assertGreaterEqual(len(data), 1)
            self.assertIn("run_id", data[0])
            self.assertIn("task_id", data[0])
            self.assertIn("agent", data[0])

    def test_task_runs_endpoint(self):
        req = urllib.request.Request(f"{self.base_url}/tasks/task-001/runs")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertIsInstance(data, list)
            for r in data:
                self.assertEqual(r.get("task_id"), "task-001")

    def test_run_detail_endpoint(self):
        # First get a run_id from the runs list
        req = urllib.request.Request(f"{self.base_url}/runs")
        with urllib.request.urlopen(req) as res:
            runs = json.loads(res.read().decode("utf-8"))
        if not runs:
            self.skipTest("No runs to test detail endpoint.")

        run_id = runs[0]["run_id"]
        detail_req = urllib.request.Request(f"{self.base_url}/runs/{run_id}")
        with urllib.request.urlopen(detail_req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertEqual(data.get("run_id"), run_id)
            self.assertIn("task_id", data)
            self.assertIn("agent", data)
            self.assertIn("status", data)
            self.assertIn("started_at", data)
            self.assertIn("ended_at", data)

    def test_run_detail_not_found(self):
        req = urllib.request.Request(f"{self.base_url}/runs/run-nonexistent")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 404)
        data = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()
