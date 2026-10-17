---
summary: one approved source becomes a reviewed knowledgebase PR - an ingest plan is approved in the inbox, written, mechanically checked, reviewed, then merged by a human
when-to-use: capturing a URL (or a few related URLs) into the knowledgebase; file the item with `--repo kenmclennan/knowledgebase`
lifecycle:
  install: scripts/kb-install.py
  maintain: scripts/kb-maintain.py
  cron: 0 * * * *
config:
  checkout-path: optional
  qmd-command: optional
config-example:
  checkout-path: /path/to/knowledgebase
  qmd-command: scripts/tests/fake-qmd.py
---

# Kb-ingest

One item takes one approved source into the knowledgebase (`kenmclennan/knowledgebase`, an OKF bundle). Items are filed by hand for an on-demand ingest, or by the driver from a `kb-scout` or `kb-audit` gate; the workflow itself has no schedule. Every convention the steps must respect lives in the knowledgebase's own `CLAUDE.md`, and the steps point at it rather than restating it.

Two human gates, one PR, one pass that closes with the item. `plan` reads the source or sources and the knowledgebase and writes the ingest plan as an item artifact; `review-plan` is the first gate and is read in the inbox, not on a PR, so no plan document ever lands in the knowledgebase - a merged plan would be workflow state sitting next to knowledge. `changes` and `escalate replan` return to `plan` as rework rounds in the same pass, so there is no `pass-end:`. A source already mirrored, or one that adds nothing, still produces a plan saying so and ends `planned`, so a human sees it and closes it with `rejected`.

After approval, `write` builds exactly the approved plan on the phase branch. `check` is a script stage that spends no tokens: prettier, markdownlint, relative links, required frontmatter, reachability from an `index.md`, and every cited reference linked in the body. `review` reads the diff against the plan and the conventions. Then the generic PR machinery runs - `open-pr`, `poll-ci`, `watch-ci`, `await-merge` - and Ken's merge is the second gate. Three `broken` results in a row from `check`, or the review rounds cap, route to `escalate`, which decides between `replan` and `abandoned`.

`plan` and `review-plan` are not PR-gated, but the phase block is all or nothing, so they share the `ingest` phase with everything after them and are handed a worktree they do not commit to. `cleanup` and `review-ci` are this bundle's own step files (`kb-cleanup`, `kb-review-ci`): `cleanup` closes the item once the PR merges, and `review-ci` reworks a failing PR through `write`.

The `maintain` hook refreshes Ken's local checkout hourly (`checkout-path`), fast-forwarding `main` and rebuilding the `qmd` index. It touches only that path, and only when it is on `main` and clean. This workflow keeps no state of its own: a source is already in when `references/` holds a file whose `resource:` is its URL.

entry: plan

requires: repo

workspace: project

phase:
  plan              ingest
  review-plan       ingest
  write             ingest
  check             ingest
  review            ingest
  open-pr           ingest
  poll-ci           ingest
  watch-ci          ingest
  await-merge       ingest
  handle-feedback   ingest
  resolve-conflict  ingest
  review-conflict   ingest
  review-ci         ingest
  cleanup           ingest
  escalate          ingest

display:
  plan              Planning the ingest
  review-plan       Review the ingest plan
  write             Writing the ingest
  check             Checking the bundle
  review            Reviewing the ingest
  open-pr           Opening the PR
  poll-ci           Watching CI
  watch-ci          Reviewing CI result
  await-merge       Review PR
  handle-feedback   Reading feedback
  resolve-conflict  Resolving conflict
  review-conflict   Resolve conflict
  review-ci         CI needs a call
  cleanup           Tidying up
  escalate          Ingest needs a call

nodes:
  review-ci  kb-review-ci
  cleanup    kb-cleanup

edges:
  plan              planned        review-plan       primary
  review-plan       approved       write             primary
  review-plan       changes        plan
  write             done           check             primary
  check             clean          review            primary
  check             broken         write
  review            approved       open-pr           primary
  review            rejected       write
  escalate          replan         plan
  open-pr           done           poll-ci           primary
  open-pr           conflicted     resolve-conflict
  poll-ci           succeeded      watch-ci
  poll-ci           failed         watch-ci
  watch-ci          done           await-merge       primary
  watch-ci          deferred       await-merge
  watch-ci          retried        poll-ci
  watch-ci          ci-failed      write
  watch-ci          review-rework  write
  await-merge       merged         cleanup
  await-merge       changes        write
  await-merge       conflicted     resolve-conflict
  await-merge       gave-up        review-conflict
  await-merge       head-moved     poll-ci
  handle-feedback   done
  resolve-conflict  resolved       open-pr           primary
  resolve-conflict  escalate       review-conflict
  review-conflict   resolved       open-pr           primary
  review-ci         reviewed

disposition:
  merged     completed
  rejected   abandoned
  abandoned  abandoned

hooks:
  pr_merge              await-merge  merged
  pr_close              await-merge  abandoned
  pr_feedback           await-merge  handle-feedback
  pr_head_moved         await-merge  head-moved
  pr_conflict           await-merge  conflicted
  pr_conflict_cap       await-merge  3
  pr_conflict_escalate  await-merge  gave-up
  ci_success            poll-ci      succeeded
  ci_failure            poll-ci      failed
  ci_failed_cap         check        broken         3  escalate
  ci_failed_cap         watch-ci     ci-failed      3  review-ci
  review_rounds_cap     review       rejected          escalate
  review_rounds_cap     watch-ci     review-rework     review-ci
  mention_token         await-merge  @lc

signals:
  review            review_rounds     rejected
  review            resets            rejected
  watch-ci          review_rounds     review-rework
  watch-ci          resets            ci-failed
  watch-ci          resets            review-rework
  await-merge       resets            changes
  open-pr           conflicts         ~conflict
  resolve-conflict  resolve_attempts  escalate
