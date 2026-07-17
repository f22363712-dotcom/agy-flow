# Agent Output Contract — agent-relay

**Version**: 1.0 | **Last updated**: 2026-07-13

## Purpose

When an external CLI agent (Claude, Gemini, etc.) or an LLM adapter (DeepSeek)
completes its work, agent-relay parses the agent's free-text response into a
structured ``parsed_output`` that drives the next action — such as
automatically dispatching a reviewer.

Agents are **encouraged** to embed a JSON block inside their Markdown output,
but the system never crashes on malformed or missing JSON.

---

## Recommended Output Format

At the end of the agent's response, include a fenced JSON block:

````markdown
任务已完成，下面是结构化结果：

```json
{
  "status": "completed",
  "summary": "Implemented login validation fix.",
  "changes": ["Updated login form validation", "Added regression test"],
  "files_touched": ["src/login.py", "test_login.py"],
  "tests_run": ["python test_login.py"],
  "risks": ["Need manual check for edge-case OAuth login"],
  "next_action": "review"
}
```
````

---

## Field Reference

| Field | Type | Required | Default | Values |
|---|---|---|---|---|
| `status` | string | yes | `unknown` | `completed`, `needs_review`, `blocked`, `failed`, `unknown` |
| `summary` | string | yes | `""` | Free-text one-line summary |
| `changes` | string[] | no | `[]` | Descriptions of each change made |
| `files_touched` | string[] | no | `[]` | File paths relative to project root |
| `tests_run` | string[] | no | `[]` | Test commands that were executed |
| `risks` | string[] | no | `[]` | Risk items the reviewer should check |
| `next_action` | string | yes | `manual` | `review`, `revise`, `submit`, `manual`, `none` |

### Status meanings

| Status | Meaning | Next expected action |
|---|---|---|
| `completed` | Work done, ready for review | → `review` |
| `needs_review` | Same as completed, explicit review request | → `review` |
| `blocked` | Cannot proceed — dependency or decision needed | → `manual` |
| `failed` | Task attempted but failed | → `manual` or `revise` |
| `unknown` | No structured JSON provided | → `manual` |

### next_action meanings

| Value | When to use |
|---|---|
| `review` | Writer is done and wants a reviewer to inspect |
| `revise` | Writer encountered issues and needs to revise later |
| `submit` | Work is ready for agent-relay submit (no review needed) |
| `manual` | Requires human decision before continuing |
| `none` | No further action required |

---

## Writer Guidelines

When acting as **writer** (role = `"writer"`):

1. Perform the task in the worktree per usual.
2. At the end of your response, include a JSON block per the format above.
3. Set `status` to `"completed"` if you finished the work.
4. Set `next_action` to `"review"` to trigger an automatic reviewer dispatch.
5. List `files_touched` and `tests_run` so the reviewer knows what to check.
6. If blocked, set `status: "blocked"` and explain why in `summary`.

## Reviewer Guidelines

When acting as **reviewer** (role = `"reviewer"`):

1. Read the writer's output and inspect the changes in the worktree.
2. At the end of your response, include a JSON block:
   - `status`: `"completed"` if the code looks good, `"needs_revision"` if issues found.
   - `summary`: Overall assessment.
   - `risks`: Remaining concerns.
   - `next_action`: `"submit"` if approved, `"revise"` if changes needed.

---

## Parse Behaviour (for system implementors)

The parser in `agent_relay/output_parser.py`:

1. Scans the agent output for a `` ```json `` fenced code block.
2. Parses the JSON inside — if valid, merges with defaults.
3. If no valid JSON block is found, returns a safe fallback:
   ```json
   {
     "status": "unknown",
     "summary": "(first 200 chars of output)",
     "changes": [], "files_touched": [], "tests_run": [], "risks": [],
     "next_action": "manual",
     "parse_error": "No valid JSON block found"
   }
   ```
4. The parser **never raises an exception**.
