# Codex Global Project Guide

Welcome! This is the global project-wide guide for Codex.

## ⚠️ Agent Assignment Enforcement (CRITICAL)
Before executing any tasks, reading code, or performing file/command operations, you MUST check the active task metadata:
1. Locate and read the file `.agents/current_task.json` in the workspace root.
2. Determine if you are authorized using the **writer/reviewer guard protocol**:
   - **Writer check**: If `"writer"` is `"Codex"`, you have **full write access** — proceed with all operations.
   - **Reviewer check**: If `"writer"` is NOT `"Codex"` but `"Codex"` appears in `"reviewers"` (a list), you have **read-only / review access** — you may read code and perform review/analysis, but MUST NOT edit files or run destructive commands.
   - **Legacy fallback**: If `"writer"` is absent, fall back to the `"agent"` field — if `"agent"` is `"Codex"`, you are authorized.
3. If none of the above conditions match, **YOU ARE NOT AUTHORIZED TO WORK ON THIS TASK**. Immediately stop all actions, DO NOT edit any files, and print a clear exit message:
   `[Routing Stop] This task is assigned to {writer} (writer, role={role}), not Codex. Stopping.`
4. If authorized, proceed with the instructions below.

## agent-relay Integration
This project uses the agent-relay multi-agent collaboration framework.

## Task Submission Command
Once you complete the user's requirements and they are satisfied, you MUST run the following command in the VS Code integrated terminal to submit:
`agent-relay submit <task-id>`
(The active task ID is specified in `.agents/current_task.json`)
Alternatively, you can run the default VS Code Build task by pressing `Ctrl+Shift+B` to submit automatically.
