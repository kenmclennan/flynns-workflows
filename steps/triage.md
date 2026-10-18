---
presents: in:description
detail: [in:description, report, outcome]
---

# Triage (you + driver)

One item lists GitHub issues on the lightcycle repos that were not raised before. Every one is already recorded as raised, so none will be listed again whatever you decide here.

1. `lc show STEP`, then read the item description: issues grouped by repo, one line each with link, title, author and a one-line summary.
2. For each issue decide one of: reply on GitHub, file an `lc` item for it, close it as won't-fix, or leave it.
3. Deferring an issue means filing a follow-up item or a note for it, not leaving it listed - it will not be raised again.
4. `lc done STEP triaged` once every issue has a decision.
5. To drop the whole batch, `lc done ITEM abandoned`. Both outcomes close the item and neither writes state.
