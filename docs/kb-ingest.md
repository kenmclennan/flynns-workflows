# Kb-ingest

Takes one approved source into the knowledgebase (`kenmclennan/knowledgebase`) through a plan, a PR and a human merge. File an item for it with `--repo kenmclennan/knowledgebase` and the source URL or URLs in the brief.

- **plan** reads the source and the knowledgebase and writes the ingest plan as an item artifact: the reference mirror, each new concept doc, each fold, each supersession, and the cross-links in both directions.
- **confirm-skip** is a human gate reached only when `plan` finds the source already in or adding nothing: `rejected` ends the item, `changes` returns to plan.
- **review-plan** is an agent that reads the plan and the source against the knowledgebase's `CLAUDE.md`. `approved` goes on, `changes` returns to plan, `escalate` hands it to a human. No plan document is ever committed to the knowledgebase; the plan is quoted in the PR body instead.
- **write** builds the approved plan on a branch, and nothing more.
- **check** is a script stage that spends no tokens: prettier, markdownlint, relative links, required frontmatter, reachability from an `index.md`, every cited reference linked in the body, every `addresses:` path resolving, and each Problem doc's "What responds to it" list matching the docs that address it.
- **cold-read** is a cold reader that reads only the changed concept docs, explains each back and lists what is unclear. `clear` goes on to review; `unclear` returns to write.
- **review** reads the diff against the plan and the knowledgebase's conventions.
- **open-pr**, **poll-ci**, **watch-ci** and **await-merge** are the generic PR machinery. Merging is the only human gate on the normal path.
- **escalate** takes three `broken` checks in a row, or the review rounds cap, which `review-plan`, `cold-read` and `review` share, and decides between replanning, reworking the docs on the existing branch, and abandoning.

```text
[ plan ] -> [ review-plan ] -> [ write ] -> [ check ] -> [ cold-read ] -> [ review ] -> [ open-pr ] -> [ poll-ci ] -> [ watch-ci ] -> {{ await-merge }} -> ([ completed ])
   |           |  changes -> plan     ^  broken        |  unclear -> write      |  rejected -> write
   |           |  escalate -> {{ escalate }}
   |  nothing-to-add -> {{ confirm-skip }}  (changes -> plan | rejected -> ([ abandoned ]))
   ({{ escalate }}: reached from check broken x3, or review-plan, cold-read or review past the rounds cap -> replan | rework (-> write) | abandoned)
```

Every convention the steps follow lives in the knowledgebase's own `CLAUDE.md`. A source is already in when `references/` holds a file whose `resource:` is its URL, so the workflow keeps no state of its own.

## Operator setup

Set `checkout-path` to Ken's local checkout of the knowledgebase. The hourly `maintain` hook fast-forwards it when it is on `main` and clean, then runs `qmd update && qmd embed`. `qmd-command` is required and names the `qmd` binary (a fake in tests); the install skips its PATH check when unset, and `maintain` fails naming it.

The knowledgebase's `.github/workflows/lint.yml` should be on its `main` before the first live ingest, so `poll-ci` has a CI run to watch. Without it the PR waits on the merge gate alone.
