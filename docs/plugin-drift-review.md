# Plugin-drift-review

Finds where the lightcycle plugin's skills have drifted from the engine and the official workflows. It raises one inbox item listing the drift and files and edits nothing itself.

**Use it when** an operator enables its suggested schedule (`0 8 * * *`, named `plugin-drift`). It is not filed by hand. The bundle never enables the schedule; an operator does, in config.

**Phases:** none beyond the item itself. The workflow runs once per firing and closes with the item, so it has one pass and no PR.

## Flow

`[ agent ]` is an agent step, `{{ human }}` is a human gate, `([ terminal ])` is where the flow ends.

```text
guard: scripts/moved.py (passes when a repo's main SHA has moved)
   |
   v
[ check-references ]  (script)
   |
   | clean / misses
   v
[ review-skills ]  (agent)
   |
   |-- findings --> {{ review-findings }} --reviewed--> ([ done ])
   |                        |
   |                        '-- abandoned --> ([ done ])
   |
   '-- clean --> ([ done ])
```

## Stages

- **Guard** (`scripts/moved.py`) fetches the engine, the official workflows and the plugin, and passes only when one of their `main` SHAs has moved since the last review.
- **check-references** is a script stage. It checks every name the plugin's skills mention in code spans and fenced blocks (verbs, flags, config keys, doctor findings, stages, step and workflow names) against snapshots of the engine and workflows. A miss can be a false positive. It attaches `missing-references`, `review-context` (snapshot paths and SHAs, since an agent stage gets neither the data directory nor the guard's state) and `changes-since`. Both `clean` and `misses` go on to `review-skills`.
- **review-skills** is the only agent stage. It reads the skills against the engine and workflows inside those snapshots and reports what they get wrong or do not teach, each finding ending with the `file:line` it concerns. `clean` closes the item.
- **review-findings** is the human gate. Decide per finding whether to file an item, fix it in place or discard it. `reviewed` and `abandoned` both close the item. A finding left unfiled is not carried forward; it is raised again only if the drift persists.

## Operator setup

All config keys are optional: `engine-url`, `workflows-url`, `plugin-url` and `skills-path`. The bundle also runs a daily maintenance script (`0 7 * * *`).
