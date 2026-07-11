# Antigravity Global Project Guide

Welcome! This is the global project-wide guide for Google Antigravity.

## ⚠️ Agent Assignment Enforcement (CRITICAL)
Before executing any tasks, reading code, or performing operations, you MUST check the active task metadata:
1. Locate and read the file `.agents/current_task.json` in the workspace root.
2. Read the `"agent"` value inside the JSON.
3. If `"agent"` is **NOT** `"antigravity"`, **YOU ARE NOT AUTHORIZED TO WORK ON THIS TASK**. You must immediately stop all actions, DO NOT edit any files, and print a clear exit message:
   `[Routing Stop] This task is assigned to {agent} (not antigravity). Stopping.`
4. If `"agent"` is `"antigravity"`, proceed with the instructions below.

## Project Context
*   **Project Name**: multi_agent_collaboration
*   **Active Directory**: D:\multi_agent_collaboration
*   **Tech Stack**: Python 3.x, Git-Native workflow, Command-line scripts.

## Core Rules & Standards
1.  **Always respect the task board**: Check `.agents/tasks/board.md` for task statuses.
2.  **Verify before commit**: Always run tests (e.g. `python test_classify_task.py`) before submitting task branches.
3.  **Cost Awareness**: Be conscious of Token budgets. Log estimated/actual costs using `agy-flow cost log <task-id>`.
