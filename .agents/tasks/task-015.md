# Task: task-015 - Display X API cost and social query preset metadata in intelligence daily report

## Metadata
- **ID**: task-015
- **Title**: Display X API cost and social query preset metadata in intelligence daily report
- **Assigned Agent**: claude->codex->deepseek
- **Status**: Todo
- **Created Time**: 2026-07-14 17:12:31

## Requirements & Spec
*Describe the functional requirements and technical specifications for this task here.*

## Acceptance Criteria
*List the test cases or verification steps that must pass.*

## Routing Plan
- **Task Type**: logic_or_backend
- **Confidence**: 0.72
- **Selected Agent**: claude -> codex
- **Selection Source**: plan
- **Strategy**: cheap-first, escalate-on-uncertainty
- **Budget Bias**: subscription_or_low_metered

### Recommended Pipeline
1. claude (implementer): logic-heavy coding, tests, and CLI execution
2. codex (human_in_loop_implementer): IDE-assisted debugging, refactor, and manual polish
3. deepseek (reviewer): low-cost diff review before final handoff
