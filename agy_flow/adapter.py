"""Agent Adapter v1 — unified dispatch abstraction for agy-flow.

Each adapter subclass implements ``dispatch(task_id, **kwargs)`` and returns
a ``RunResult`` dict.  The top-level ``dispatch()`` factory selects the
appropriate adapter by agent name, invokes it, persists a run record to
``.agents/runs/run-{run_id}.json``, and returns the result.
"""

import datetime
import json
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import agy_flow.config
from agy_flow.errors import AgyFlowError
from agy_flow.git_ops import run_cmd
from agy_flow.handoff import assign_current_task_agent, canonical_assignment_agent
from agy_flow.llm import review_task_service
from agy_flow.executors import run_cli_agent, build_agent_prompt
from agy_flow.output_parser import parse_agent_output

# ---------------------------------------------------------------------------
# Run record helpers
# ---------------------------------------------------------------------------

RUNS_DIR = None


def _ensure_runs_dir():
    global RUNS_DIR
    if RUNS_DIR is None:
        RUNS_DIR = agy_flow.config.RUNS_DIR
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return RUNS_DIR


def _new_run_id():
    return f"run-{uuid.uuid4().hex[:12]}"


def _save_run_record(record):
    path = _ensure_runs_dir() / f"{record['run_id']}.json"
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _load_task(task_id):
    """Return the board row dict for *task_id*, or raise."""
    from agy_flow.tasks import parse_board_rows

    tasks = parse_board_rows()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise AgyFlowError(f"Task '{task_id}' not found on the board.")
    return task


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add_run_record(
    task_id,
    agent,
    role="writer",
    status="completed",
    summary="",
    next_action="manual",
    files_touched=None,
    tests_run=None,
    risks=None,
):
    """Manually import a run record without invoking an adapter.

    Useful for recording work done outside agy-flow (e.g. directly in
    a chat window).  The record is persisted to ``.agents/runs/`` and the
    task state machine is updated accordingly.

    Parameters
    ----------
    task_id : str
    agent : str
    role : ``"writer"`` | ``"reviewer"``
    status : ``"completed"`` | ``"needs_review"`` | ``"blocked"`` | ``"failed"``
    summary : str
    next_action : ``"review"`` | ``"revise"`` | ``"submit"`` | ``"manual"`` | ``"none"``
    files_touched : list[str], optional
    tests_run : list[str], optional
    risks : list[str], optional

    Returns
    -------
    dict — the persisted run record.
    """
    from agy_flow.state_machine import (
        infer_event_from_run,
        transition_task_state,
        set_task_state,
    )

    if role not in ("writer", "reviewer"):
        raise AgyFlowError(f"Invalid role '{role}'. Must be 'writer' or 'reviewer'.")
    valid_statuses = {"completed", "needs_review", "blocked", "failed"}
    if status not in valid_statuses:
        raise AgyFlowError(
            f"Invalid status '{status}'. Valid: {sorted(valid_statuses)}"
        )
    valid_actions = {"review", "revise", "submit", "manual", "none"}
    if next_action not in valid_actions:
        raise AgyFlowError(
            f"Invalid next_action '{next_action}'. Valid: {sorted(valid_actions)}"
        )

    now = _now()
    run_id = _new_run_id()

    # Build parsed_output from parameters (no JSON block needed for manual
    # import)
    parsed_output = {
        "status": status,
        "summary": summary,
        "changes": [],
        "files_touched": files_touched or [],
        "tests_run": tests_run or [],
        "risks": risks or [],
        "next_action": next_action,
    }

    needs_review = next_action == "review" or status in ("completed", "needs_review")

    record = {
        "run_id": run_id,
        "task_id": task_id,
        "agent": agent,
        "role": role,
        "status": "success" if status in ("completed", "needs_review") else status,
        "started_at": now,
        "ended_at": now,
        "result": {"summary": summary} if summary else {},
        "error": "",
        "parsed_output": parsed_output,
        "next_action": next_action,
        "needs_review": needs_review,
        "files_touched": files_touched or [],
        "tests_run": tests_run or [],
        "risks": risks or [],
    }

    _save_run_record(record)

    # Trigger state machine transition
    event = infer_event_from_run(record)
    if event:
        try:
            transition_task_state(task_id, event, run_record=record)
        except Exception:
            pass

    return record


def list_runs(task_id=None):
    """List all run records, newest first.  If *task_id* is given, filter."""
    runs = []
    runs_dir = _ensure_runs_dir()
    if not runs_dir.exists():
        return runs
    for f in sorted(runs_dir.iterdir(), reverse=True):
        if f.suffix != ".json":
            continue
        try:
            record = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if task_id and record.get("task_id") != task_id:
            continue
        runs.append(record)
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return runs


def get_run(run_id):
    """Return a single run record, or None."""
    path = _ensure_runs_dir() / f"{run_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Abstract adapter
# ---------------------------------------------------------------------------


class AgentAdapter(ABC):
    """Base class for agent adapters.

    Subclasses must implement :meth:`dispatch` which returns a
    ``RunResult`` dict with at least the keys documented in
    :meth:`make_run_record`.
    """

    agent_name = ""

    @abstractmethod
    def dispatch(self, task_id, **kwargs):
        """Execute the agent against *task_id*.

        Returns
        -------
        dict
            A ``RunResult`` with keys documented under
            :meth:`make_run_record`.
        """
        ...

    def make_run_record(
        self, task_id, status="success", result=None, error=None, text_to_parse=None
    ):
        """Build a canonical run record dict.

        If *text_to_parse* is provided, it is fed to ``parse_agent_output``
        and the resulting fields are merged into the record.
        """
        record = {
            "run_id": _new_run_id(),
            "task_id": task_id,
            "agent": self.agent_name,
            "role": getattr(self, "role", "writer"),
            "status": status,
            "started_at": getattr(self, "_started_at", _now()),
            "ended_at": _now(),
            "result": result or {},
            "error": error,
        }

        if text_to_parse:
            parsed = parse_agent_output(text_to_parse)
            record["parsed_output"] = parsed
            record["next_action"] = parsed.get("next_action", "manual")
            record["needs_review"] = parsed.get(
                "next_action"
            ) == "review" or parsed.get("status") in ("completed", "needs_review")
            record["files_touched"] = parsed.get("files_touched", [])
            record["tests_run"] = parsed.get("tests_run", [])
            record["risks"] = parsed.get("risks", [])
        else:
            record["parsed_output"] = {}
            record["next_action"] = "manual"
            record["needs_review"] = False
            record["files_touched"] = []
            record["tests_run"] = []
            record["risks"] = []

        return record


# ---------------------------------------------------------------------------
# DeepSeek adapter
# ---------------------------------------------------------------------------


class DeepSeekAdapter(AgentAdapter):
    """Adapter that calls the existing DeepSeek review pipeline."""

    agent_name = "deepseek"

    def dispatch(self, task_id, mock=False, **kwargs):
        self._started_at = _now()

        # Validate task exists
        _load_task(task_id)

        review, source = review_task_service(task_id, agent="deepseek", mock=mock)

        if source == "unavailable":
            return self.make_run_record(
                task_id,
                status="unavailable",
                error="DeepSeek API key is not configured. "
                "Set DEEPSEEK_API_KEY or use --mock.",
            )

        return self.make_run_record(
            task_id,
            status="success",
            result={
                "review_source": source,
                "summary": review[:500] if review else "",
                "full_review": review,
            },
            text_to_parse=review,
        )


# ---------------------------------------------------------------------------
# Human-in-the-loop adapter
# ---------------------------------------------------------------------------


class HumanInLoopAdapter(AgentAdapter):
    """Adapter for agents that require a human to invoke them manually.

    Currently used for ``codex`` and ``antigravity``.  The adapter:
    - Validates the task has a worktree and is "In Progress".
    - Updates ``current_task.json`` via the existing handoff logic.
    - Prints a user-facing handoff instruction.
    - Persists a run record.
    """

    agent_name = ""

    def __init__(self, agent_name, display_name=None):
        self.agent_name = agent_name
        self._display_name = display_name or agent_name.capitalize()

    def dispatch(self, task_id, role="writer", **kwargs):
        self._started_at = _now()

        task = _load_task(task_id)

        # Must have an active worktree
        worktree = task.get("worktree", "").strip()
        if not worktree:
            raise AgyFlowError(
                f"Task '{task_id}' has no worktree — start it first with "
                f"'agy-flow start {task_id}'."
            )
        if "In Progress" not in task.get("status", ""):
            raise AgyFlowError(
                f"Task '{task_id}' is not in progress (status: {task['status']})."
            )

        worktree_path = Path(worktree)
        if not worktree_path.exists():
            raise AgyFlowError(f"Worktree path does not exist: {worktree}")

        # Carry forward existing reviewers for the assignment
        existing_reviewers = []
        guard_path = worktree_path / ".agents" / "current_task.json"
        if guard_path.exists():
            try:
                existing_reviewers = json.loads(
                    guard_path.read_text(encoding="utf-8")
                ).get("reviewers", [])
            except Exception:
                pass

        mode = "review" if role == "reviewer" else "handoff"
        assign_current_task_agent(
            self.agent_name,
            task_id=task_id,
            role=role,
            reviewers=existing_reviewers,
            mode=mode,
        )

        instruction = self._handoff_instruction(task_id, task, worktree_path)

        return self.make_run_record(
            task_id,
            status="handoff",
            result={
                "instruction": instruction,
                "worktree": str(worktree_path),
                "agent_display": self._display_name,
            },
            text_to_parse=instruction,
        )

    def _handoff_instruction(self, task_id, task, worktree_path):
        """Return a human-readable handoff instruction."""
        return (
            f"Task {task_id} dispatched to {self._display_name}.\n\n"
            f"Title: {task['title']}\n"
            f"Worktree: {worktree_path}\n\n"
            f"To work on this task, open the worktree in {self._display_name} "
            f"and run:\n"
            f"  agy-flow submit {task_id}\n\n"
            f"Guard file (.agents/current_task.json) has been updated for "
            f"{self.agent_name}."
        )


# ---------------------------------------------------------------------------
# CLI agent adapter (Claude, Gemini)
# ---------------------------------------------------------------------------


class CliAgentAdapter(AgentAdapter):
    """Adapter that invokes an external CLI agent via subprocess.

    Uses ``run_cli_agent`` from ``agy_flow.executors`` to call the
    agent binary, passing a structured task-context prompt built from
    the task spec, saved plan, and current route.

    The adapter never launches a GUI and never sets ``shell=True``.
    """

    agent_name = ""
    _cli_command = ""

    def __init__(self, agent_name, cli_command):
        self.agent_name = agent_name
        self._cli_command = cli_command

    def dispatch(self, task_id, role="writer", timeout=120, **kwargs):
        self._started_at = _now()

        task = _load_task(task_id)

        # Read task spec and plan
        task_spec = ""
        plan_text = ""
        plan_json = None
        try:
            plan_file = agy_flow.config.TASKS_DIR / f"{task_id}.plan.json"
            task_file = agy_flow.config.TASKS_DIR / f"{task_id}.md"
            if task_file.exists():
                task_spec = task_file.read_text(encoding="utf-8")
            if plan_file.exists():
                plan_text = plan_file.read_text(encoding="utf-8")
                plan_json = json.loads(plan_text)
        except Exception:
            pass

        # Build route context
        route = {"task_id": task_id, "role": role, "agent": self.agent_name}

        prompt = build_agent_prompt(
            task_id=task_id,
            title=task.get("title", ""),
            task_spec=task_spec,
            plan_text=plan_text,
            route=route,
            role=role,
        )

        command = [self._cli_command, "-p", prompt]
        result = run_cli_agent(
            self.agent_name,
            command,
            prompt,
            cwd=agy_flow.config.PROJECT_ROOT,
            timeout=timeout,
        )

        stdout_text = result.get("stdout", "") or ""

        if result["status"] == "unavailable":
            return self.make_run_record(
                task_id,
                status="unavailable",
                error=result["error"],
                result={
                    "stdout": "",
                    "stderr": "",
                    "returncode": None,
                    "duration_ms": 0,
                },
            )

        status = result["status"]
        error = result.get("error", "")

        return self.make_run_record(
            task_id,
            status=status,
            error=error if status != "success" else "",
            result={
                "stdout": stdout_text,
                "stderr": result.get("stderr", ""),
                "returncode": result.get("returncode"),
                "duration_ms": result.get("duration_ms", 0),
                "summary": stdout_text[:500],
            },
            text_to_parse=stdout_text,
        )


# ---------------------------------------------------------------------------
# Adapter registry and factory
# ---------------------------------------------------------------------------

_ADAPTERS = {}


def register_adapter(adapter_cls_or_instance):
    """Register an adapter class or instance by its ``agent_name``."""
    inst = (
        adapter_cls_or_instance()
        if isinstance(adapter_cls_or_instance, type)
        else adapter_cls_or_instance
    )
    _ADAPTERS[inst.agent_name] = inst


def get_adapter(agent_name):
    """Return the registered adapter for *agent_name*, or raise."""
    agent = agent_name.strip().lower()
    if agent not in _ADAPTERS:
        available = ", ".join(sorted(_ADAPTERS))
        raise AgyFlowError(
            f"No adapter registered for agent '{agent_name}'. Available: {available}"
        )
    return _ADAPTERS[agent]


# Register built-in adapters
register_adapter(DeepSeekAdapter)
register_adapter(HumanInLoopAdapter("codex", "Codex"))
register_adapter(HumanInLoopAdapter("antigravity", "Antigravity"))
register_adapter(CliAgentAdapter("claude", "claude"))
register_adapter(CliAgentAdapter("gemini", "gemini"))


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------


def dispatch(task_id, agent, mock=False, role="writer", **kwargs):
    """Select adapter for *agent*, run it, persist a run record, return result.

    Parameters
    ----------
    task_id : str
    agent : str
    mock : bool
        Passed through to adapters that support it (e.g. DeepSeek).
    role : str
        "writer" or "reviewer" — set on the adapter before dispatch.

    Returns
    -------
    dict
        Full run record including ``run_id``, ``task_id``, ``agent``,
        ``status``, ``started_at``, ``ended_at``, ``result``, ``error``.
    """
    adapter = get_adapter(agent)
    adapter.role = role
    record = adapter.dispatch(task_id, mock=mock, **kwargs)
    path = _save_run_record(record)
    record["_record_path"] = str(path)
    return record


# ---------------------------------------------------------------------------
# Module-level path sync (called by config.update_paths)
# ---------------------------------------------------------------------------


def update_module_paths():
    global RUNS_DIR
    RUNS_DIR = agy_flow.config.RUNS_DIR
