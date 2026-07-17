# Agent Execution Contract — agy-flow

**Version**: 1.0 | **Last updated**: 2026-07-13

## Purpose

When agy-flow dispatches a task to an external CLI agent (Claude Code, Gemini CLI, etc.), it passes a structured task-context prompt. This document defines what that prompt contains and what the external agent is expected to do (and not do).

---

## Prompt Contract

Every dispatch to a CLI agent is built by `build_agent_prompt()` in `agy_flow/executors.py`. The prompt contains these sections:

### 1. Header

```
You are assigned to work on task {task_id} inside agy-flow.
```

Identifies the task and the framework.

### 2. Role

```
You are acting as a **writer** for this task.
```

or

```
You are acting as a **reviewer** for this task.
You may read code and produce reviews, but must NOT modify files.
```

The role is determined by the routing plan:

| `mode`  | `role`     | Allowed operations           |
| ------- | ---------- | ---------------------------- |
| `write` | `writer`   | Full write access            |
| `review`| `reviewer` | Read-only, review only       |
| `handoff`| `writer`  | Full write (human handoff)   |

### 3. Task Specification

The full contents of `.agents/tasks/{task_id}.md` are included so the agent knows the task requirements, acceptance criteria, and any historical context.

### 4. Routing Plan

If a saved plan exists at `.agents/tasks/{task_id}.plan.json`, the full JSON is included so the agent understands the multi-agent pipeline, confidence, and fallback strategy.

### 5. Current Route

A compact JSON block showing the task ID, role, and assigned agent:

```json
{
  "task_id": "task-001",
  "role": "writer",
  "agent": "claude"
}
```

### 6. Workflow Requirements

Always present at the end of every prompt:

1. Read `.agents/current_task.json` to verify your assignment.
2. Work inside the worktree directory only.
3. Do **NOT** modify files outside the worktree.
4. When finished, run: `agy-flow submit {task_id}`
5. Do **NOT** commit or push to the main branch directly.

---

## CLI Agent Behavioural Contract

When a CLI agent is invoked via `run_cli_agent()` in `agy_flow/executors.py`, the following contract is expected:

| Aspect | Expectation |
|---|---|
| **Input** | Prompt is passed via stdin (`-p` flag for claude) |
| **Output** | stdout is the agent's response; stderr is diagnostics |
| **Exit code** | 0 = success, non-zero = error |
| **Timeout** | Default 120 seconds; configurable via `timeout` kwarg |
| **Side effects** | Agent MUST NOT modify files outside the assigned worktree |
| **Guard check** | Agent MUST read `.agents/current_task.json` before making changes |
| **Submission** | Agent MUST run `agy-flow submit {task_id}` when done (writer mode) |

---

## Security Rules

1. **No `shell=True`**: `run_cli_agent()` never sets `shell=True`; commands are always a list of strings.
2. **No GUI launch**: The executor never launches VS Code, desktop apps, or browser windows.
3. **PATH-scoped**: The agent binary must be on `PATH` or the command is rejected as `unavailable`.
4. **Timeout enforced**: Long-running agents are killed after the configured timeout (default 120 s).

---

## Example Prompt (abridged)

```
You are assigned to work on task task-012 inside agy-flow.

## Task: task-012 - Implement user login API

### Role
You are acting as a **writer** for this task.
You have full write access to the worktree.

### Task Specification
# Task: task-012 - Implement user login API
...

### Routing Plan
{
  "task_type": "backend",
  "selected_agent": "claude",
  "recommended_pipeline": [{"agent": "claude", "role": "implementer", ...}]
}

### Current Route
{"task_id": "task-012", "role": "writer", "agent": "claude"}

### Workflow Requirements
1. Read .agents/current_task.json to verify your assignment.
2. Work inside the worktree directory only.
3. Do NOT modify files outside the worktree.
4. When finished, run: agy-flow submit task-012
5. Do NOT commit or push to the main branch directly.
```

---

## Registering a New CLI Agent

1. Add a `CliAgentAdapter(agent_name, cli_command)` to the adapter registry in `adapter.py`.
2. Add a connector in `connectors.py` so the system knows if the CLI is on `PATH`.
3. Add the agent to `AGENT_META` in `connectors.py` with appropriate capabilities.
4. Create a test case in `test_executors.py` with mocked `subprocess.run`.
