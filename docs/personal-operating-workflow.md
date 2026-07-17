# Personal Operating Workflow v1 — agent-relay

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
| **agent-relay** | Task record, state tracking, handoff prompt, trial data, quality gate | Every multi-step task |

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
agent-relay whoami

# 2. Take the writer lock (--force if someone else has it, which is fine)
agent-relay lease codex --force

# 3. Start a value trial to track metrics
agent-relay trial start trial-add-auth --task "Add auth middleware" --track agent-relay

# 4. Create the task
agent-relay create "Add auth middleware with JWT support"

# 5. Preview the route
agent-relay route-task task-001
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
agent-relay route "Add auth middleware"
```

This asks the classifier (keyword + score based) and the connector probes
(which CLIs are installed, which API keys are set) to recommend.

But the final call is always yours. The role split above is a default,
not a rule.

---

## 4. Generating a Handoff Prompt for Claude

After Codex has planned the task, or when you know what needs doing:

```bash
agent-relay handoff-prompt claude --objective "Implement X social_signals collector in intelligence-collector/src/social/x_signals.py"
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
You are about to hand off work to **Claude Code** inside the agent-relay
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
- When finished, run: agent-relay submit task-002
```

---

## 5. After Claude Completes: Codex Review

After Claude finishes, the review loop should be manual by default
(writer was human-in-loop) but can be automated with `--mock`:

```bash
# 1. Dispatch a reviewer via the adapter
agent-relay continue run-xxxx --mock

# 2. Or manually: lease the reviewer
agent-relay lease codex --force
agent-relay handoff-prompt codex --objective "Review Claude's implementation for correctness, security, and X API usage"

# 3. Record what happened
agent-relay trial event trial-add-auth error_caught --note "Codex caught X API rate limit edge case"
agent-relay trial event trial-add-auth decision --note "Used tweepy v2 instead of v1"
agent-relay trial event trial-add-auth friction --note "Claude didn't check API key env var name"

# 4. Run tests
python -m pytest intelligence-collector/tests/

# 5. Check quality gate
agent-relay quality task-001

# 6. Review full status
agent-relay status task-001
agent-relay doctor
```

---

## 6. When to Use Antigravity

```bash
# Lease Antigravity as writer
agent-relay lease antigravity --force

# Generate prompt
agent-relay handoff-prompt antigravity --objective "Polish the dashboard UI — fix alignment, add dark mode toggle, clean up CSS"
```

Antigravity is the right choice when the task involves:

- HTML / CSS / frontend framework (React, Vue, etc.)
- UI dashboard modifications
- Visual design decisions (colors, spacing, layout)
- Interaction / animation improvements
- Accessibility review

Antigravity does not write backend logic. Do not send it there.

---

## 7. When NOT to Use agent-relay

agent-relay adds structure and traceability. Not every task needs that.

### Skip agent-relay When

| Situation | Why Not |
|---|---|
| **Less than 5 minutes** (typo fix, one-line change) | Setup overhead > task time |
| **Single file, no review needed** | No handoff needed |
| **Pure chat / learning** (asking a question, reading docs) | No artifact produced |
| **Personal note** (not a coding task) | Not a task |
| **Quick experiment** (might be discarded) | Trial data noise |

### Use agent-relay When

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
| Copy count | `agent-relay trial event <id> copy` | Each time you copy context between agents |
| Decision count | `agent-relay trial event <id> decision --note "..."` | Each time you choose what to do next |
| Friction points | `agent-relay trial event <id> friction --note "..."` | Each time you get stuck or confused |
| Errors caught | `agent-relay trial event <id> error_caught --note "..."` | Each time review/quality catches a real bug |
| Subjective score | Fill in at end: state_clarity, traceability, review_quality (1-5) | After stopping the trial |

### Optional

```bash
agent-relay trial event <id> agent_switch --note "Codex → Claude"
agent-relay trial event <id> artifact --note "generated x_signals.py"
agent-relay trial event <id> note --count 5   # lines of notes taken
```

### Stop and Export

```bash
agent-relay trial stop <id>
agent-relay trial export <id> --output docs/value-trials/<id>-results.json
agent-relay value-report docs/value-trials/<id>-results.json
```

---

## 9. One-Page Cheat Sheet

### 10 Most Common Commands

```bash
# ---------- Session start ----------
agent-relay whoami                          # Who holds the writer lock
agent-relay lease codex --force             # Take the writer lock
agent-relay trial start <id> --task "..."   # Start recording metrics

# ---------- Task lifecycle ----------
agent-relay create "<title>"                # Create task (auto-routes)
agent-relay route-task task-001             # Show recommended route
agent-relay handoff-prompt claude --objective "..."  # Generate Claude prompt

# ---------- Review & quality ----------
agent-relay lease codex --force             # Take reviewer role
agent-relay quality task-001                # Check quality gate
agent-relay status task-001                 # Full task status

# ---------- Trial recording ----------
agent-relay trial event <id> error_caught --note "..."
agent-relay trial stop <id>
agent-relay trial export <id> --output results.json
agent-relay value-report results.json
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
agent-relay whoami
# → writer: none (first task of the day)

agent-relay lease codex --force
# → status: leased, writer: Codex

agent-relay trial start x-social --task "Add X social_signals collector" --track agent-relay

agent-relay create "Add X social_signals collector"
# → task-002

agent-relay route-task task-002
# → primary: claude, fallbacks: [codex, antigravity]

# === Plan with Codex (1.0 min) ===
agent-relay handoff-prompt codex --objective "Plan the X social_signals collector module"
# Copy output → Codex plans module structure, API considerations, risks

agent-relay trial event x-social copy
agent-relay trial event x-social decision --note "Use tweepy v2, respect X API rate limits"

# === Implement with Claude (2.5 min) ===
agent-relay lease claude --force
agent-relay handoff-prompt claude --objective "Implement X social_signals in src/social/x_signals.py"
# Copy output → Claude writes the implementation
# Claude finds X API default spend issue and mentions it

agent-relay trial event x-social copy
agent-relay trial event x-social error_caught --note "Claude caught X API default $5K / month spend risk"
agent-relay trial event x-social decision --note "Added explicit cost warning in config"

# === Review with Codex (1.5 min) ===
agent-relay lease codex --force
agent-relay handoff-prompt codex --objective "Review the x_signals implementation for correctness, security, API compliance"
# Codex reviews, runs tests, confirms structure
# Codex catches config validation gap and edge case with empty API keys

agent-relay trial event x-social error_caught --note "Codex caught missing config validation for empty keys"
agent-relay trial event x-social copy
agent-relay trial event x-social friction --note "Had to manually switch between Codex and Claude UIs"

# === Review & quality ===
agent-relay quality task-002
agent-relay status task-002

# === Trial end ===
agent-relay trial stop x-social
agent-relay trial export x-social --output docs/value-trials/x-social-signals-trial-2026-07-14.json
agent-relay value-report docs/value-trials/x-social-signals-trial-2026-07-14.json
```

### Metrics from the actual trial

| Metric | Manual | agent-relay | Delta |
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
- agent-relay records but does not automatically route between agents

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
