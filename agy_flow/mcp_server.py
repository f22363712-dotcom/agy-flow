"""MCP Server v2 — expose agy-flow core capabilities as MCP tools + resources.

v2  adds  ``agy_handoff_write`` / ``agy_handoff_read`` / ``agy_handoff_ack``
tools and three  MCP resources  (``handoff://current/{task_id}``,
``handoff://history``,  ``board://tasks``) so  any MCP  client  (Claude Code,
Codex CLI, Antigravity, …) can share a persistent handoff blackboard.

Runs over stdin/stdout (JSON-RPC 2.0).  Start with ``agy-flow mcp`` or
directly: ``python -m agy_flow.mcp_server``.
"""

import json
import re
import sys
import traceback
from dataclasses import asdict
from pathlib import Path

from agy_flow.errors import AgyFlowError

_RE_TASK_ID = re.compile(r"^task-\d{3,}$")
_RE_RUN_ID = re.compile(r"^run-[a-f0-9]{12}$")
_RE_HANDOFF_CURRENT = re.compile(r"^handoff://current/(task-\d{3,})$")
_RE_HANDOFF_HISTORY = re.compile(r"^handoff://history(\?limit=(\d+))?$")

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "name": "agy_create_task",
        "description": "Create a new task with capability-aware routing plan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Task title or natural-language description",
                },
                "body": {
                    "type": "string",
                    "description": "Optional extended task body",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "agy_route_task",
        "description": "Return the capability-aware routing plan for a task title or task ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Task title (ignored if task_id given)",
                },
                "task_id": {
                    "type": "string",
                    "description": "Existing task ID, e.g. task-001",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "agy_auto_dispatch",
        "description": "Capability-aware auto dispatch for a task.  Default dry_run=True for safety.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID, e.g. task-001"},
                "dry_run": {
                    "type": "boolean",
                    "description": "Only compute route, don't dispatch (default True)",
                },
                "mock": {"type": "boolean", "description": "Mock mode for DeepSeek"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "agy_dispatch",
        "description": "Dispatch a task to a specific agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID, e.g. task-001"},
                "agent": {
                    "type": "string",
                    "description": "Agent name",
                    "enum": ["deepseek", "claude", "gemini", "codex", "antigravity"],
                },
                "role": {
                    "type": "string",
                    "description": "Role: writer or reviewer",
                    "enum": ["writer", "reviewer"],
                },
                "mock": {"type": "boolean", "description": "Mock mode for DeepSeek"},
            },
            "required": ["task_id", "agent"],
        },
    },
    {
        "name": "agy_continue_run",
        "description": "Continue after a writer run — dispatch a reviewer if warranted.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Run ID, e.g. run-xxxx"},
                "mock": {
                    "type": "boolean",
                    "description": "Mock mode for reviewer dispatch",
                },
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "agy_quality",
        "description": "Evaluate the quality gate for a task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID, e.g. task-001"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "agy_finalize",
        "description": "Finalise a task after quality gate passes.  Default dry_run=True for safety.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID, e.g. task-001"},
                "dry_run": {
                    "type": "boolean",
                    "description": "Only check quality gate, don't submit (default True)",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "agy_status",
        "description": "Return a comprehensive status summary for a task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID, e.g. task-001"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "agy_doctor",
        "description": "Run a full system health check.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # -- v2: Handoff blackboard tools ----------------------------------------
    {
        "name": "agy_handoff_write",
        "description": "Write a handoff context to the shared blackboard for a task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID, e.g. task-001"},
                "from_agent": {
                    "type": "string",
                    "description": "Current agent handing off",
                },
                "to_agent": {
                    "type": "string",
                    "description": "Target agent to receive",
                },
                "summary": {
                    "type": "string",
                    "description": "One-line handoff summary",
                },
                "context": {
                    "type": "string",
                    "description": "Full structured context / prompt for the next agent",
                },
                "commit_hash": {
                    "type": "string",
                    "description": "Optional current commit hash",
                },
            },
            "required": ["task_id", "from_agent", "to_agent", "summary", "context"],
        },
    },
    {
        "name": "agy_handoff_read",
        "description": "Read the latest handoff context for a task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID, e.g. task-001"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "agy_handoff_ack",
        "description": "Acknowledge a handoff, marking it as received.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID, e.g. task-001"},
                "agent": {
                    "type": "string",
                    "description": "Agent acknowledging the handoff",
                },
            },
            "required": ["task_id", "agent"],
        },
    },
]

# ---------------------------------------------------------------------------
# Resource definitions (MCP specification)
# ---------------------------------------------------------------------------

_RESOURCE_TEMPLATES = [
    {
        "uriTemplate": "handoff://current/{task_id}",
        "name": "Handoff Current (template)",
        "description": "Latest handoff context for a specific task.",
        "mimeType": "application/json",
    },
]

_STATIC_RESOURCES = [
    {
        "uri": "handoff://history",
        "name": "Handoff History",
        "description": "Recent handoff history across all tasks.",
        "mimeType": "application/json",
    },
    {
        "uri": "board://tasks",
        "name": "Task Board",
        "description": "Current task board overview with all task statuses.",
        "mimeType": "application/json",
    },
]


def _build_resource_list():
    """Build concrete resource list for ``resources/list``.

    Returns static resources plus concrete ``handoff://current/{task_id}`` URIs
    for every task that has a current handoff on disk.
    """
    resources = list(_STATIC_RESOURCES)

    # Add concrete handoff URIs from store
    try:
        store = _get_store()
        current_all = store.current_all()
        for task_id in sorted(current_all):
            resources.append(
                {
                    "uri": f"handoff://current/{task_id}",
                    "name": f"Handoff Current: {task_id}",
                    "description": f"Latest handoff context for {task_id}.",
                    "mimeType": "application/json",
                }
            )
    except Exception:
        pass  # store unavailable — return static resources only

    return resources


# ---------------------------------------------------------------------------
# Lazy store singleton (path-aware — rebuilds if AGENTS_DIR changes)
# ---------------------------------------------------------------------------

_store = None
_store_agents_dir = None


def _get_store():
    global _store, _store_agents_dir
    from agy_flow.config import AGENTS_DIR

    if _store is not None and str(_store_agents_dir) == str(AGENTS_DIR):
        return _store

    from agy_flow.mcp_handoff_store import HandoffStore

    _store = HandoffStore()
    _store_agents_dir = AGENTS_DIR
    return _store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require(args, key, label=None):
    """Require *key* in *args*, raising AgyFlowError if missing."""
    if key not in args:
        raise AgyFlowError(
            f"Missing required parameter: '{key}'. {label or ''}".strip()
        )
    return args[key]


def _validate_task_id(task_id):
    if not _RE_TASK_ID.match(str(task_id)):
        raise AgyFlowError(f"Invalid task_id format: '{task_id}'. Expected task-NNN.")
    return task_id


def _validate_run_id(run_id):
    if not _RE_RUN_ID.match(str(run_id)):
        raise AgyFlowError(
            f"Invalid run_id format: '{run_id}'. Expected run-xxxxxxxxxxxx."
        )
    return run_id


# ---------------------------------------------------------------------------
# Tool handler dispatch
# ---------------------------------------------------------------------------


def _handle_call(name, args):
    """Execute *name* with *args* and return a result dict.

    Returns ``{"content": [...]}`` on success or raises an exception.
    """
    from agy_flow.tasks import create_task
    from agy_flow.router import route_task_by_id, route_task
    from agy_flow.orchestrator import auto_dispatch_task
    from agy_flow.adapter import dispatch as adapter_dispatch
    from agy_flow.review_loop import continue_after_run
    from agy_flow.quality_gate import evaluate_task_quality
    from agy_flow.submit_pipeline import finalize_task
    from agy_flow.doctor import task_status, doctor

    if name == "agy_create_task":
        title = _require(args, "title", "A task title is required.")
        body = args.get("body", "")

        from types import SimpleNamespace

        ca = SimpleNamespace()
        ca.title = title
        ca.agent = None  # let create_task auto-route via classifier
        ca.desc = body

        result = create_task(ca)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, ensure_ascii=False),
                }
            ]
        }

    if name == "agy_route_task":
        task_id = args.get("task_id")
        title = args.get("title")
        if task_id:
            _validate_task_id(task_id)
            route = route_task_by_id(task_id)
        elif title:
            route = route_task(title)
        else:
            raise AgyFlowError("Provide task_id or title to route.")
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(route, indent=2, ensure_ascii=False),
                }
            ]
        }

    if name == "agy_auto_dispatch":
        task_id = _validate_task_id(_require(args, "task_id"))
        dry_run = args.get("dry_run", True)  # safe default
        mock = args.get("mock", False)
        result = auto_dispatch_task(task_id, dry_run=dry_run, mock=mock)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, ensure_ascii=False),
                }
            ]
        }

    if name == "agy_dispatch":
        task_id = _validate_task_id(_require(args, "task_id"))
        agent = _require(
            args, "agent", "One of: deepseek, claude, gemini, codex, antigravity"
        )
        role = args.get("role", "writer")
        mock = args.get("mock", False)
        result = adapter_dispatch(task_id, agent, mock=mock, role=role)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, ensure_ascii=False),
                }
            ]
        }

    if name == "agy_continue_run":
        run_id = _validate_run_id(_require(args, "run_id"))
        mock = args.get("mock", False)
        result = continue_after_run(run_id, mock=mock)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, ensure_ascii=False),
                }
            ]
        }

    if name == "agy_quality":
        task_id = _validate_task_id(_require(args, "task_id"))
        result = evaluate_task_quality(task_id)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, ensure_ascii=False),
                }
            ]
        }

    if name == "agy_finalize":
        task_id = _validate_task_id(_require(args, "task_id"))
        dry_run = args.get("dry_run", True)  # safe default
        result = finalize_task(task_id, dry_run=dry_run)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, ensure_ascii=False),
                }
            ]
        }

    if name == "agy_status":
        task_id = _validate_task_id(_require(args, "task_id"))
        result = task_status(task_id)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, ensure_ascii=False),
                }
            ]
        }

    if name == "agy_doctor":
        result = doctor()
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, ensure_ascii=False),
                }
            ]
        }

    # -- v2: Handoff tools (lazy imports to avoid polluting non-handoff calls) --

    if name == "agy_handoff_write":
        from agy_flow.mcp_handoff_store import HandoffContext

        store = _get_store()
        task_id = _validate_task_id(_require(args, "task_id"))
        from_agent = _require(args, "from_agent")
        to_agent = _require(args, "to_agent")
        summary = _require(args, "summary")
        context = _require(args, "context")
        commit_hash = args.get("commit_hash")

        ctx = HandoffContext(
            handoff_id="",  # store.write() will generate if empty
            task_id=task_id,
            from_agent=from_agent,
            to_agent=to_agent,
            summary=summary,
            context=context,
            commit_hash=commit_hash,
        )
        saved = store.write(ctx)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(asdict(saved), ensure_ascii=False, indent=2),
                }
            ]
        }

    if name == "agy_handoff_read":
        store = _get_store()
        task_id = _validate_task_id(_require(args, "task_id"))
        ctx = store.read(task_id)
        if ctx is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"status": "not_found", "task_id": task_id},
                            ensure_ascii=False,
                            indent=2,
                        ),
                    }
                ]
            }
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(asdict(ctx), ensure_ascii=False, indent=2),
                }
            ]
        }

    if name == "agy_handoff_ack":
        store = _get_store()
        task_id = _validate_task_id(_require(args, "task_id"))
        agent = _require(args, "agent")
        result = store.ack(task_id, agent)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(asdict(result), ensure_ascii=False, indent=2),
                }
            ]
        }

    raise AgyFlowError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Resource handler
# ---------------------------------------------------------------------------


def _handle_read_resource(uri: str) -> dict:
    """Return the MCP resource content for *uri*.

    Returns ``{"contents": [{"uri": ..., "mimeType": ..., "text": ...}]}``.
    """
    # handoff://current/{task_id}
    m = re.match(r"^handoff://current/(task-\d{3,})$", uri)
    if m:
        from agy_flow.mcp_handoff_store import HandoffContext

        task_id = m.group(1)
        ctx = _get_store().read(task_id)
        if ctx is None:
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {"status": "not_found", "task_id": task_id},
                            ensure_ascii=False,
                        ),
                    }
                ]
            }
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(asdict(ctx), ensure_ascii=False),
                }
            ]
        }

    # handoff://history[?limit=N]
    m = re.match(r"^handoff://history(\?limit=(\d+))?$", uri)
    if m:
        limit = int(m.group(2)) if m.group(2) else 5
        entries = _get_store().history(limit=limit)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(
                        [asdict(e) for e in entries], ensure_ascii=False
                    ),
                }
            ]
        }

    # board://tasks
    if uri == "board://tasks":
        from agy_flow.tasks import parse_board_rows

        rows = parse_board_rows()
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(rows, ensure_ascii=False),
                }
            ]
        }

    raise AgyFlowError(f"Unknown resource URI: {uri}")


# ---------------------------------------------------------------------------
# JSON-RPC message handling
# ---------------------------------------------------------------------------


def _handle_message(msg):
    """Process a single parsed JSON-RPC message and return a response dict.

    Returns ``None`` for notifications (no ``id``).
    """
    msg_id = msg.get("id")
    method = msg.get("method", "")
    params = msg.get("params", {})

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": _TOOLS}}

    if method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"resources": _build_resource_list()},
        }

    if method == "resources/read":
        uri = params.get("uri", "")
        try:
            result = _handle_read_resource(uri)
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}
        except AgyFlowError as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32002, "message": str(e)},
            }
        except Exception as e:
            traceback.print_exc()
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32603, "message": f"Resource read error: {e}"},
            }

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        try:
            result = _handle_call(name, arguments)
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}
        except AgyFlowError as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32000, "message": str(e)},
            }
        except Exception as e:
            traceback.print_exc()
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32603, "message": f"Internal error: {e}"},
            }

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "agy-flow-mcp", "version": "2.0.0"},
            },
        }

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None  # notification, no response

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def run_mcp_server():
    """Run the MCP server over stdin/stdout (JSON-RPC 2.0)."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue

        msg_id = msg.get("id")
        try:
            resp = _handle_message(msg)
        except Exception as e:
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32603, "message": f"Unhandled: {e}"},
            }

        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


def main():
    """Entry point for ``agy-flow mcp``."""
    run_mcp_server()


if __name__ == "__main__":
    main()
