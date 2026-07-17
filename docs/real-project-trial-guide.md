# agent-relay Real Project Trial Guide

This guide walks you through using agent-relay in a real software project.

---

## Prerequisites

- Python 3.10+
- Git installed and available on PATH
- A project directory (existing or new)

## Step 1: Initialize

```bash
cd your-project
agent-relay init
```

This creates:
- `.agents/config.json` — project configuration
- `.agents/tasks/board.md` — task board
- `.agents/tasks/task_template.md` — task template
- `.agents/costs.json` — cost tracking
- `.gitignore` entries for agent-relay artifacts

## Step 2: Create a Task

```bash
agent-relay create "Implement user login API"
```

Or specify an agent:
```bash
agent-relay create "Design login page" --agent antigravity
```

This creates:
- `.agents/tasks/task-001.md` — task specification
- `.agents/tasks/task-001.plan.json` — routing plan
- A row in `board.md`

## Step 3: Preview the Route

```bash
agent-relay route "Implement user login API"
agent-relay route-task task-001
```

Shows the capability-aware routing plan: primary agent, fallbacks, reviewers.

## Step 4: Auto Dispatch (Dry Run First)

```bash
agent-relay auto task-001 --dry-run
```

This shows what would happen without actually dispatching.

## Step 5: Dispatch a Writer

For LLM agents (DeepSeek):
```bash
agent-relay dispatch task-001 --agent deepseek --mock
```

For CLI agents (Claude, Gemini):
```bash
agent-relay dispatch task-001 --agent claude
```

For human-in-loop (Codex, Antigravity):
```bash
agent-relay dispatch task-001 --agent codex
```
This updates `.agents/current_task.json` and gives you instructions.

## Step 6: Dispatch a Reviewer

After the writer completes, continue the review loop:
```bash
agent-relay continue run-xxxx --mock
```

Or use auto-dispatch to let the system decide:
```bash
agent-relay auto task-001 --mock
```

## Step 7: Check Quality Gate

```bash
agent-relay quality task-001
agent-relay quality task-001 --json
```

## Step 8: Finalize

```bash
agent-relay finalize task-001 --dry-run
agent-relay finalize task-001
```

This runs the quality gate, then transitions the task to `submitted`.

## Step 9: Check Status

```bash
agent-relay status task-001   # detailed task summary
agent-relay doctor            # system health check
agent-relay agents            # agent availability
```

---

## Workflow Diagram

```
create → route → auto-dispatch
                     ↓
            ┌── dispatch writer
            │       ↓
            │   parse output
            │       ↓
            │   continue reviewer
            │       ↓
            │   quality gate
            │       ↓
            └── finalize
```

---

## Troubleshooting

### "CLI not found"
Install the CLI tool or use `--mock` for testing:
```bash
agent-relay dispatch task-001 --agent deepseek --mock
```

### "Task not found"
Ensure the task ID is correct:
```bash
agent-relay status
agent-relay status task-001
```

### "Quality gate blocked"
Run `agent-relay quality` to see specific blocking issues.
Common causes:
- No writer run yet
- Reviewer requested revision
- Task is in blocked state

### "Agent unavailable"
Run `agent-relay doctor` or `agent-relay agents` to check availability.
Run `agent-relay probe all` for detailed connector status.

### Gateway not starting
Check port availability:
```bash
agent-relay serve --port 8001
```
