# Triage-github-issues

Surfaces open GitHub issues on the lightcycle repos that were not raised before. It raises one inbox item listing them. No agent runs anywhere in the flow, so a firing with nothing new and a firing with something new both spend no tokens.

**Use it when** an operator enables its suggested schedule (`0 9,14 * * 1-5`, named `triage`). It is not filed by hand. The bundle never enables the schedule; an operator does, in config.

**Phases:** none beyond the item itself. The workflow runs once per firing and closes with the item, so it has one pass and no PR.

## Flow

`[ agent ]` is an agent step, `{{ human }}` is a human gate, `([ terminal ])` is where the flow ends.

```text
guard: scripts/new-issues.py (passes when an issue was not raised before)
   |
   v
[ record-raised ]  (script)
   |
   | recorded
   v
{{ triage }}
   |
   |-- triaged   --> ([ done ])
   |
   '-- abandoned --> ([ done ])
```

## Stages

- **Guard** (`scripts/new-issues.py`) looks for open issues on the configured repos that were not raised before, and fails when there are none.
- **record-raised** is a script stage. It marks every listed issue raised in `triage.db` and advances each repo's high-water mark, before the gate. `triaged`, `abandoned` and an item closed by hand therefore all leave the issues marked, and they never come back.
- **triage** is the human gate. For each issue decide to reply on GitHub, file an `lc` item, close it as won't-fix, or leave it. When an issue reports a defect, name the causing item only if that is established. Deferring means filing a follow-up, since the issue will not be listed again. `triaged` and `abandoned` both close the item.

## Operator setup

All config keys are optional: `repos`, `labels`, `ignore-authors`, `lookback-days` and `gh-command` (a recorded-response fake for tests).
