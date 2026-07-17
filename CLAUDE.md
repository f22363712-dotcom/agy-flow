# Claude Code Global Project Guide

Welcome! This is the global project-wide guide for Claude Code.

## ⚠️ Agent Assignment Enforcement (CRITICAL)
Before executing any tasks, reading code, or performing file/command operations, you MUST check the active task metadata:
1. Locate and read the file `.agents/current_task.json` in the workspace root.
2. Determine if you are authorized using the **writer/reviewer guard protocol**:
   - **Writer check**: If `"writer"` is `"claude"`, you have **full write access** — proceed with all operations.
   - **Reviewer check**: If `"writer"` is NOT `"claude"` but `"claude"` appears in `"reviewers"` (a list), you have **read-only / review access** — you may read code and perform review/analysis, but MUST NOT edit files or run destructive commands.
   - **Legacy fallback**: If `"writer"` is absent, fall back to the `"agent"` field — if `"agent"` is `"claude"`, you are authorized.
3. If none of the above conditions match, **YOU ARE NOT AUTHORIZED TO WORK ON THIS TASK**. Immediately stop all actions, DO NOT edit any files or run tests, and print a clear exit message:
   `[Routing Stop] This task is assigned to {writer} (writer, role={role}), not claude. Exiting.`
4. If authorized, proceed with the instructions below.

## Build and Test Commands
*   Run tests: `python test_classify_task.py` or equivalent test suite command.

## Core Rules & Standards
1.  **Strict Linting**: Keep python code clean and check for syntax errors.
2.  **No Direct master push**: Always work in the active task branch/worktree, never push directly to master.
3.  **Self-Submission**: When you complete the task requirements and verify all tests pass, you MUST run `agent-relay submit <task-id>` inside the worktree terminal before exiting.
