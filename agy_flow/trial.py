"""Value Trial Report — compare manual vs agy-flow experiment results.

Usage (via CLI): agy-flow value-report path/to/results.json
"""

import json
import sys


_METRIC_LABELS = {
    "context_copy_count": "Context copies",
    "manual_decision_count": "Manual decisions",
    "time_to_first_action_min": "Time to first action (min)",
    "time_to_done_min": "Time to done (min)",
    "friction_points": "Friction points",
    "agent_switches": "Agent switches",
    "artifacts_generated": "Artifacts generated",
    "errors_caught": "Errors caught",
    "notes_taken_lines": "Notes taken (lines)",
    "task_state_clarity": "State clarity (/5)",
    "result_traceability": "Traceability (/5)",
    "review_quality": "Review quality (/5)",
    "setup_friction": "Setup friction (1=worst)",
}


def _fmt(val):
    """Format a metric value for table display."""
    if val is None:
        return "-"
    if isinstance(val, float):
        return f"{val:.1f}"
    return str(val)


def _delta_str(a, b):
    """Return a formatted delta string between two values."""
    if a is None or b is None:
        return ""
    try:
        d = float(b) - float(a)
        sign = "+" if d > 0 else ""
        return f"{sign}{d:.1f}" if isinstance(d, float) else f"{sign}{int(d)}"
    except (ValueError, TypeError):
        return ""


def value_report(filepath):
    """Read a trial JSON file and print a comparison summary."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {filepath}")
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}")
        return 1

    trial_id = data.get("trial_id", "unknown")
    task_title = data.get("task_title", "(no title)")
    date = data.get("date", "(no date)")

    track_a = data.get("track_a", {})
    track_b = data.get("track_b", {})

    print("=" * 72)
    print(f"  agy-flow Value Trial Report: {trial_id}")
    print(f"  Task: {task_title}")
    print(f"  Date: {date}")
    print("=" * 72)
    print()
    print(f"{'Metric':<30} {'Manual':<12} {'agy-flow':<12} {'Delta':<12}")
    print("-" * 72)

    all_keys = set(track_a.keys()) | set(track_b.keys())
    for key in sorted(all_keys):
        label = _METRIC_LABELS.get(key, key)
        a_val = track_a.get(key)
        b_val = track_b.get(key)
        if a_val is None and b_val is None:
            continue
        delta = _delta_str(a_val, b_val)
        print(f"  {label:<28} {_fmt(a_val):<12} {_fmt(b_val):<12} {delta:<12}")

    print("-" * 72)

    # Go / no-go check
    print()
    print("  Go / No-Go Assessment")
    print("  " + "-" * 50)

    passed = 0
    total = 0

    # Criterion 1: context copies reduced >= 50%
    total += 1
    a_copy = track_a.get("context_copy_count")
    b_copy = track_b.get("context_copy_count")
    if a_copy and b_copy is not None and b_copy <= a_copy * 0.5:
        print(f"  ✅ Context copies reduced >= 50% ({a_copy} → {b_copy})")
        passed += 1
    elif a_copy and b_copy is not None:
        print(f"  ❌ Context copies not reduced >= 50% ({a_copy} → {b_copy})")
    else:
        print(f"  ⬜ Context copies: insufficient data")

    # Criterion 2: manual decisions reduced >= 40%
    total += 1
    a_dec = track_a.get("manual_decision_count")
    b_dec = track_b.get("manual_decision_count")
    if a_dec and b_dec is not None and b_dec <= a_dec * 0.6:
        print(f"  ✅ Manual decisions reduced >= 40% ({a_dec} → {b_dec})")
        passed += 1
    elif a_dec and b_dec is not None:
        print(f"  ❌ Manual decisions not reduced >= 40% ({a_dec} → {b_dec})")
    else:
        print(f"  ⬜ Manual decisions: insufficient data")

    # Criterion 3: time not worse (within 20%)
    total += 1
    a_time = track_a.get("time_to_done_min")
    b_time = track_b.get("time_to_done_min")
    if a_time and b_time is not None and b_time <= a_time * 1.2:
        print(f"  ✅ Time not worse (Manual {a_time}min vs agy-flow {b_time}min)")
        passed += 1
    elif a_time and b_time is not None:
        print(f"  ❌ Time significantly worse ({a_time}min → {b_time}min)")
    else:
        print(f"  ⬜ Time: insufficient data")

    # Criterion 4: subjective score average >= 4/5
    total += 1
    b_scores = [
        track_b.get("task_state_clarity"),
        track_b.get("result_traceability"),
        track_b.get("review_quality"),
    ]
    valid = [s for s in b_scores if s is not None]
    if valid:
        avg = sum(valid) / len(valid)
        if avg >= 4.0:
            print(f"  ✅ Subjective score avg >= 4/5 ({avg:.1f})")
            passed += 1
        else:
            print(f"  ❌ Subjective score avg < 4/5 ({avg:.1f})")
    else:
        print(f"  ⬜ Subjective scores: insufficient data")

    # Criterion 5: at least one bug caught by review/quality
    total += 1
    b_errors = track_b.get("errors_caught")
    if b_errors and b_errors > 0:
        print(f"  ✅ {b_errors} error(s) caught by review/quality gate")
        passed += 1
    else:
        print(f"  ⬜ No errors caught by quality gate")

    print()
    print(f"  Criteria passed: {passed}/{total}")
    if passed >= 2:
        print(f"  ▶ Decision: ✅ Continue developing agy-flow")
    elif passed >= 1:
        print(f"  ▶ Decision: ⏸ Pause — value unclear; reduce friction first")
    else:
        print(f"  ▶ Decision: 🛑 Stop — agy-flow does not add value in current form")

    print()
    return 0
