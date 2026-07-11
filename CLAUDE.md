# Claude Code Global Project Guide

Welcome! This is the global project-wide guide for Claude Code.

## ⚠️ Agent Assignment Enforcement (CRITICAL)
Before executing any tasks, reading code, or performing file/command operations, you MUST check the active task metadata:
1. Locate and read the file `.agents/current_task.json` in the workspace root.
2. Read the `"agent"` value inside the JSON.
3. If `"agent"` is **NOT** `"claude"`, **YOU ARE NOT AUTHORIZED TO WORK ON THIS TASK**. You must immediately stop all actions, DO NOT edit any files or run tests, and print a clear exit message:
   `[Routing Stop] This task is assigned to {agent} (not claude). Exiting.`
4. If `"agent"` is `"claude"`, proceed with the instructions below.

## Build and Test Commands
*   Run tests: `python test_classify_task.py` or equivalent test suite command.

## Core Rules & Standards
1.  **Strict Linting**: Keep python code clean and check for syntax errors.
2.  **No Direct master push**: Always work in the active task branch/worktree, never push directly to master.
3.  **Self-Submission**: When you complete the task requirements and verify all tests pass, you MUST run `agy-flow submit <task-id>` inside the worktree terminal before exiting.
