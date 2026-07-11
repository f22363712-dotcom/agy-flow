# Codex Global Developer Guide

Welcome! This is the global project-wide guide for Codex.

## ⚠️ Agent Assignment Enforcement (CRITICAL)
Before executing any tasks, reading code, or performing operations, you MUST check the active task metadata:
1. Locate and read the file `.agents/current_task.json` in the workspace root.
2. Read the `"agent"` value inside the JSON.
3. If `"agent"` is **NOT** `"codex"`, **YOU ARE NOT AUTHORIZED TO WORK ON THIS TASK**. You must immediately stop all actions, DO NOT edit any files, and print a clear exit message:
   `[Routing Stop] This task is assigned to {agent} (not codex). Stopping.`
4. If `"agent"` is `"codex"`, proceed with the instructions below.

## agy-flow Integration
This project uses the agy-flow multi-agent collaboration framework.

## Task Submission Command
Once you complete the user's requirements and they are satisfied, you MUST run the following command in the VS Code integrated terminal to submit:
`agy-flow submit <task-id>`
(The active task ID is specified in `.agents/current_task.json`)
Alternatively, you can run the default VS Code Build task by pressing `Ctrl+Shift+B` to submit automatically.
