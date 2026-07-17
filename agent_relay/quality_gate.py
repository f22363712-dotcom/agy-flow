"""Quality Gate v1 — evaluate whether a task is ready for submission.

The function ``evaluate_task_quality(task_id)`` inspects task state, run
records, parsed output, reviewer results, and metadata to determine
whether the task can safely be finalised.
"""

from agent_relay.state_machine import get_task_state
from agent_relay.adapter import list_runs
from agent_relay.errors import AgentRelayError


def evaluate_task_quality(task_id):
    """Return a structured quality assessment for *task_id*.

    Returns
    -------
    dict with keys:
        task_id, state, ready (bool), blocking_issues (list),
        warnings (list), latest_writer_run (dict), latest_reviewer_run (dict),
        tests_run (list), files_touched (list), risks (list),
        recommended_next_action (str).
    """
    state = get_task_state(task_id)
    cur = state.get("state", "planned")

    runs = list_runs(task_id=task_id)
    writer_runs = [r for r in runs if r.get("role") == "writer"]
    reviewer_runs = [r for r in runs if r.get("role") == "reviewer"]

    latest_writer = writer_runs[0] if writer_runs else {}
    latest_reviewer = reviewer_runs[0] if reviewer_runs else {}

    writer_parsed = latest_writer.get("parsed_output", {}) or {}
    reviewer_parsed = latest_reviewer.get("parsed_output", {}) or {}

    blocking_issues = []
    warnings = []

    # --- Blocking checks ---

    # 1. blocked / failed / revision_requested cannot submit
    if cur in ("blocked",):
        blocking_issues.append("Task is 'blocked'. Clear the blocked state first.")

    if cur == "revision_requested":
        blocking_issues.append(
            "Reviewer requested revision ('revision_requested'). "
            "Address reviewer feedback before submitting."
        )

    if cur == "failed":
        blocking_issues.append("Task is in 'failed' state.")

    # 2. submitted / done cannot re-submit
    if cur in ("submitted", "done"):
        blocking_issues.append(f"Task is already '{cur}'. Cannot re-submit.")

    # 3. No writer run
    if not writer_runs:
        blocking_issues.append("No writer run found. Dispatch a writer first.")

    # 4. Writer run has no parsed output
    if writer_runs and not writer_parsed:
        blocking_issues.append(
            "Latest writer run has no parsed_output. "
            "The agent output could not be parsed."
        )

    # 5. Writer requested review but no reviewer run
    writer_next = writer_parsed.get("next_action", "manual")
    if writer_runs and writer_parsed and writer_next == "review" and not reviewer_runs:
        blocking_issues.append(
            "Writer requested review, but no reviewer run found. "
            "Run 'continue' to dispatch a reviewer."
        )

    # 6. Reviewer requested revision
    reviewer_next = reviewer_parsed.get("next_action", "manual")
    if reviewer_runs and reviewer_next == "revise":
        blocking_issues.append(
            "Reviewer requested revision ('revise'). "
            "Address feedback before submitting."
        )

    # --- Warning checks ---

    # 7. tests_run
    all_tests_run = set()
    for r in runs:
        for t in r.get("tests_run", []):
            if t:
                all_tests_run.add(t)
        for t in r.get("parsed_output", {}).get("tests_run", []):
            if t:
                all_tests_run.add(t)
    if not all_tests_run:
        warnings.append(
            "No tests_run recorded across any runs. "
            "Consider running tests before submitting."
        )

    # 8. risks
    all_risks = []
    for r in runs:
        risks = r.get("risks", []) or r.get("parsed_output", {}).get("risks", [])
        all_risks.extend(risks)

    # 9. files_touched
    all_files = set()
    for r in runs:
        for f in r.get("files_touched", []):
            if f:
                all_files.add(f)
        for f in r.get("parsed_output", {}).get("files_touched", []):
            if f:
                all_files.add(f)
    if not all_files:
        warnings.append(
            "No files_touched recorded across any runs. "
            "The task may not have produced any changes."
        )

    # --- Determine recommendation ---

    if blocking_issues:
        recommended = "manual"
    elif all_risks:
        recommended = "review"
    elif reviewer_runs and reviewer_next in ("submit", "none"):
        recommended = "submit"
    elif reviewer_runs:
        recommended = "review"
    elif writer_next == "submit":
        recommended = "submit"
    elif writer_runs:
        recommended = "review"
    else:
        recommended = "manual"

    ready = len(blocking_issues) == 0

    return {
        "task_id": task_id,
        "state": cur,
        "ready": ready,
        "blocking_issues": blocking_issues,
        "warnings": warnings,
        "latest_writer_run": latest_writer,
        "latest_reviewer_run": latest_reviewer,
        "tests_run": sorted(all_tests_run),
        "files_touched": sorted(all_files),
        "risks": all_risks,
        "recommended_next_action": recommended,
    }
