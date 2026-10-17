# Kb-ingest

Takes one approved source into the knowledgebase (`kenmclennan/knowledgebase`) through a plan, a PR and a human merge. File an item for it with `--repo kenmclennan/knowledgebase` and the source URL or URLs in the brief.

- **plan** reads the source and the knowledgebase and writes the ingest plan as an item artifact: the reference mirror, each new concept doc, each fold, each supersession, and the cross-links in both directions.
- **review-plan** is the first human gate, read in the inbox. `approved` goes on, `changes` returns to plan, `rejected` ends the item. No plan document is ever committed to the knowledgebase.
- **write** builds the approved plan on a branch, and nothing more.
- **check** is a script stage that spends no tokens: prettier, markdownlint, relative links, required frontmatter, reachability from an `index.md`, and every cited reference linked in the body.
- **review** reads the diff against the plan and the knowledgebase's conventions.
- **open-pr**, **poll-ci**, **watch-ci** and **await-merge** are the generic PR machinery. Merging is the second gate.
- **escalate** takes three `broken` checks in a row, or the review rounds cap, and decides between replanning and abandoning.

Every convention the steps follow lives in the knowledgebase's own `CLAUDE.md`. A source is already in when `references/` holds a file whose `resource:` is its URL, so the workflow keeps no state of its own.

## Operator setup

Optionally set `checkout-path` to Ken's local checkout of the knowledgebase. The hourly `maintain` hook fast-forwards it when it is on `main` and clean, then runs `qmd update && qmd embed`. `qmd-command` is optional and points at a fake `qmd` in tests.

The knowledgebase's `.github/workflows/lint.yml` should be on its `main` before the first live ingest, so `poll-ci` has a CI run to watch. Without it the PR waits on the merge gate alone.
