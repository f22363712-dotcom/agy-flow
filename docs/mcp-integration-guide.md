# agy-flow MCP Integration Guide

**Version**: 1.0 | **Last updated**: 2026-07-13

## Overview

agy-flow provides an MCP server (Model Context Protocol) that exposes its
core capabilities as tools.  Any MCP-compatible client — Claude Desktop,
Claude Code, VS Code extensions — can invoke agy-flow operations.

The server communicates over **stdin/stdout** using **JSON-RPC 2.0**.

---

## Starting the MCP Server

### CLI

```bash
agy-flow mcp
```

Or directly:

```bash
python -m agy_flow.mcp_server
```

The server reads a JSON-RPC message per line from stdin and writes one
response per line to stdout.  It is designed to be launched as a
subprocess by an MCP client.

---

## Configuring MCP Clients

### Claude Code (`~/.claude/settings.json` or `.claude/settings.local.json`)

```json
{
  "mcpServers": {
    "agy-flow": {
      "command": "python",
      "args": ["-m", "agy_flow.mcp_server"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

### VS Code / Other MCP Hosts

Use the same server definition; the exact configuration key depends on the
host.  The core parts are:

| Field | Value |
|---|---|
| `command` | `python` |
| `args` | `["-m", "agy_flow.mcp_server"]` |
| `cwd` | Your project root (where `.agents/` lives) |

---

## Available Tools

| Tool | Description |
|---|---|
| `agy_create_task` | Create a new task with capability-aware routing |
| `agy_route_task` | Get the routing plan for a task title or existing task |
| `agy_auto_dispatch` | Capability-aware auto dispatch (with dry-run mode) |
| `agy_dispatch` | Dispatch a task to a specific agent |
| `agy_continue_run` | Continue after a writer run — dispatch a reviewer |
| `agy_quality` | Evaluate the quality gate for a task |
| `agy_finalize` | Finalise a task after quality gate passes |
| `agy_status` | Get a comprehensive task status summary |
| `agy_doctor` | Run a full system health check |

---

## Example Workflow

### 1. Create a task

```
Call: agy_create_task("Implement user login API")
→ { "task_id": "task-001", "agent": "claude", ... }
```

### 2. View the route

```
Call: agy_route_task({ "task_id": "task-001" })
→ { "primary": "claude", "fallbacks": [...], "reviewers": [...], ... }
```

### 3. Auto-dispatch (dry run)

```
Call: agy_auto_dispatch({ "task_id": "task-001", "dry_run": true })
→ { "status": "dry_run", "selected_agent": "claude", ... }
```

### 4. Dispatch a writer

```
Call: agy_dispatch({ "task_id": "task-001", "agent": "deepseek", "mock": true })
→ { "status": "success", "run_id": "run-...", ... }
```

### 5. Continue with reviewer

```
Call: agy_continue_run({ "run_id": "run-...", "mock": true })
→ { "status": "continued", "selected_reviewer": "codex", ... }
```

### 6. Check quality

```
Call: agy_quality({ "task_id": "task-001" })
→ { "ready": true, "blocking_issues": [], ... }
```

### 7. Finalize

```
Call: agy_finalize({ "task_id": "task-001", "dry_run": false })
→ { "status": "submitted", ... }
```

---

## Error Handling

All tools return structured JSON.  If an error occurs:

```json
{
  "isError": true,
  "content": [
    { "type": "text", "text": "Error message here" }
  ]
}
```

The MCP server never crashes.  Internal errors are caught and returned as
JSON-RPC error responses with code `-32603`.

---

## Protocol Notes

- **Transport**: stdin/stdout, one JSON object per line (newline-delimited).
- **Protocol version**: `2024-11-05`
- **Capabilities**: `tools` only (no resources, no prompts).
- **Initialization**: The client sends `initialize` → server responds with capabilities → client sends `notifications/initialized`.

---

## Verified Client Trial

A simulated MCP client trial was run using `scripts/mcp_client_smoke.py`. All steps passed.

### How to Run

```bash
python scripts/mcp_client_smoke.py
```

The script creates a temporary project, starts the MCP server, sends a sequence
of JSON-RPC messages, validates responses, and outputs a JSON report.

### How to Interpret Results

- Each step shows `[PASS]`, `[FAIL]`, or `[WARN]`.
- The final summary shows `"overall": "pass"` if all required steps succeeded.
- A JSON report with step details is printed at the end.

Common success output:
```
  [PASS] 0. init_temp_project 
  [PASS] 1. start_server 
  [PASS] 2. initialize 
  [PASS] 3. notification
  [PASS] 4. tools/list 9 tools
  [PASS] 5. agy_doctor healthy=True
  ...
  "overall": "pass"
```

### Common Failure Reasons

| Symptom | Likely Cause | Fix |
|---|---|---|
| `Server closed stdout (rc=2)` | `agy-flow.py` not found in CWD | Use absolute path to agy-flow.py |
| Non-JSON line in stdout (e.g. "Executing: git...") | `run_cmd` logging to stdout | This was fixed in v1; update agy_flow/git_ops.py |
| `tools/list` returns 0 tools | Server started in wrong directory | Ensure cwd contains `.agents/` |
| `python` not found | Python not in PATH | Use `sys.executable` or full path |
| Timeout on communicate | MCP server waiting for stdin | Ensure stdin is flushed and closed |
| MCP Client reports "Method not found" | Client using wrong protocol version | Use `"protocolVersion": "2024-11-05"` |

For the full trial report, see `docs/mcp-client-trial-report.md`.

## Security

- The MCP server runs with the same permissions as the user who starts it.
- No API keys are stored in the server process.
- No GUI is launched by any tool.
- All file operations are confined to the project root and its worktrees.
