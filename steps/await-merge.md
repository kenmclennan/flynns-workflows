# Await-merge (you + driver)

A PR is green, comments resolved, and rebased on the tip of main - ready to merge. You merge it (lightcycle never merges for you); the driver runs this skill to set it up and record the outcome.

1. `lc show STEP`. The PR is on the phase run: take the `.runs` entry whose `pass` matches the step's `.pass` and whose `phase` is the one this gate sits in (`lc workflow describe <workflow>` names it), and open its `pr` on GitHub. A pass can have more than one run open at once, so match on both - `.pr` is on the claim JSON only, and `lc show` does not carry it.
2. Confirm CI is green and review comments are resolved; summarise the PR for the human.
3. The human merges it on GitHub - their call, their click.
4. The pool's PR monitor closes the item automatically once GitHub shows the merge; run `lc done STEP merged` yourself only if it has not caught up yet.
5. If it needs changes instead of merging, ask for them **on the PR**, not in the store: post a top-level comment mentioning the gate's feedback token (`@lc` in the built-in bundles - the `mention_token` hook on this node names it) saying exactly what to change and why. The pool's PR monitor spawns `handle-feedback`, which decides rework vs answer, replies on the thread carrying `<!-- lc -->` to record that decision, and routes this step for you. Do NOT run `lc done STEP changes` yourself while there is a PR to comment on - it skips the recorded reply, leaves the reviewer's reasoning where no reviewer will look, and never advances the comment ledger. Fall back to `lc done STEP changes --note "..."` only when there is no PR thread to post to.

The merge is the human's irreducible act; you assist and do the bookkeeping.
