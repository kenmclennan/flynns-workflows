---
script: scripts/kb-check.py
accepts:
  branch: required
produces:
  check-report: optional
detail: [outcome, out:check-report, needs, reason]
---

# Check

Engine-owned: no agent claims this stage. `scripts/kb-check.py` runs the moment `write` finishes, in the phase worktree, over the markdown files changed on the phase branch against `origin/main` (committed, modified or untracked). It only reads, so a repeat gives the same answer.

It runs `prettier --check --prose-wrap=never` and `markdownlint-cli2` with the repo's own config, then checks that every relative link in a changed file resolves and is not bundle-absolute, that frontmatter carries the keys the knowledgebase requires (see its `CLAUDE.md`, section "Conformance": `type` on every non-reserved file, none on `index.md`; a `references/` file also needs `resource` and `retrieved_at`), that every changed concept doc is reachable from the root `index.md` by following links, and that every `sources` citation of a `references/` file also appears as a body link.

It prints `clean`, or `broken` after attaching `check-report` (one line per failure: file, then reason) for `write` to read on the next round. Three `broken` results in a row skip `write` and go to `escalate`. A missing `npx`, or a worktree it cannot read, parks the step with the reason and the stderr tail instead.
