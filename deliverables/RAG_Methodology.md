# RAG Methodology For Automated Project Health Reporting

## Objective

The agent determines whether a project is **Green**, **Amber**, or **Red** by translating operational project signals into a weighted risk score from `0` to `100`, then overlaying a few hard-stop escalation rules for obviously unhealthy plans.

## Core signals

1. **Schedule health**
   Uses progress vs planned progress, schedule delay, overdue work, and overdue milestones.
2. **Budget burn**
   Compares spend consumed to delivery progress and flags recent overspend trends.
3. **Milestone health**
   Measures delayed milestones and milestones that should have been completed by the reporting date.
4. **Execution blockers**
   Looks at critical blockers, blocked tasks, and unresolved high-priority issues.
5. **Risk exposure**
   Weights active risks by severity, giving critical and high risks more influence.
6. **Stakeholder sentiment**
   Converts recent sponsor or stakeholder feedback into a risk signal.
7. **Resource strain**
   Flags utilization that suggests the team is overloaded or operating without contingency.
8. **Change pressure**
   Used when change-request data exists, especially if high-impact changes are still entering the plan.

## Scoring logic

- Each signal is converted into a `0–100` risk score.
- Example interpretation:
  - `0–34`: healthy
  - `35–64`: watch closely
  - `65–100`: unhealthy
- The overall score is a weighted average of the available signals.
- If a workbook does not contain every signal, the model renormalizes weights instead of forcing missing data to zero.

## Default weights

- Schedule: `27%`
- Budget: `18%`
- Milestones: `13%`
- Execution blockers: `16%`
- Risk exposure: `12%`
- Stakeholder sentiment: `8%`
- Resource strain: `6%`
- Change pressure: `3%`

## RAG thresholds

- **Green**: overall score `< 35` and no hard-stop trigger is active
- **Amber**: overall score `35–64`, or one moderate warning trigger is active
- **Red**: overall score `>= 65`, or a hard-stop trigger is active

## Hard-stop triggers

A project is forced to **Red** even if the blended score is lower when any of the following is true:

- multiple critical blockers are open
- a large share of due work or milestones is overdue
- budget burn is materially ahead of progress while the project is also behind schedule
- critical risks are piling up without mitigation
- task-level execution is severely blocked

## Handling incomplete or messy data

- If one signal is missing, the model scores using the remaining signals.
- If two sources disagree, such as weekly summary progress vs task-level completion, the model uses a conservative blended value and lowers confidence.
- Every report includes a confidence flag and a short assumptions section so leadership can separate project risk from data-quality risk.

## Assumptions

- The latest available row in a weekly status tab is treated as the most recent reported status.
- Dates are evaluated against the report’s explicit as-of date.
- A provided `RAG_Status` column can be used for validation, but not as an input to scoring.
