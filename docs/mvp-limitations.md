# agent-relay MVP Limitations v1

This document records the known limitations of the current MVP.

---

## 1. Human-in-Loop Agents

**Codex and Antigravity** are still **human-in-loop handoff** only.

- Dispatching to `codex` or `antigravity` does **not** launch a VS Code window or desktop agent.
- The adapter updates `.agents/current_task.json` and prints a handoff instruction.
- A human must manually open the worktree in the appropriate tool.

**Planned**: Future versions will add deeper integration (IPC, protocol adapters).

---

## 2. CLI Agent Dependencies

**Claude Code** and **Gemini CLI** must be installed on the system PATH for the CLI adapters to work.

- If the CLI is not installed, `dispatch --agent claude` returns `unavailable`.
- The system never crashes, but the agent won't run.
- Use `agent-relay doctor` or `agent-relay probe claude` to check availability.

---

## 3. Agent Output Contract Adherence

The output parser (`parse_agent_output`) expects a JSON block in the agent's response.

- If the agent does not include a ` ```json ``` ` block, the output is treated as `unknown`.
- The system never crashes on malformed output, but parsed fields will be empty.
- Prompt engineering is required to encourage agents to follow the contract.

---

## 4. Dashboard Scope

The Dashboard is a **simple control console**, not a full IDE.

- It provides task CRUD, dispatch, runs, state, and quality gate views.
- It does not provide file editing, terminal, or git operations.
- The UI is embedded HTML/JS, suitable for local `localhost` use.

---

## 5. No Bypass of API/Subscription Limits

agent-relay does **not** bypass API rate limits, subscription tiers, or platform restrictions of any agent runtime.

- DeepSeek calls go through the official OpenAI-compatible API and require a valid API key.
- Claude Code requires a valid Claude subscription.
- Gemini CLI requires a valid Google account with Gemini access.
- The system merely orchestrates and records; it does not proxy or circumvent.

---

## 6. Local-First Architecture

agent-relay is designed for **local, single-user** use.

- State files, run records, and task artifacts live on the local filesystem.
- There is no built-in multi-user, team sync, or server deployment.
- The Gateway is a single-threaded HTTP server for local Dashboard access.

---

## 7. No Persistent Agent State

Each dispatch is independent. The system does not maintain a long-lived agent process.

- CLI agents are invoked per-dispatch and terminate after producing output.
- Human-in-loop agents receive a guard file update but no persistent connection.
- There is no daemon or background watcher.

---

## 8. Test Isolation

All tests run in `TemporaryDirectory` and do not touch the real project.

- This is intentional: the MVP is designed for safe experimentation.
- Real project state is never modified during tests.
