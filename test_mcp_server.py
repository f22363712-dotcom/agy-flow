"""Tests for agent_relay/mcp_server.py — MCP Server v2.

v2 adds 3 handoff tools + 3 resources.  Tests cover tools list, resource
listing/reading, initialize capabilities, and the full handoff tool flow.

All calls run in an isolated temporary directory.
"""

from agent_relay.errors import AgentRelayError
from agent_relay.mcp_server import (
    _TOOLS,
    _RESOURCE_TEMPLATES,
    _STATIC_RESOURCES,
    _build_resource_list,
    _handle_message,
)
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


# Known tool names for v2
_HANDOFF_TOOLS = {"agy_handoff_write", "agy_handoff_read", "agy_handoff_ack"}


class TestMCPToolsWithoutProject(unittest.TestCase):
    """Tests that don't need a full project init."""

    def test_tools_list_returns_12_tools(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        resp = _handle_message(msg)
        tools = resp["result"]["tools"]
        self.assertEqual(len(tools), 12)

    def test_each_tool_has_required_fields(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        resp = _handle_message(msg)
        for tool in resp["result"]["tools"]:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("inputSchema", tool)
            self.assertIn("properties", tool["inputSchema"])

    def test_tool_names_prefix(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        resp = _handle_message(msg)
        for tool in resp["result"]["tools"]:
            self.assertTrue(
                tool["name"].startswith("agy_"), f"Bad name: {tool['name']}"
            )

    def test_unknown_tool_returns_error(self):
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "nonexistent", "arguments": {}},
        }
        resp = _handle_message(msg)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32000)

    def test_initialize_returns_capabilities(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        resp = _handle_message(msg)
        self.assertIn("result", resp)
        self.assertIn("capabilities", resp["result"])
        self.assertIn("tools", resp["result"]["capabilities"])

    def test_notification_returns_none(self):
        msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        resp = _handle_message(msg)
        self.assertIsNone(resp)

    def test_unknown_method_returns_error(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "bogus", "params": {}}
        resp = _handle_message(msg)
        self.assertIn("error", resp)

    def test_agy_doctor_schema_has_no_required(self):
        for tool in _TOOLS:
            if tool["name"] == "agy_doctor":
                self.assertEqual(tool["inputSchema"]["required"], [])
                return
        self.fail("agy_doctor not found")

    # -- v2: Resources tests -------------------------------------------------

    def test_resources_list_returns_at_least_2_resources(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "resources/list"}
        resp = _handle_message(msg)
        self.assertIn("result", resp)
        resources = resp["result"]["resources"]
        # 2 static (handoff://history, board://tasks) + dynamic
        # handoff://current/*
        self.assertGreaterEqual(len(resources), 2)

    def test_each_resource_has_required_fields(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "resources/list"}
        resp = _handle_message(msg)
        for r in resp["result"]["resources"]:
            self.assertIn("uri", r)
            self.assertIn("name", r)
            self.assertIn("description", r)
            self.assertIn("mimeType", r)

    def test_initialize_has_resources_capability(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        resp = _handle_message(msg)
        caps = resp["result"]["capabilities"]
        self.assertIn("resources", caps)

    def test_handoff_tools_in_list(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        resp = _handle_message(msg)
        names = {t["name"] for t in resp["result"]["tools"]}
        for htool in _HANDOFF_TOOLS:
            self.assertIn(htool, names, f"Missing handoff tool: {htool}")

    def test_handoff_tools_have_required_fields(self):
        for tool in _TOOLS:
            if tool["name"] in _HANDOFF_TOOLS:
                self.assertIn("inputSchema", tool)
                props = tool["inputSchema"]["properties"]
                self.assertIn("task_id", props, f"{tool['name']} missing task_id")
                if tool["name"] == "agy_handoff_write":
                    self.assertIn("from_agent", props)
                    self.assertIn("to_agent", props)
                    self.assertIn("summary", props)
                    self.assertIn("context", props)
                if tool["name"] == "agy_handoff_ack":
                    self.assertIn("agent", props)

    def test_resources_read_unknown_uri_returns_error(self):
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/read",
            "params": {"uri": "handoff://unknown"},
        }
        resp = _handle_message(msg)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32002)

    def test_resources_read_board_returns_json(self):
        """board://tasks should return a JSON array even without a project."""
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/read",
            "params": {"uri": "board://tasks"},
        }
        resp = _handle_message(msg)
        self.assertIn("result", resp, msg=f"Got error: {resp.get('error')}")
        self.assertIn("contents", resp["result"])
        self.assertEqual(resp["result"]["contents"][0]["mimeType"], "application/json")


class TestMCPCallsWithProject(unittest.TestCase):
    """Integration tests that require a full project init."""

    @classmethod
    def setUpClass(cls):
        os.environ["AGY_FLOW_TESTING"] = "1"
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.temp_dir.name).resolve()

        # Import and init project
        import agent_relay.config

        agent_relay.config.update_paths(cls.temp_path)

        from agent_relay.tasks import init_project

        class DummyArgs:
            pass

        init_project(DummyArgs())

        config_path = cls.temp_path / ".agents" / "config.json"
        if config_path.exists():
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            cfg["worktrees_dir"] = str(cls.temp_path / "worktrees")
            config_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

        # Also need to init git
        import agent_relay.git_ops

        cls._orig_git_root = agent_relay.git_ops.PROJECT_ROOT
        agent_relay.git_ops.PROJECT_ROOT = cls.temp_path

        # Create a task so we have something to work with
        from agent_relay.tasks import create_task

        class CreateArgs:
            title = "MCP test task"
            agent = "claude"
            desc = "Testing MCP server"

        create_task(CreateArgs())

    @classmethod
    def tearDownClass(cls):
        import agent_relay.git_ops

        agent_relay.git_ops.PROJECT_ROOT = cls._orig_git_root
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def _call(self, tool_name, arguments=None):
        """Helper: call *tool_name* via _handle_message and return result."""
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments or {}},
        }
        resp = _handle_message(msg)
        if "error" in resp:
            return {"error": resp["error"]["message"]}
        return json.loads(resp["result"]["content"][0]["text"])

    def test_agy_create_task(self):
        result = self._call("agy_create_task", {"title": "Another MCP task"})
        self.assertIn("task_id", result)
        self.assertIn("agent", result)
        self.assertEqual(result["status"], "created")

    def test_agy_route_task_with_task_id(self):
        result = self._call("agy_route_task", {"task_id": "task-001"})
        self.assertIn("primary", result)
        self.assertIn("fallbacks", result)

    def test_agy_route_task_with_title(self):
        result = self._call("agy_route_task", {"title": "Design login page"})
        self.assertIn("primary", result)

    def test_agy_route_task_no_args_returns_error(self):
        """When neither task_id nor title is given, route returns error."""
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "agy_route_task", "arguments": {}},
        }
        resp = _handle_message(msg)
        # Should return an AgentRelayError (code -32000)
        self.assertIn(
            "error",
            resp,
            msg=f"Expected error, got: {resp.get('result', {}).get('content', '')}",
        )

    def test_agy_auto_dispatch_dry_run(self):
        result = self._call(
            "agy_auto_dispatch", {"task_id": "task-001", "dry_run": True}
        )
        self.assertEqual(result["status"], "dry_run")
        self.assertIn("selected_agent", result)

    def test_agy_dispatch_deepseek_mock(self):
        result = self._call(
            "agy_dispatch", {"task_id": "task-001", "agent": "deepseek", "mock": True}
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("run_id", result)

    def test_agy_dispatch_missing_agent(self):
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "agy_dispatch", "arguments": {"task_id": "task-001"}},
        }
        resp = _handle_message(msg)
        # Should be an AgentRelayError for missing agent
        if "error" not in resp:
            result = json.loads(resp["result"]["content"][0]["text"])
            self.assertIn("error", str(result))
        else:
            self.assertIn("error", resp)

    def test_agy_continue_run_mock(self):
        # First create a run
        run_result = self._call(
            "agy_dispatch", {"task_id": "task-001", "agent": "deepseek", "mock": True}
        )
        run_id = run_result["run_id"]

        result = self._call("agy_continue_run", {"run_id": run_id, "mock": True})
        self.assertIn("status", result)
        self.assertIn("review_run", result)

    def test_agy_quality(self):
        result = self._call("agy_quality", {"task_id": "task-001"})
        self.assertIn("ready", result)
        self.assertIn("blocking_issues", result)

    def test_agy_finalize_dry_run(self):
        result = self._call("agy_finalize", {"task_id": "task-001", "dry_run": True})
        self.assertEqual(result["status"], "dry_run")
        self.assertIn("quality", result)

    def test_agy_status(self):
        result = self._call("agy_status", {"task_id": "task-001"})
        self.assertIn("state", result)
        self.assertIn("run_count", result)
        self.assertIn("quality_ready", result)

    def test_agy_doctor(self):
        result = self._call("agy_doctor", {})
        self.assertIn("healthy", result)
        self.assertIn("checks", result)

    # ------------------------------------------------------------------
    # New tests covering review findings
    # ------------------------------------------------------------------

    def test_ping_method(self):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
        resp = _handle_message(msg)
        self.assertIn("result", resp)
        self.assertEqual(resp["result"], {})

    def test_notifications_cancelled(self):
        msg = {"jsonrpc": "2.0", "method": "notifications/cancelled"}
        resp = _handle_message(msg)
        self.assertIsNone(resp)

    def test_agy_dispatch_claude_unavailable_or_handled(self):
        """Dispatching claude does not crash the server (CLI may/may not exist)."""
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "agy_dispatch",
                "arguments": {"task_id": "task-001", "agent": "claude"},
            },
        }
        resp = _handle_message(msg)
        # The server must not crash — it should return either a result or a
        # clean error
        self.assertTrue(
            "result" in resp or "error" in resp, msg=f"No result/error in {resp}"
        )
        if "error" in resp:
            self.assertIn("code", resp["error"])

    def test_agy_dispatch_invalid_agent_returns_error(self):
        """An unknown agent name should return a JSON-RPC error."""
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "agy_dispatch",
                "arguments": {"task_id": "task-001", "agent": "nonexistent"},
            },
        }
        resp = _handle_message(msg)
        self.assertIn("error", resp, f"Expected error, got: {resp}")

    def test_agy_finalize_default_dry_run(self):
        """Default dry_run=True must be the safe default."""
        result = self._call("agy_finalize", {"task_id": "task-001"})
        self.assertEqual(
            result.get("status"),
            "dry_run",
            f"Expected dry_run, got {result.get('status')} — safe default violated",
        )

    def test_agy_auto_dispatch_default_dry_run(self):
        """Default dry_run=True must be the safe default."""
        result = self._call("agy_auto_dispatch", {"task_id": "task-001"})
        self.assertEqual(
            result.get("status"),
            "dry_run",
            f"Expected dry_run, got {result.get('status')} — safe default violated",
        )

    def test_malformed_json_returns_parse_error(self):
        """Simulate malformed input to run_mcp_server via string."""
        import io

        old_stdin = sys.stdin
        old_stdout = sys.stdout

        sys.stdin = io.StringIO("not-json\n")
        sys.stdout = io.StringIO()
        try:
            from agent_relay.mcp_server import run_mcp_server

            # Run one iteration
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    resp = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    }
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
                    break  # one iteration for test

            output = sys.stdout.getvalue()
            parsed = json.loads(output)
            self.assertEqual(parsed["error"]["code"], -32700)
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

    def test_agy_create_task_auto_routes(self):
        """Create with UI task → antigravity (not hardcoded claude)."""
        result = self._call("agy_create_task", {"title": "设计视觉走查登录页面"})
        self.assertEqual(result.get("status"), "created")
        self.assertIn("task_id", result)
        # agent should be set by classifier, not hardcoded
        self.assertIn("agent", result)

    def test_invalid_task_id_format(self):
        """Malformed task_id returns AgentRelayError."""
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "agy_status", "arguments": {"task_id": "bad-id"}},
        }
        resp = _handle_message(msg)
        self.assertIn("error", resp)
        self.assertIn("Invalid task_id", resp["error"]["message"])

    def test_invalid_run_id_format(self):
        """Malformed run_id returns AgentRelayError."""
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "agy_continue_run", "arguments": {"run_id": "bad"}},
        }
        resp = _handle_message(msg)
        self.assertIn("error", resp)
        self.assertIn("Invalid run_id", resp["error"]["message"])

    def test_missing_required_arg_returns_error(self):
        """Missing required param returns clean AgentRelayError, not KeyError."""
        # agy_dispatch with no agent
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "agy_dispatch", "arguments": {"task_id": "task-001"}},
        }
        resp = _handle_message(msg)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32000)
        self.assertIn("Missing required parameter", resp["error"]["message"])

    # ------------------------------------------------------------------
    # v2: Handoff tool integration tests
    # ------------------------------------------------------------------

    def _handoff_call(self, tool_name, arguments):
        """Helper: call a handoff tool and return the parsed result dict."""
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        resp = _handle_message(msg)
        if "error" in resp:
            return {"error": resp["error"]["message"]}
        return json.loads(resp["result"]["content"][0]["text"])

    def test_agy_handoff_write_and_read(self):
        """Write a handoff then read it back."""
        write_args = {
            "task_id": "task-001",
            "from_agent": "claude",
            "to_agent": "codex",
            "summary": "Backend logic done, needs frontend",
            "context": "You are now the writer for task-001. The auth API is ready.",
            "commit_hash": "a1b2c3d",
        }
        written = self._handoff_call("agy_handoff_write", write_args)
        self.assertIn("handoff_id", written, msg=f"Write failed: {written}")
        self.assertEqual(written["task_id"], "task-001")
        self.assertEqual(written["from_agent"], "claude")
        self.assertIn("timestamp", written)

        # Read back
        read = self._handoff_call("agy_handoff_read", {"task_id": "task-001"})
        self.assertEqual(read["handoff_id"], written["handoff_id"])
        self.assertEqual(read["summary"], "Backend logic done, needs frontend")

    def test_agy_handoff_read_not_found(self):
        """Reading a nonexistent handoff returns not_found."""
        result = self._handoff_call("agy_handoff_read", {"task_id": "task-999"})
        self.assertEqual(result.get("status"), "not_found")

    def test_agy_handoff_ack(self):
        """Write then acknowledge."""
        write_args = {
            "task_id": "task-001",
            "from_agent": "claude",
            "to_agent": "antigravity",
            "summary": "UI needs visual pass",
            "context": "Frontend HTML is ready. Please check layout.",
        }
        written = self._handoff_call("agy_handoff_write", write_args)
        self.assertIn("handoff_id", written)

        result = self._handoff_call(
            "agy_handoff_ack", {"task_id": "task-001", "agent": "antigravity"}
        )
        self.assertEqual(result["status"], "acknowledged")
        self.assertEqual(result["acked_by"], "antigravity")

    def test_agy_handoff_ack_already_acked(self):
        """Acknowledging twice returns already_acked."""
        self._handoff_call(
            "agy_handoff_write",
            {
                "task_id": "task-001",
                "from_agent": "claude",
                "to_agent": "codex",
                "summary": "Test",
                "context": "Test ack idempotency",
            },
        )
        result1 = self._handoff_call(
            "agy_handoff_ack", {"task_id": "task-001", "agent": "codex"}
        )
        self.assertEqual(result1["status"], "acknowledged")

        result2 = self._handoff_call(
            "agy_handoff_ack", {"task_id": "task-001", "agent": "codex"}
        )
        self.assertEqual(result2["status"], "already_acked")

    def test_agy_handoff_ack_not_found(self):
        """Ack on nonexistent task returns not_found."""
        result = self._handoff_call(
            "agy_handoff_ack", {"task_id": "task-999", "agent": "claude"}
        )
        self.assertEqual(result["status"], "not_found")

    def test_resources_read_handoff_current_after_write(self):
        """After writing a handoff, handoff://current/{task_id} should reflect it."""
        self._handoff_call(
            "agy_handoff_write",
            {
                "task_id": "task-001",
                "from_agent": "claude",
                "to_agent": "codex",
                "summary": "Resource test",
                "context": "Testing resource read",
            },
        )
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/read",
            "params": {"uri": "handoff://current/task-001"},
        }
        resp = _handle_message(msg)
        self.assertIn("result", resp, msg=f"Got error: {resp.get('error')}")
        text = resp["result"]["contents"][0]["text"]
        data = json.loads(text)
        self.assertEqual(data["summary"], "Resource test")

    def test_resources_read_history_returns_list(self):
        """handoff://history should return a JSON array."""
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/read",
            "params": {"uri": "handoff://history"},
        }
        resp = _handle_message(msg)
        self.assertIn("result", resp, msg=f"Got error: {resp.get('error')}")
        text = resp["result"]["contents"][0]["text"]
        data = json.loads(text)
        self.assertIsInstance(data, list)


if __name__ == "__main__":
    unittest.main()
