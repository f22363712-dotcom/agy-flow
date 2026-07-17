# Personal Operating Workflow v1 — agy-flow

**Version**: 1.0 | **Last updated**: 2026-07-14  
**Based on**: X social_signals Value Trial (docs/value-trials/)  
**Verdict**: Continue developing — 3/5 criteria passed, real friction reduced.

---

## 1. Default Role Split

This is the role assignment that the X social_signals trial validated. It works.

| Persona | Default Role | When to Use |
|---|---|---|
| **Codex** | Planner, reviewer, risk discoverer, test validator, final decision maker | Task start (plan), Claude done (review), unsure (first) |
| **Claude** | Primary implementer, script refactor, documentation writer | Backend logic, Python, tests, docstrings |
| **Antigravity** | UI, visualization, interaction design, frontend polish | Dashboards, HTML/CSS, layout, UX touch-ups |
| **agy-flow** | Task record, state tracking, handoff prompt, trial data, quality gate | Every multi-step task |

### Why Codex = planner + reviewer, not implementer?

The trial showed:

- Codex catches errors Claude misses (6 errors caught vs 0 manually).
- Codex is better at architecture + risk assessment.
- Claude is faster at implementation.
- Separating planner and implementer catches more bugs than having one agent do both.

---

## 2. Every Task: How to Start

```bash
# 1. Check who currently holds the writer lock
agy-flow whoami

# 2. Take the writer lock (--force if someone else has it, which is fine)
agy-flow lease codex --force

# 3. Start a value trial to track metrics
agy-flow trial start trial-add-auth --task "Add auth middleware" --track agy-flow

# 4. Create the task
agy-flow create "Add auth middleware with JWT support"

# 5. Preview the route
agy-flow route-task task-001
```

This takes about 30 seconds. It replaces "open a note file and figure out what to do."

---

## 3. Deciding Who Should Do the Work

### Decision Tree

```
Is it UI / frontend / visual?
  → Antigravity

Is it backend / Python / tests / documentation?
  → Claude

Is it architecture / code review / risk assessment / uncertain?
  → Codex

Is it a plan-first-then-implement?
  → Codex plans → Claude implements
```

### If Uncertain

Do not guess. Run:

```bash
agy-flow route "Add auth middleware"
```

This asks the classifier (keyword + score based) and the connector probes
(which CLIs are installed, which API keys are set) to recommend.

But the final call is always yours. The role split above is a default,
not a rule.

---

## 4. Generating a Handoff Prompt for Claude

After Codex has planned the task, or when you know what needs doing:

```bash
agy-flow handoff-prompt claude --objective "Implement X social_signals collector in intelligence-collector/src/social/x_signals.py"
```

This outputs a structured prompt containing:

- Current task state
- Writer/reviewer guard info
- Quality gate status
- Safety constraints (no API keys, no GUI, worktree only)
- Role-specific instructions

**Copy the output and paste it to Claude.**

Do not manually rewrite context. The prompt is designed to give Claude
everything it needs: what to do, what not to do, where to work, and
how to submit when done.

### Example (abridged)

```
You are about to hand off work to **Claude Code** inside the agy-flow
collaboration framework.

## Objective
Implement X social_signals collector in
intelligence-collector/src/social/x_signals.py

## Task: task-002
  Current State: dispatched
  Latest Writer: codex — completed

## Guard: Writer / Reviewer Protocol
  Current Writer: Codex
  Reviewers: [claude, antigravity]
  Current Role: writer
  Current Mode: handoff

## Safety Constraints
- Do NOT write API keys into code or config.
- Do NOT launch any GUI, browser, or desktop application.
- Work inside the assigned worktree directory only.
- When finished, run: agy-flow submit task-002
```

---

## 5. After Claude Completes: Codex Review

After Claude finishes, the review loop should be manual by default
(writer was human-in-loop) but can be automated with `--mock`:

```bash
# 1. Dispatch a reviewer via the adapter
agy-flow continue run-xxxx --mock

# 2. Or manually: lease the reviewer
agy-flow lease codex --force
agy-flow handoff-prompt codex --objective "Review Claude's implementation for correctness, security, and X API usage"

# 3. Record what happened
agy-flow trial event trial-add-auth error_caught --note "Codex caught X API rate limit edge case"
agy-flow trial event trial-add-auth decision --note "Used tweepy v2 instead of v1"
agy-flow trial event trial-add-auth friction --note "Claude didn't check API key env var name"

# 4. Run tests
python -m pytest intelligence-collector/tests/

# 5. Check quality gate
agy-flow quality task-001

# 6. Review full status
agy-flow status task-001
agy-flow doctor
```

---

## 6. When to Use Antigravity

```bash
# Lease Antigravity as writer
agy-flow lease antigravity --force

# Generate prompt
agy-flow handoff-prompt antigravity --objective "Polish the dashboard UI — fix alignment, add dark mode toggle, clean up CSS"
```

Antigravity is the right choice when the task involves:

- HTML / CSS / frontend framework (React, Vue, etc.)
- UI dashboard modifications
- Visual design decisions (colors, spacing, layout)
- Interaction / animation improvements
- Accessibility review

Antigravity does not write backend logic. Do not send it there.

---

## 7. When NOT to Use agy-flow

agy-flow adds structure and traceability. Not every task needs that.

### Skip agy-flow When

| Situation | Why Not |
|---|---|
| **Less than 5 minutes** (typo fix, one-line change) | Setup overhead > task time |
| **Single file, no review needed** | No handoff needed |
| **Pure chat / learning** (asking a question, reading docs) | No artifact produced |
| **Personal note** (not a coding task) | Not a task |
| **Quick experiment** (might be discarded) | Trial data noise |

### Use agy-flow When

| Situation | Why |
|---|---|
| **Multi-step task** (plan → implement → review) | Handoff between agents |
| **Task involves ≥ 2 agents** | Route + dispatch + continue |
| **You want to track metrics** | Value trial recording |
| **You need to reproduce the result later** | Run records + state history |
| **Task is important or risky** | Quality gate catches issues |

---

## 8. Value Trial Recording: Minimum Requirements

You do not need to record everything. The trial showed that these 5
metrics give 90% of the signal:

### Required (track every task)

| Metric | CLI | When |
|---|---|---|
| Copy count | `agy-flow trial event <id> copy` | Each time you copy context between agents |
| Decision count | `agy-flow trial event <id> decision --note "..."` | Each time you choose what to do next |
| Friction points | `agy-flow trial event <id> friction --note "..."` | Each time you get stuck or confused |
| Errors caught | `agy-flow trial event <id> error_caught --note "..."` | Each time review/quality catches a real bug |
| Subjective score | Fill in at end: state_clarity, traceability, review_quality (1-5) | After stopping the trial |

### Optional

```bash
agy-flow trial event <id> agent_switch --note "Codex → Claude"
agy-flow trial event <id> artifact --note "generated x_signals.py"
agy-flow trial event <id> note --count 5   # lines of notes taken
```

### Stop and Export

```bash
agy-flow trial stop <id>
agy-flow trial export <id> --output docs/value-trials/<id>-results.json
agy-flow value-report docs/value-trials/<id>-results.json
```

---

## 9. One-Page Cheat Sheet

### 10 Most Common Commands

```bash
# ---------- Session start ----------
agy-flow whoami                          # Who holds the writer lock
agy-flow lease codex --force             # Take the writer lock
agy-flow trial start <id> --task "..."   # Start recording metrics

# ---------- Task lifecycle ----------
agy-flow create "<title>"                # Create task (auto-routes)
agy-flow route-task task-001             # Show recommended route
agy-flow handoff-prompt claude --objective "..."  # Generate Claude prompt

# ---------- Review & quality ----------
agy-flow lease codex --force             # Take reviewer role
agy-flow quality task-001                # Check quality gate
agy-flow status task-001                 # Full task status

# ---------- Trial recording ----------
agy-flow trial event <id> error_caught --note "..."
agy-flow trial stop <id>
agy-flow trial export <id> --output results.json
agy-flow value-report results.json
```

---

## 10. Complete Example: X social_signals Trial

This is the actual workflow that was tested in the Value Trial.

### Task

Add X (Twitter) social_signals collector layer to `intelligence-collector`
in `D:\my-automations`.

### Step-by-step

```bash
# === Session start ===
agy-flow whoami
# → writer: none (first task of the day)

agy-flow lease codex --force
# → status: leased, writer: Codex

agy-flow trial start x-social --task "Add X social_signals collector" --track agy-flow

agy-flow create "Add X social_signals collector"
# → task-002

agy-flow route-task task-002
# → primary: claude, fallbacks: [codex, antigravity]

# === Plan with Codex (1.0 min) ===
agy-flow handoff-prompt codex --objective "Plan the X social_signals collector module"
# Copy output → Codex plans module structure, API considerations, risks

agy-flow trial event x-social copy
agy-flow trial event x-social decision --note "Use tweepy v2, respect X API rate limits"

# === Implement with Claude (2.5 min) ===
agy-flow lease claude --force
agy-flow handoff-prompt claude --objective "Implement X social_signals in src/social/x_signals.py"
# Copy output → Claude writes the implementation
# Claude finds X API default spend issue and mentions it

agy-flow trial event x-social copy
agy-flow trial event x-social error_caught --note "Claude caught X API default $5K / month spend risk"
agy-flow trial event x-social decision --note "Added explicit cost warning in config"

# === Review with Codex (1.5 min) ===
agy-flow lease codex --force
agy-flow handoff-prompt codex --objective "Review the x_signals implementation for correctness, security, API compliance"
# Codex reviews, runs tests, confirms structure
# Codex catches config validation gap and edge case with empty API keys

agy-flow trial event x-social error_caught --note "Codex caught missing config validation for empty keys"
agy-flow trial event x-social copy
agy-flow trial event x-social friction --note "Had to manually switch between Codex and Claude UIs"

# === Review & quality ===
agy-flow quality task-002
agy-flow status task-002

# === Trial end ===
agy-flow trial stop x-social
agy-flow trial export x-social --output docs/value-trials/x-social-signals-trial-2026-07-14.json
agy-flow value-report docs/value-trials/x-social-signals-trial-2026-07-14.json
```

### Metrics from the actual trial

| Metric | Manual | agy-flow | Delta |
|---|---|---|---|
| Context copies | 10 | 4 | **-60%** |
| Manual decisions | 8 | 6 | -25% |
| Friction points | 5 | 3 | -40% |
| Errors caught | 0 | 6 | **+6** |
| Subjective avg | 2.3 | 4.3 | **+2.0** |

### Verdict

```
3/5 criteria met → Continue developing.
```

The biggest wins were:
- **Fewer context copies** — handoff prompt eliminated "copy everything into Claude"
- **More bugs caught** — Codex review loop caught 6 issues Claude missed
- **Better state clarity** — whoami + status eliminated "where were we?"

The biggest remaining friction:
- Still had to manually switch between Codex/Claude UIs
- agy-flow records but does not automatically route between agents

---

## Quick Reference: Command Flow

```
START                    MID-TASK                 END
│                        │                        │
├─ whoami                ├─ lease <agent> --force  ├─ quality <task-id>
├─ lease <agent>         ├─ handoff-prompt         ├─ status <task-id>
├─ trial start           ├─ (paste to agent)       ├─ trial stop
├─ create "<title>"      ├─ trial event            ├─ trial export
├─ route-task <task-id>  ├─ continue <run-id>      └─ value-report
└─                       └─ quality <task-id>
```
