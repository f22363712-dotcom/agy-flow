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
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port

# Dynamically import agy-flow.py due to hyphen in filename
project_root = Path(__file__).parent.resolve()
spec = importlib.util.spec_from_file_location(
    "agy_flow_main",
    project_root / "agy-flow.py"
)
agy_flow_mod = importlib.util.module_from_spec(spec)
sys.modules["agy_flow_main"] = agy_flow_mod
spec.loader.exec_module(agy_flow_mod)


class TestAgyFlowServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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

        # Create a dummy task inside the temp environment for details/handoff tests
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
        
        cls.temp_dir.cleanup()

    def test_health(self):
        req = urllib.request.Request(f"{self.base_url}/health")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode('utf-8'))
            self.assertEqual(data.get("status"), "ok")
            self.assertIn("project_root", data)

    def test_tasks(self):
        req = urllib.request.Request(f"{self.base_url}/tasks")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode('utf-8'))
            self.assertIsInstance(data, list)
            if len(data) > 0:
                self.assertIn("id", data[0])
                self.assertIn("title", data[0])
                self.assertIn("agent", data[0])
                self.assertIn("status", data[0])

    def test_task_detail(self):
        req_tasks = urllib.request.Request(f"{self.base_url}/tasks")
        with urllib.request.urlopen(req_tasks) as res_tasks:
            tasks = json.loads(res_tasks.read().decode('utf-8'))
        
        if not tasks:
            self.skipTest("No tasks found in board.md to test detail endpoint.")
        
        target_id = tasks[0]["id"]
        req = urllib.request.Request(f"{self.base_url}/tasks/{target_id}")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode('utf-8'))
            self.assertEqual(data.get("id"), target_id)
            self.assertIn("title", data)
            self.assertIn("agent", data)
            self.assertIn("status", data)
            self.assertIn("plan", data)
            self.assertIn("content", data)

    def test_task_handoff_plan(self):
        req_tasks = urllib.request.Request(f"{self.base_url}/tasks")
        with urllib.request.urlopen(req_tasks) as res_tasks:
            tasks = json.loads(res_tasks.read().decode('utf-8'))
        
        if not tasks:
            self.skipTest("No tasks found in board.md to test handoff-plan endpoint.")
        
        target_id = tasks[0]["id"]
        req = urllib.request.Request(f"{self.base_url}/tasks/{target_id}/handoff-plan")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode('utf-8'))
            self.assertEqual(data.get("task_id"), target_id)
            self.assertIn("active_agent", data)
            self.assertIn("handoff_steps", data)
            self.assertIn("next_step", data)

    def test_plan_post(self):
        payload = json.dumps({"title": "设计用户登录页面并在后台验证"}).encode('utf-8')
        req = urllib.request.Request(
            f"{self.base_url}/plan",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode('utf-8'))
            self.assertIn("legacy_agent", data)
            self.assertIn("recommended_pipeline", data)
            self.assertIn("task_type", data)

    def test_plan_post_invalid(self):
        # 1. Empty body
        req = urllib.request.Request(
            f"{self.base_url}/plan",
            data=b"",
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)
        err_data = json.loads(ctx.exception.read().decode('utf-8'))
        self.assertIn("error", err_data)

        # 2. Missing title
        payload = json.dumps({"wrong_key": "some value"}).encode('utf-8')
        req2 = urllib.request.Request(
            f"{self.base_url}/plan",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req2)
        self.assertEqual(ctx.exception.code, 400)
        err_data2 = json.loads(ctx.exception.read().decode('utf-8'))
        self.assertIn("error", err_data2)

    def test_not_found(self):
        req = urllib.request.Request(f"{self.base_url}/invalid-route-abc")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 404)
        err_data = json.loads(ctx.exception.read().decode('utf-8'))
        self.assertIn("error", err_data)

    def test_cors_headers(self):
        # Test OPTIONS preflight
        req = urllib.request.Request(f"{self.base_url}/health", method="OPTIONS")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 204)
            self.assertEqual(res.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertEqual(res.headers.get("Access-Control-Allow-Methods"), "GET, POST, OPTIONS")
            self.assertEqual(res.headers.get("Access-Control-Allow-Headers"), "Content-Type")

        # Test normal GET headers
        req_get = urllib.request.Request(f"{self.base_url}/health")
        with urllib.request.urlopen(req_get) as res:
            self.assertEqual(res.headers.get("Access-Control-Allow-Origin"), "*")

    def test_create_task_post(self):
        payload = json.dumps({
            "title": "API Gateway Integration Test Task",
            "agent": "codex",
            "desc": "Testing POST /tasks write API"
        }).encode('utf-8')
        req = urllib.request.Request(
            f"{self.base_url}/tasks",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 201)
            data = json.loads(res.read().decode('utf-8'))
            self.assertEqual(data.get("status"), "created")
            self.assertTrue(data.get("task_id").startswith("task-"))
            self.assertIn("task_file", data)
            self.assertIn("plan_file", data)
            self.assertEqual(data.get("agent"), "codex")

    def test_start_and_submit_task_post_fail_if_no_worktree(self):
        # Test start task with a non-existent task_id should raise SystemExit handled code 400
        req = urllib.request.Request(
            f"{self.base_url}/tasks/task-999/start",
            data=b"",
            method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)
        err_data = json.loads(ctx.exception.read().decode('utf-8'))
        self.assertIn("error", err_data)

        # Test submit task with a non-existent task_id should raise SystemExit handled code 400
        req_submit = urllib.request.Request(
            f"{self.base_url}/tasks/task-999/submit",
            data=b"",
            method="POST"
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_submit)
        self.assertEqual(ctx.exception.code, 400)
        err_data_sub = json.loads(ctx.exception.read().decode('utf-8'))
        self.assertIn("error", err_data_sub)

    def test_dashboard_endpoint(self):
        # Test GET /
        req = urllib.request.Request(f"{self.base_url}/")
        with urllib.request.urlopen(req) as res:
            self.assertEqual(res.status, 200)
            self.assertIn("text/html", res.headers.get("Content-Type"))
            html_content = res.read().decode('utf-8')
            self.assertIn("agy-flow | 协同看板", html_content)

        # Test GET /dashboard
        req_dash = urllib.request.Request(f"{self.base_url}/dashboard")
        with urllib.request.urlopen(req_dash) as res:
            self.assertEqual(res.status, 200)
            self.assertIn("text/html", res.headers.get("Content-Type"))


if __name__ == "__main__":
    unittest.main()
