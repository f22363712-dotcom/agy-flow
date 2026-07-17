"""Value Trial Recorder v1 — record trial events and export value-report compatible JSON.

Events are accumulated in ``.agents/trials/{trial_id}.json`` and can be
exported to the format expected by ``agy-flow value-report``.
"""

import datetime
import json
import os

import agy_flow.config
from agy_flow.errors import AgyFlowError


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _trials_dir():
    d = agy_flow.config.AGENTS_DIR / "trials"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(trial_id):
    return _trials_dir() / f"{trial_id}.json"


_VALID_EVENTS = frozenset(
    {"copy", "decision", "agent_switch", "friction", "error_caught", "artifact", "note"}
)

_DEFAULT_METRIC_MAP = {
    "copy": "context_copy_count",
    "decision": "manual_decision_count",
    "agent_switch": "agent_switches",
    "friction": "friction_points",
    "error_caught": "errors_caught",
    "artifact": "artifacts_generated",
}


def _load(trial_id):
    path = _path(trial_id)
    if not path.exists():
        raise AgyFlowError(f"Trial '{trial_id}' not found at {path}.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise AgyFlowError(f"Failed to read trial '{trial_id}': {e}")


def trial_start(trial_id, task_title, track="agy-flow"):
    """Start a new value trial.

    Parameters
    ----------
    trial_id : str
    task_title : str
    track : str
        ``"manual"`` or ``"agy-flow"`` — maps to ``track_a`` / ``track_b``.

    Returns
    -------
    dict — the trial record.
    """
    path = _path(trial_id)
    if path.exists():
        raise AgyFlowError(f"Trial '{trial_id}' already exists at {path}.")

    track_key = "track_a" if track == "manual" else "track_b"
    record = {
        "trial_id": trial_id,
        "date": _now()[:10],
        "task_title": task_title,
        "started_at": _now(),
        "ended_at": None,
        "track": track_key,
        "events": [],
        "counters": {
            "context_copy_count": 0,
            "manual_decision_count": 0,
            "agent_switches": 0,
            "friction_points": 0,
            "errors_caught": 0,
            "artifacts_generated": 0,
            "notes_taken_lines": 0,
        },
        "qualitative": {},
    }
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return record


def trial_event(trial_id, event_type, note=None, count=1):
    """Record a single event in the trial.

    Parameters
    ----------
    trial_id : str
    event_type : str
        One of: copy, decision, agent_switch, friction, error_caught, artifact, note.
    note : str, optional
    count : int
        How many to increment the counter by (default 1).

    Returns
    -------
    dict — updated trial record.
    """
    if event_type not in _VALID_EVENTS:
        raise AgyFlowError(
            f"Invalid event type '{event_type}'. Valid: {sorted(_VALID_EVENTS)}"
        )

    record = _load(trial_id)
    record.setdefault("events", []).append(
        {
            "event_type": event_type,
            "note": note or "",
            "timestamp": _now(),
        }
    )

    # Update counter
    metric_key = _DEFAULT_METRIC_MAP.get(
        event_type, "notes_taken_lines" if event_type == "note" else None
    )
    if metric_key:
        record["counters"][metric_key] = record["counters"].get(metric_key, 0) + count

    _path(trial_id).write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return record


def trial_stop(trial_id):
    """Stop the trial and set ended_at.

    Returns
    -------
    dict — updated trial record.
    """
    record = _load(trial_id)
    record["ended_at"] = _now()
    _path(trial_id).write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return record


def trial_export(trial_id, output_path=None):
    """Export a trial to value-report-compatible JSON.

    The output JSON has ``track_a`` or ``track_b`` at top level so that
    ``agy-flow value-report`` can read it.

    Parameters
    ----------
    trial_id : str
    output_path : str, optional
        If omitted, writes to stdout (returns the dict).

    Returns
    -------
    dict or None (if output_path given).
    """
    record = _load(trial_id)
    track_key = record.get("track", "track_b")
    counters = record.get("counters", {})

    export = {
        "trial_id": trial_id,
        "date": record.get("date", ""),
        "task_title": record.get("task_title", ""),
        track_key: counters,
        "_source": "agy_flow_trial_recorder",
    }

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export, f, indent=2, ensure_ascii=False)
        print(f"Exported to {output_path}")
        return None

    return export
