---
presents: artifact:findings
---

# Review-findings (you + driver)

One item lists where the lightcycle plugin's skills have drifted from the current engine and official workflows. The workflow files nothing itself: you decide what becomes work.

1. `lc show STEP`, then read the `findings` digest and the item description, which names which repos moved. Each finding ends with the `file:line` it concerns.
2. For each finding decide one of: file an `lc` item for it, fix it in place, or discard it.
3. A finding left unfiled is not carried forward. The next firing starts from the new SHAs and raises it again only if the drift persists and is found again.
4. `lc done STEP reviewed` once every finding has a decision.
5. To drop the whole batch, `lc done ITEM abandoned`. Both outcomes close the item.
