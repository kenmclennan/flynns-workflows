---
summary: loops a Blueprint's delivery plan - one pass per work item through spec/feature/code, then an adversarial design audit before closing
when-to-use: delivering a whole Blueprint's plan as one lc item, instead of filing each work item by hand
---

# Blueprint-delivery

One item, one id, delivering an entire Blueprint's `plan/` by looping. `plan-next` reads the
Blueprint's `plan/` and the target codebase at `origin/main` to decide what is genuinely
undelivered, names the next work item, and sends it through a spec/feature/code arc - three
phases, three PRs, three human gates: a spec is written and merged, gherkin scenarios are derived
from it and merged, then code is implemented to turn every scenario green and merged. Both phases
that put code-repo changes on a PR - feature and code - watch that PR's CI before a reviewer sees
it, so no human ever gates a red branch. The feature phase needs its own gate as much as the code
phase does: it ships scenarios written ahead of their bindings, which stay off CI only while the
repo enforces the `@wip` tag, and that is a property of the target repo rather than of this
workflow. Once that
work item's code PR merges, `cleanup` tears down just that pass's code-phase worktree and routes
back to `plan-next` rather than closing the item - one delivered work item is one pass, not the
whole item.
The item ends only once nothing remains to deliver: at that point `audit-design` adversarially
assesses the WHOLE built system against the WHOLE design, not the item just delivered, and either
files remedial work items into `plan/` - routed through a fourth PR, `plan-open-pr` /
`plan-await-merge`, the human gate for the audit's own judgment - or finds the design holds and
closes the item. `open-pr` and `await-merge` each appear four times now, once per phase (spec,
feature, code, plan); `plan-next` and `audit-design` carry this workflow's own subject matter -
deciding what a Blueprint plan still owes, and auditing a built system against a whole design - and
are new craft, not reused from anywhere. `plan-next` shares the `plan` phase with `audit-design`,
`plan-open-pr` and `plan-await-merge` - every owned stage needs a phase for the graph to compose -
but it reads the Blueprint's `plan/` from that shared `blueprints` worktree and the target codebase
at `origin/main` read-only: it never commits and never opens a PR, so the worktree it is handed goes
unused by design, not by omission.

entry: plan-next

requires: brief repo blueprint

workspace:
  plan-next         blueprints
  spec-writer       specs
  spec-open-pr      specs
  review-spec       specs
  spec-review-rounds  specs
  spec-await-merge  specs
  audit-design      blueprints
  plan-open-pr      blueprints
  plan-await-merge  blueprints

phase:
  plan-next            plan
  spec-writer          spec
  spec-open-pr         spec
  review-spec          spec
  spec-review-rounds   spec
  spec-await-merge     spec
  feature-writer       feature
  feature-open-pr      feature
  feature-watch-ci     feature
  review-features      feature
  feature-review-rounds  feature
  feature-review-ci    feature
  feature-await-merge  feature
  implement-features   code
  code-open-pr         code
  code-watch-ci        code
  review-code          code
  code-review-rounds   code
  code-await-merge     code
  cleanup              code
  resolve-conflict     code
  code-review-ci       code
  handle-feedback      code
  audit-design         plan
  plan-open-pr         plan
  plan-await-merge     plan

nodes:
  spec-open-pr         open-pr
  spec-await-merge     await-merge
  feature-open-pr      open-pr
  feature-watch-ci     watch-ci
  feature-review-ci    review-ci
  spec-review-rounds     review-rounds
  feature-review-rounds  review-rounds
  code-review-rounds     review-rounds
  feature-await-merge  await-merge
  code-open-pr         open-pr
  code-watch-ci        watch-ci
  code-review-ci       review-ci
  code-await-merge     await-merge
  plan-open-pr         open-pr
  plan-await-merge     await-merge

edges:
  plan-next            item-selected    spec-writer
  plan-next            all-delivered    audit-design
  spec-writer          done             spec-open-pr
  spec-open-pr         done             review-spec
  review-spec          done             spec-await-merge
  review-spec          rejected         spec-writer
  spec-await-merge     changes          spec-writer
  spec-await-merge     spec-merged      feature-writer
  feature-writer       done             feature-open-pr
  feature-open-pr      done             feature-watch-ci
  feature-watch-ci     done             review-features
  feature-watch-ci     ci-failed        feature-writer
  review-features      done             feature-await-merge
  review-features      rejected         feature-writer
  feature-await-merge  changes          feature-writer
  feature-await-merge  features-merged  implement-features
  implement-features   done             code-open-pr
  code-open-pr         done             code-watch-ci
  code-open-pr         conflicted       resolve-conflict
  code-watch-ci        done             review-code
  code-watch-ci        ci-failed        implement-features
  review-code          done             code-await-merge
  review-code          rejected         implement-features
  code-await-merge     merged           cleanup
  code-await-merge     changes          implement-features
  code-await-merge     conflicted       resolve-conflict
  code-await-merge     gave-up          review-conflict
  resolve-conflict     resolved         code-open-pr
  resolve-conflict     escalate         review-conflict
  cleanup              done             plan-next
  audit-design         remedial-filed   plan-open-pr
  audit-design         clean            done
  plan-open-pr         done             plan-await-merge
  plan-await-merge     changes          audit-design
  plan-await-merge     plan-merged      plan-next

hooks:
  pr_merge              spec-await-merge     spec-merged
  pr_merge              feature-await-merge  features-merged
  pr_merge              code-await-merge     merged
  pr_merge              plan-await-merge     plan-merged
  pr_close              spec-await-merge     abandoned
  pr_close              feature-await-merge  abandoned
  pr_close              code-await-merge     abandoned
  pr_close              plan-await-merge     abandoned
  pr_feedback           spec-await-merge     handle-feedback
  pr_feedback           feature-await-merge  handle-feedback
  pr_feedback           code-await-merge     handle-feedback
  pr_feedback           plan-await-merge     handle-feedback
  pr_conflict           code-await-merge     conflicted
  pr_conflict_cap       code-await-merge     3
  pr_conflict_escalate  code-await-merge     gave-up
  ci_failed_cap         feature-watch-ci     ci-failed  3  feature-review-ci
  ci_failed_cap         review-spec          rejected   3  spec-review-rounds
  ci_failed_cap         review-features      rejected   3  feature-review-rounds
  ci_failed_cap         review-code          rejected   3  code-review-rounds
  ci_failed_cap         code-watch-ci        ci-failed  3  code-review-ci
  mention_token         spec-await-merge     @lc
  mention_token         feature-await-merge  @lc
  mention_token         code-await-merge     @lc
  mention_token         plan-await-merge     @lc
  review_bot_allowlist  code-await-merge     copilot-pull-request-reviewer[bot]

signals:
  spec-await-merge     resets            changes
  review-spec          review_rounds     rejected
  review-spec          resets            rejected
  review-features      review_rounds     rejected
  review-features      resets            rejected
  feature-await-merge  resets            changes
  review-code          review_rounds     rejected
  review-code          resets            rejected
  code-open-pr         conflicts         ~conflict
  feature-watch-ci     resets            ci-failed
  code-watch-ci        resets            ci-failed
  code-await-merge     resets            changes
  resolve-conflict     resolve_attempts  escalate
  plan-await-merge     resets            changes
