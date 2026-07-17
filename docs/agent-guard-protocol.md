# Agent Guard Protocol — agy-flow

**Version**: 1.0 | **Last updated**: 2026-07-12

## Overview

The Agent Guard Protocol is the access-control mechanism that prevents unauthorised agent runtimes (Codex, Claude, Antigravity, DeepSeek) from operating on tasks they are not assigned to. Each agent reads `.agents/current_task.json` before performing any work and decides whether it is allowed to proceed based on the **writer/reviewer** model.

---

## Guard File Location

```
.agents/current_task.json
```

This file lives in the **project root** (for worktree-less operations like review) and is also copied into **each worktree** at `.agents/current_task.json` during `agy-flow start`.

---

## Guard File Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `agent` | string | yes | **Legacy** — the single active agent name. Always kept for backward compatibility with older agent instructions that only read this field. |
| `writer` | string | yes | The agent currently holding **write access**. Only this agent may modify files, run tests, or push code. |
| `reviewers` | string[] | yes | List of agents that have **read-only / review access**. These agents may read code and submit reviews, but must not modify files. |
| `mode` | string | yes | Current guard mode: `"handoff"` (active development handover), `"review"` (code review phase), or others as defined by workflow. |
| `role` | string | yes | `"writer"` or `"reviewer"` — reflects the current acting role of `agent`. |
| `task_id` | string | no | Active task ID, if known. |
| `title` | string | no | Task title for display purposes. |
| `timestamp` | string | yes | ISO-format timestamp of last update. |

### Example — Writer has full access

```json
{
    "agent": "claude",
    "writer": "claude",
    "reviewers": ["Codex", "antigravity"],
    "mode": "handoff",
    "role": "writer",
    "task_id": "task-012",
    "timestamp": "2026-07-12 12:00:00"
}
```

- `claude` is **writer** → has write access.
- `Codex` and `antigravity` are **reviewers** → may read and review, but not write.

### Example — Review mode

```json
{
    "agent": "Codex",
    "writer": "claude",
    "reviewers": ["Codex", "antigravity"],
    "mode": "review",
    "role": "reviewer",
    "task_id": "task-012",
    "timestamp": "2026-07-12 12:05:00"
}
```

- `claude` remains **writer** (original author).
- `Codex` is now the active **reviewer** → may read and analyse, but not modify files.

---

## Decision Logic

Every agent MUST run this check before any operation:

```
1. Read .agents/current_task.json
2. IF writer exists AND writer == MY_NAME → AUTHORIZED (full write access)
3. ELSE IF writer exists AND MY_NAME in reviewers → AUTHORIZED (read-only / review only)
4. ELSE IF writer is absent AND agent == MY_NAME → AUTHORIZED (legacy fallback, full access)
5. ELSE → UNAUTHORIZED → print rejection message + STOP
```

### Pseudocode

```
def check_guard():
    guard = read_json(".agents/current_task.json")
    writer = guard.get("writer")
    reviewers = guard.get("reviewers", [])
    agent_legacy = guard.get("agent")

    if writer is not None:
        if writer == MY_NAME:
            return AUTHORIZED_WRITER
        elif MY_NAME in reviewers:
            return AUTHORIZED_REVIEWER
    elif agent_legacy == MY_NAME:
        return AUTHORIZED_LEGACY

    print(f"[Routing Stop] This task is assigned to {writer or agent_legacy}, not {MY_NAME}.")
    exit_operation()
```

---

## CLI Usage

### Assign as writer

```bash
agy-flow assign claude --role writer --reviewer codex --reviewer antigravity
```

Sets `writer=claude`, adds `codex` and `antigravity` to `reviewers`.

### Assign as reviewer

```bash
agy-flow assign codex --role reviewer --mode review
```

Sets `role=reviewer`, adds `codex` to `reviewers` (keeping the existing writer).  
The legacy `agent` field is updated to `codex` so old guard logic still works.

### Assign with task ID

```bash
agy-flow assign antigravity --task-id task-015
```

Writes `task_id: "task-015"` alongside the guard metadata.

---

## Gateway API — `POST /assign`

The HTTP gateway also supports the full protocol:

**Request:**
```json
{
    "agent": "codex",
    "task_id": "task-012",
    "role": "reviewer",
    "reviewers": ["antigravity"],
    "mode": "review"
}
```

**Response:**
```json
{
    "status": "success",
    "agent": "codex",
    "writer": "claude",
    "reviewers": ["Codex", "antigravity"],
    "mode": "review",
    "role": "reviewer",
    "task_id": "task-012",
    "metadata": { ... }
}
```

---

## Cross-Agent Behaviour

### Claude (reads `writer == "claude"` or `agent == "claude"`)
- **As writer**: full development, test-running, submission.
- **As reviewer** (`"claude" in reviewers`): may inspect code and produce reviews, but must not edit.

### Codex (reads `writer == "Codex"` or `agent == "Codex"`)
- **Case-sensitive**: `AGENTS.md` checks `"Codex"`, `CODEX.md` checks `"codex"`.
- **As writer**: VS Code worktree launch, editing, running `Ctrl+Shift+B`.
- **As reviewer**: read and review only.

### Antigravity (reads `writer == "antigravity"` or `agent == "antigravity"`)
- **As writer**: visual review, test optimisation, code changes.
- **As reviewer**: UI audit, accessibility checks, analysis only.

### DeepSeek (LLM-only — does not read guards)
- DeepSeek is invoked via `agy-flow ask deepseek` or `POST /ask/deepseek` and does not read `current_task.json`. The calling agent is responsible for authorising the request.

---

## Backward Compatibility

The legacy `"agent"` field is always written alongside the new `"writer"`/`"reviewers"` fields.  
Old guard instructions that only check:

```
if agent != "Codex": stop
```

will continue to work — `agent` is always set to the canonical name of the last assigned agent.

---

## Testing

The test suite in `test_serve.py` covers:

- `test_assign_endpoint` — basic assign with `status == "success"`
- `test_assign_writer` — assign with explicit `role=writer` and `reviewers`
- `test_assign_reviewer` — assign as reviewer preserves existing writer
- `test_assign_legacy_agent_field` — legacy `agent` field is always present

Run tests:

```bash
python test_serve.py
```
