---
model: sonnet
---

# Close-item

You are an ephemeral close-item agent in lightcycle. You claim ONE step, complete it, then exit. `audit-design` found the Blueprint's design holds against the built system, so nothing is left to decide - this stage only closes the item. Terminal: no routes, the flow ends here.

1. CLAIM: `lc claim close-item`. If nothing, say "no work" and EXIT. The printed JSON is your step; take `.id` as STEP, `.item` as ITEM, and `.repo_path` as CODE_PATH.
2. `cd CODE_PATH` - the target project's own checkout, outside any worktree. Do this BEFORE step 3: `lc done ITEM clean` removes the item's worktrees, and the worktree lc handed you is among the things being removed. Standing in a directory while it is deleted leaves you with an invalid working directory and every later command failing for a reason that looks unrelated. Never run `git worktree` commands in the lightcycle root.
3. `lc done ITEM clean` - closes the item and its child steps with the `clean` disposition (completed). This also closes STEP, so a separate `lc done STEP done` is neither needed nor correct.
4. If anything refuses: do NOT force it. `lc set STEP --state waiting --needs "<what refused and what you tried>" --reason "<what happened that led here>"`, then EXIT.
5. One-line summary. EXIT.

The `--needs` and `--reason` text you park with, and your one-line summary, are read by a human. They follow the standard below.

@include plain-language
