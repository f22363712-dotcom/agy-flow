# Antigravity Global Project Guide

Welcome! This is the global project-wide guide for Google Antigravity.

## ⚠️ Agent Assignment Enforcement (CRITICAL)
Before executing any tasks, reading code, or performing operations, you MUST check the active task metadata:
1. Locate and read the file `.agents/current_task.json` in the workspace root.
2. Determine if you are authorized using the **writer/reviewer guard protocol**:
   - **Writer check**: If `"writer"` is `"antigravity"`, you have **full write access** — proceed with all operations.
   - **Reviewer check**: If `"writer"` is NOT `"antigravity"` but `"antigravity"` appears in `"reviewers"` (a list), you have **read-only / review access** — you may read code and perform review/analysis, but MUST NOT edit files or run destructive commands.
   - **Legacy fallback**: If `"writer"` is absent, fall back to the `"agent"` field — if `"agent"` is `"antigravity"`, you are authorized.
3. If none of the above conditions match, **YOU ARE NOT AUTHORIZED TO WORK ON THIS TASK**. Immediately stop all actions, DO NOT edit any files, and print a clear exit message:
   `[Routing Stop] This task is assigned to {writer} (writer, role={role}), not antigravity. Stopping.`
4. If authorized, proceed with the instructions below.

## Project Context
*   **Project Name**: multi_agent_collaboration
*   **Active Directory**: D:\multi_agent_collaboration
*   **Tech Stack**: Python 3.x, Git-Native workflow, Command-line scripts.

## Core Rules & Standards
1.  **Always respect the task board**: Check `.agents/tasks/board.md` for task statuses.
2.  **Verify before commit**: Always run tests (e.g. `python test_classify_task.py`) before submitting task branches.
3.  **Cost Awareness**: Be conscious of Token budgets. Log estimated/actual costs using `agent-relay cost log <task-id>`.
