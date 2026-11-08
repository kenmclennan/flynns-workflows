# Close-delivered-issues

Proposes closes for open GitHub issues on the lightcycle repos whose fix has merged. It raises one inbox item, and closes nothing without a human approving it. No agent runs anywhere in the flow, so a quiet firing spends no tokens and files nothing.

**Use it when** an operator enables its suggested schedule (`0 10 * * 1-5`, named `issue-close`). It is not filed by hand. The bundle never enables the schedule; an operator does, in config.

**Phases:** none beyond the item itself. The workflow runs once per firing and closes with the item, so it has one pass and no PR.

## Flow

`[ agent ]` is an agent step, `{{ human }}` is a human gate, `([ terminal ])` is where the flow ends. Every stage here is a script except the one gate.

```text
guard: scripts/delivered-issues.py (passes when an issue is new or changed)
   |
   v
[ record-proposed ]  (script)
   |
   | recorded
   v
{{ review-closes }}
   |
   |-- approved --> [ close-issues ] (script) --closed--> ([ done ])
   |
   '-- declined --> ([ done ])
```

## Stages

- **Guard** (`scripts/delivered-issues.py`) lists open issues that an `lc` item refers to. It sorts them into "proposed closes" (every referring item is done and completed with a merged PR) and "needs a look" (anything else), and fails when nothing is new or changed. An issue shown once is not proposed again until a referring item is added or changes state.
- **record-proposed** is a script stage. It records every shown issue with its fingerprint in `delivered.db` before the gate, so a decline, a partial approval and an item closed by hand all leave it recorded.
- **review-closes** is the human gate. Attach the approved set (all proposed closes, or a named subset) and finish `approved`, or attach an empty set and finish `declined`. Only proposed closes can be approved; "needs a look" issues are followed up by hand.
- **close-issues** is a script stage. It re-checks each approved issue live, skips any that is no longer a proposed close or is already closed, and closes the rest with a comment naming the PRs and items that fixed them. Its closing note lists what it closed and skipped. A re-run after a failure is safe.

## Operator setup

`repos`, `gh-command` and `lc-command` are all required, and the guard and the `close-issues` stage fail naming any that is unset. `gh-command` and `lc-command` name the `gh` and `lc` binaries (a recorded-response fake in tests); `repos` is a comma-separated list of `owner/repo`.
