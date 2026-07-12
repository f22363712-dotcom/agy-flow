import os
import sys
import json
import urllib.request
import urllib.error
import agy_flow.config
from agy_flow.git_ops import run_cmd

def truncate_text(text, max_chars):
    """Keeps prompts bounded before sending them to a metered model."""
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}\n\n[... truncated {omitted} chars ...]"

def call_openai_compatible_chat(agent, prompt, system_prompt=None, dry_run=False):
    """Call an OpenAI-compatible chat completions endpoint."""
    config = agy_flow.config.get_config()
    settings = agy_flow.config.get_llm_agent_settings(agent, config)
    payload = {
        "model": settings["model"],
        "messages": [],
        "temperature": 0.2,
    }
    if system_prompt:
        payload["messages"].append({"role": "system", "content": system_prompt})
    payload["messages"].append({"role": "user", "content": prompt})

    if dry_run:
        print(json.dumps({k: v for k, v in settings.items() if k != "api_key"}, indent=4))
        print("\n--- prompt ---")
        print(prompt)
        return None

    if not settings["api_key"]:
        print(
            f"Error: Missing API key for '{agent}'. Set {settings['api_key_env']} "
            "or configure api_key_env in .agents/config.json."
        )
        sys.exit(1)

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{settings['base_url']}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            body = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"Error: LLM request failed with HTTP {e.code}: {detail}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: LLM request failed: {e}")
        sys.exit(1)

    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print("Error: Unexpected LLM response:")
        print(json.dumps(body, indent=4, ensure_ascii=False))
        sys.exit(1)

def ask_agent_command(args):
    """Ask an LLM API agent a one-off question."""
    answer = call_openai_compatible_chat(
        args.agent,
        args.prompt,
        system_prompt=(
            "You are a low-cost planning and review agent inside agy-flow. "
            "Be concise, concrete, and biased toward actionable engineering output."
        ),
        dry_run=args.dry_run,
    )
    if answer is not None:
        print(answer)

def get_task_diff_fallback(task, max_chars):
    worktree = task.get("worktree", "").strip()
    if not worktree:
        print(f"Error: Task '{task['id']}' has no worktree path.")
        sys.exit(1)
    from pathlib import Path
    worktree_path = Path(worktree)
    if not worktree_path.exists():
        print(f"Error: Worktree path does not exist: {worktree_path}")
        sys.exit(1)

    code, stat, stderr = run_cmd(["git", "diff", "--stat"], cwd=str(worktree_path))
    if code != 0:
        print(f"Error collecting diff stat: {stderr}")
        sys.exit(1)

    code, diff, stderr = run_cmd(["git", "diff", "--", "."], cwd=str(worktree_path))
    if code != 0:
        print(f"Error collecting diff: {stderr}")
        sys.exit(1)

    if not diff:
        code, diff, stderr = run_cmd(["git", "diff", "HEAD", "--", "."], cwd=str(worktree_path))
        if code != 0:
            print(f"Error collecting HEAD diff: {stderr}")
            sys.exit(1)

    return stat, truncate_text(diff or "[No diff found]", max_chars)

def parse_board_rows_fallback():
    from agy_flow.config import BOARD_FILE
    if not BOARD_FILE.exists():
        return []
    with open(BOARD_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    tasks = []
    for line in lines:
        if "|" in line:
            if "---" in line or "Task ID" in line:
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 4:
                tasks.append({
                    "id": parts[0],
                    "title": parts[1],
                    "agent": parts[2],
                    "status": parts[3],
                    "branch": parts[4] if len(parts) > 4 else "",
                    "worktree": parts[5] if len(parts) > 5 else "",
                })
    return tasks

def review_task_command(args):
    """Ask an LLM API agent to review a task worktree diff."""
    tasks = parse_board_rows_fallback()
    task = next((t for t in tasks if t["id"] == args.task_id), None)
    if not task:
        print(f"Error: Task '{args.task_id}' not found.")
        sys.exit(1)

    task_file = agy_flow.config.TASKS_DIR / f"{args.task_id}.md"
    plan_file = agy_flow.config.TASKS_DIR / f"{args.task_id}.plan.json"
    task_spec = task_file.read_text(encoding="utf-8") if task_file.exists() else ""
    plan_text = plan_file.read_text(encoding="utf-8") if plan_file.exists() else "{}"
    diff_stat, diff = get_task_diff_fallback(task, args.max_diff_chars)

    prompt = f"""Review this task implementation as a concise engineering reviewer.

Focus on correctness, regressions, missing tests, security, and maintainability.
Return findings first, ordered by severity. If there are no material issues, say so.

Task:
{json.dumps(task, ensure_ascii=False, indent=2)}

Task Spec:
{truncate_text(task_spec, 6000)}

Routing Plan:
{truncate_text(plan_text, 6000)}

Diff Stat:
{diff_stat or "[No diff stat]"}

Diff:
{diff}
"""
    answer = call_openai_compatible_chat(
        args.agent,
        prompt,
        system_prompt=(
            "You are a careful code reviewer. Do not rewrite the whole patch. "
            "Prioritize concrete bugs and risks over style."
        ),
        dry_run=args.dry_run,
    )
    if answer is not None:
        print(answer)


def update_module_paths():
    global TASKS_DIR, PROJECT_ROOT
    import agy_flow.config
    TASKS_DIR = agy_flow.config.TASKS_DIR
    PROJECT_ROOT = agy_flow.config.PROJECT_ROOT
