# DOGFOOD — loderunner

_Session: 2026-04-23T14:41:49, driver: pty, duration: 1.5 min_

**PASS** — ran for 1.2m, captured 15 snap(s), 1 milestone(s), 0 blocker(s), 0 major(s).

## Summary

Ran a rule-based exploratory session via `pty` driver. Found no findings worth flagging. Game reached 77 unique state snapshots. Captured 1 milestone shot(s); top candidates promoted to `screenshots/candidates/`.

## Findings

### Blockers

_None._

### Majors

_None._

### Minors

_None._

### Nits

_None._

### UX (feel-better-ifs)

_None._

## Coverage

- Driver backend: `pty`
- Keys pressed: 589 (unique: 58)
- State samples: 113 (unique: 77)
- Score samples: 0
- Milestones captured: 1
- Phase durations (s): A=40.7, B=20.2, C=9.1
- Snapshots: `/home/brian/AI/projects/tui-dogfood/reports/snaps/loderunner-20260423-144037`

Unique keys exercised: +, ,, -, ., /, 0, 1, 2, 3, 4, 5, :, ;, =, ?, H, R, [, ], a, b, backspace, c, ctrl+l, d, delete, down, end, enter, escape, f1, f2, h, home, j, k, l, left, m, n ...

## Milestones

| Event | t (s) | Interest | File | Note |
|---|---|---|---|---|
| first_input | 0.3 | 0.0 | `loderunner-20260423-144037/milestones/first_input.txt` | key=right |
