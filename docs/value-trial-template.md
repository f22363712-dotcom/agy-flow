# agent-relay Value Trial Record

**Trial ID**: `<!-- e.g. trial-001 -->`  
**Date**: `<!-- YYYY-MM-DD -->`  
**Tester**: `<!-- your name -->`  
**Task Title**: `<!-- one-line description -->`

---

## Track A (Manual)

### Preparation

| Item | Value |
|---|---|
| Agents used | `<!-- e.g., Codex + Claude -->` |
| External tools | `<!-- e.g., Notion, VS Code, terminal -->` |

### Metrics

| Metric | Value |
|---|---|
| context_copy_count | `<!-- number -->` |
| manual_decision_count | `<!-- number -->` |
| time_to_first_action (min) | `<!-- minutes -->` |
| time_to_done (min) | `<!-- minutes -->` |
| friction_points | `<!-- count -->` |
| agent_switches | `<!-- count -->` |
| artifacts_generated | `<!-- count -->` |
| errors_caught | `<!-- count -->` |
| notes_taken (lines) | `<!-- approx lines -->` |

### Qualitative Scores (1-5)

| Metric | Score | Notes |
|---|---|---|
| task_state_clarity | `/5` | |
| result_traceability | `/5` | |
| review_quality | `/5` | |
| setup_friction | `/5` (1=worst) | |

### Friction Notes

```
What got in the way? Where did you get stuck?
```

---

## Track B (agent-relay)

### Preparation

| Item | Value |
|---|---|
| `agent-relay init` | ✅ / ❌ |
| agent-relay version | `<!-- output of agent-relay doctor -->` |
| Agents available | `<!-- output of agent-relay agents --json -->` |

### Steps Completed

| Step | Done? | Notes |
|---|---|---|
| create task | ✅ ❌ | |
| route / route-task | ✅ ❌ | |
| auto-dispatch --dry-run | ✅ ❌ | |
| dispatch writer | ✅ ❌ | |
| parse output (automatic) | ✅ ❌ | |
| continue reviewer | ✅ ❌ | |
| quality gate | ✅ ❌ | |
| finalize --dry-run | ✅ ❌ | |
| status / doctor review | ✅ ❌ | |

### Metrics

| Metric | Value |
|---|---|
| context_copy_count | `<!-- number -->` |
| manual_decision_count | `<!-- number -->` |
| time_to_first_action (min) | `<!-- minutes -->` |
| time_to_done (min) | `<!-- minutes -->` |
| friction_points | `<!-- count -->` |
| agent_switches | `<!-- count -->` |
| artifacts_generated | `<!-- count -->` |
| errors_caught | `<!-- count -->` |
| notes_taken (lines) | `<!-- approx lines -->` |

### Qualitative Scores (1-5)

| Metric | Score | Notes |
|---|---|---|
| task_state_clarity | `/5` | |
| result_traceability | `/5` | |
| review_quality | `/5` | |
| setup_friction | `/5` (1=worst) | |

### Friction Notes

```
What got in the way? What was confusing about agent-relay?
```

---

## Comparison

| Metric | Track A (Manual) | Track B (agent-relay) | Delta |
|---|---|---|---|
| context_copy_count | | | |
| manual_decision_count | | | |
| time_to_first_action | | | |
| time_to_done | | | |
| friction_points | | | |
| agent_switches | | | |
| artifacts_generated | | | |
| errors_caught | | | |
| task_state_clarity | /5 | /5 | |
| result_traceability | /5 | /5 | |
| review_quality | /5 | /5 | |
| setup_friction | /5 | /5 | |

---

## Verdict

Based on the go/no-go criteria in `docs/value-trial-plan.md`:

- [ ] **Continue**: agent-relay adds measurable value.
  - Context copy reduced: Y/N
  - Manual decisions reduced: Y/N
  - Time not worse: Y/N
  - Subjective score ≥ 4: Y/N
  - Bug caught by review/quality: Y/N

- [ ] **Pause**: Value is unclear; focus on reducing friction.
- [ ] **Stop**: agent-relay does not solve a real problem.

### Free-form Feedback

```
What would make agent-relay more useful?
What was the single best thing about using agent-relay?
What was the single worst thing?
```

---

## JSON Summary (for `agent-relay value-report`)

```json
{
  "trial_id": "",
  "date": "",
  "task_title": "",
  "track_a": {
    "context_copy_count": 0,
    "manual_decision_count": 0,
    "time_to_first_action_min": 0,
    "time_to_done_min": 0,
    "friction_points": 0,
    "agent_switches": 0,
    "artifacts_generated": 0,
    "errors_caught": 0,
    "notes_taken_lines": 0,
    "task_state_clarity": 0,
    "result_traceability": 0,
    "review_quality": 0,
    "setup_friction": 0
  },
  "track_b": {
    "context_copy_count": 0,
    "manual_decision_count": 0,
    "time_to_first_action_min": 0,
    "time_to_done_min": 0,
    "friction_points": 0,
    "agent_switches": 0,
    "artifacts_generated": 0,
    "errors_caught": 0,
    "notes_taken_lines": 0,
    "task_state_clarity": 0,
    "result_traceability": 0,
    "review_quality": 0,
    "setup_friction": 0
  }
}
```
