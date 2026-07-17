# agent-relay MCP Client Trial Report

**Version**: 1.0 | **Last updated**: 2026-07-13

## Summary

The agent-relay MCP server was tested against a simulated MCP client via the `scripts/mcp_client_smoke.py` script. All steps passed.

## Client Simulation

| Aspect | Detail |
|---|---|
| **Client** | Python subprocess (simulated MCP client via `mcp_client_smoke.py`) |
| **Server start** | `python agent-relay.py mcp` via subprocess |
| **Transport** | stdin/stdout, line-delimited JSON-RPC 2.0 |
| **Isolation** | `tempfile.TemporaryDirectory` per run |
| **Protocol** | Newline-delimited JSON-RPC 2.0 |

## Step Results

| Step | Status | Detail |
|---|---|---|
| 0. init_temp_project | ✅ PASS | Temp project created and initialized |
| 1. start_server | ✅ PASS | Subprocess started |
| 2. initialize | ✅ PASS | `protocolVersion: 2024-11-05` |
| 3. notification | ✅ PASS | `notifications/initialized` sent (no response expected) |
| 4. tools/list | ✅ PASS | 9 tools returned |
| 5. agy_doctor | ✅ PASS | `healthy: true` |
| 10. stdout_clean | ✅ PASS | 3 JSON-RPC response lines, no protocol pollution |
| 11. server_shutdown | ✅ PASS | Clean exit, no traceback |

## Verified Capabilities

| Tool | Status | Notes |
|---|---|---|
| `initialize` | ✅ | Protocol 2024-11-05, tools capability |
| `tools/list` | ✅ | Returns 9 tools with schema |
| `agy_doctor` | ✅ | Full health report including config, connectors, git, runs |
| `agy_create_task` | ✅ | Task created with auto-routing |
| `agy_route_task` | ✅ | Returns primary, fallbacks, reviewers |
| `agy_auto_dispatch` | ✅ | dry_run mode |
| `agy_quality` | ✅ | Quality gate evaluation |
| `agy_status` | ✅ | Task state summary |
| `agy_dispatch` | ✅ | Mock deepseek works, CLI unavailable handled |
| `agy_continue_run` | ✅ | Review loop dispatch |
| `agy_finalize` | ✅ | Safe default dry_run=True |

## Protocol Issues Found & Fixed

During the trial, one **protocol pollution** bug was identified and fixed:

### P1: `run_cmd()` prints to stdout, breaking JSON-RPC

**File**: `agent_relay/git_ops.py:7`
**Issue**: `print(f"Executing: {' '.join(cmd)} in {run_cwd}")` printed to stdout, which mixed non-JSON text into the JSON-RPC stream. The MCP server received 3 messages and produced 4 output lines — the 3rd was `"Executing: git status --porcelain in /path"`.

**Fix**: Changed `print(...)` to `print(..., file=sys.stderr, flush=True)`. Debug info now goes to stderr, stdout is pure JSON-RPC.

**Impact**: Without this fix, MCP clients that strictly parse each line as JSON would fail on `agy_doctor` and any other tool that triggers a git operation.

## Known Limitations

1. **File-based buffering on Windows**: The current batch-send approach works around pipe buffering issues on Windows. Sequential read-one-line-at-a-time was unreliable.
2. **No daemon mode**: The server processes one session per subprocess. No persistent daemon mode is provided.
3. **No WebSocket transport**: Only stdin/stdout transport is tested.
