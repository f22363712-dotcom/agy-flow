# agy-flow Value Trial Plan v1

**Version**: 1.0 | **Last updated**: 2026-07-13

## Objective

Determine whether agy-flow, in its current MVP state, reduces friction
compared to manually coordinating multiple AI agents (Codex, Claude,
Antigravity) for a real software development task.

If agy-flow shows measurable value, development continues. If not, the
project should be paused or re-scoped.

---

## Experiment Design: A/B Parallel Track

One real task, executed twice — once manually (Track A) and once with
agy-flow (Track B). The task should be a real, non-trivial development
task such as:

> "Add a dark-mode toggle to the project's settings page, including
>  UI changes, state persistence, and a brief automated test."

| Aspect | Track A (Manual) | Track B (agy-flow) |
|---|---|---|
| **Task creation** | Manual note in an external tracker | `agy-flow create` |
| **Routing decision** | User decides which agent to use | `agy-flow route` or `agy-flow auto --dry-run` |
| **Writer dispatch** | Open Codex/Claude manually, copy context | `agy-flow dispatch --agent claude` |
| **Output recording** | Manual copy-paste to notes | Auto-recorded as run record |
| **Review** | Open reviewer manually, copy diff | `agy-flow continue run-xxxx --mock` |
| **State tracking** | User manually tracks status | `agy-flow status task-001` |
| **Quality check** | User manually reviews | `agy-flow quality task-001` |
| **Finalize** | Manual close-out | `agy-flow finalize task-001 --dry-run` |
| **Traceability** | User notes / memory | Run records + state history |

---

## Metrics

### Primary (Quantitative)

| Metric | Description | How to Measure |
|---|---|---|
| `context_copy_count` | Number of times user copied context between agents | Count manually during trial |
| `manual_decision_count` | Number of "what next?" decisions the user made | Count manually during trial |
| `time_to_first_action` | Time from task start to first agent invocation | Timestamp |
| `time_to_done` | Total time from task start to completion | Timestamp |
| `friction_points` | Number of times user got stuck or confused | Count manually during trial |

### Secondary (Qualitative, 1-5 scale)

| Metric | 1 | 5 |
|---|---|---|
| `task_state_clarity` | "I have no idea what's happening" | "I always know the exact status" |
| `result_traceability` | "I can't find what agent X did" | "Every action is recorded and searchable" |
| `review_quality` | "Review was skipped or shallow" | "Review was thorough and recorded" |
| `setup_friction` | "It took forever to set up" | "Setup was instant" |

### Task-Specific

| Metric | Description |
|---|---|
| `agent_switches` | Number of times work moved between different agents |
| `artifacts_generated` | Files modified, tests written, docs produced |
| `errors_caught` | Bugs or issues caught during review / quality gate |
| `notes_taken` | Pages or lines of notes the user wrote externally |

---

## Procedure

### Preparation

1. Pick one real task — small enough to finish in one session, large
   enough to benefit from multiple agents.
2. Ensure both tracks use the same task description.
3. Record starting timestamp.

### Track A (Manual)

1. User decides which agent to use first.
2. User manually opens the agent (Codex, Claude, Antigravity).
3. User copies/pastes context from notes or IDE.
4. Agent works; user copies/pastes output back to notes.
5. User decides next step manually.
6. Repeat until task is done.
7. Record ending timestamp and all metrics.

### Track B (agy-flow)

1. `agy-flow init` (if not already done).
2. `agy-flow create "task title"`.
3. `agy-flow route-task task-001` to see the plan.
4. `agy-flow auto task-001 --dry-run` to preview.
5. `agy-flow dispatch task-001 --agent claude` (or whichever is primary).
6. Parse output automatically (run record includes `parsed_output`).
7. `agy-flow continue run-xxxx` to trigger review (or `--mock` if no
   DeepSeek key).
8. `agy-flow quality task-001` to check readiness.
9. `agy-flow status task-001` to review the full picture.
10. `agy-flow finalize task-001 --dry-run` for the closing report.
11. Record all metrics.

---

## Go / No-Go Criteria

After completing both tracks, compare the results.

### Go (Continue Development)

agy-flow is worth continuing if **at least two** of these are true:

1. **`context_copy_count` reduced by ≥ 50%** — agy-flow measurably
   reduces manual context shuffling.
2. **`manual_decision_count` reduced by ≥ 40%** — the route + dispatch +
   continue chain automates real decisions.
3. **`time_to_done` is not worse** — agy-flow does not add overhead
   beyond the manual approach (within 20%).
4. **Subjective score average ≥ 4/5** — user reports that agy-flow
   genuinely helps, not just "interesting experiment".
5. **At least one real bug or improvement found** — the review loop or
   quality gate catches something the user would have missed manually.

### No-Go (Pause or Re-scope)

Consider pausing if **at least two** of these are true:

1. **Setup friction outweighs benefits** — initializing and learning
   agy-flow takes longer than just doing the work.
2. **`time_to_done` is ≥ 50% worse** — agy-flow is a net time drain.
3. **Subjective score average ≤ 2/5** — the user does not find it useful.
4. **No defects caught** — the review loop and quality gate never
   identify anything the user missed.
5. **Manual track was equally traceable** — user already has a workflow
   (e.g., git log + notebook) that provides equivalent traceability.

### Decision

After the trial, update this file with the results and a clear decision:

- ✅ **Continue**: agy-flow adds measurable value.
- ⏸ **Pause**: Value is unclear; focus on reducing friction.
- 🛑 **Stop**: agy-flow does not solve a real problem in its current form.

---

## Reporting

Use the `docs/value-trial-template.md` to record each trial.

You can also run:

```bash
agy-flow value-report path/to/trial-results.json
```

This will print a summary comparison table.
