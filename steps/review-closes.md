---
presents: in:description
produces:
  approved: required
detail: [in:description, out:approved, report, outcome]
---

# Review-closes (you + driver)

One item lists open GitHub issues whose referring `lc` items have finished. "Proposed closes" are issues where every referring item is done and completed with a merged PR. "Needs a look" is everything else. Every issue listed is already recorded as shown, so none is proposed again until a referring item changes.

1. `lc show STEP`, then read the item description: issues grouped by repo, one line each with link, title, the referring items and the merged PRs.
2. To close issues, attach the approved set: `lc attach ITEM approved '{"issues": ["kenmclennan/lightcycle#12", "kenmclennan/lightcycle-plugin#7"]}' --replace`. To approve everything proposed, list every issue under "Proposed closes". Only proposed closes can be approved; the close stage skips anything else.
3. `lc done STEP approved`. The close stage comments on and closes each approved issue still open, and records what it closed in the closing note.
4. To close nothing, attach an empty set first so the step can finish: `lc attach ITEM approved '{"issues": []}' --replace`, then `lc done STEP declined`. Issues under "Needs a look" are for you to follow up by hand; this workflow never closes them.
