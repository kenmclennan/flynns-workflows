---
presents: artifact:findings
---

# Review-kb-findings (you + driver)

One item lists where the knowledgebase has gone stale, come unlinked or stopped following its conventions. The workflow files and edits nothing itself: you decide what becomes work. The audited sha is already recorded, so none of this is raised again unless the next tip still shows it.

1. `lc show STEP`, then read the `findings` digest. Each entry ends with the path it concerns and names the follow-up it suggests.
2. For each finding decide one of: file a `kb-ingest` item (a rewrite, a supersession or a new reference), file a `small-change` item (a repair), fix it in place, or leave it. File against `kenmclennan/knowledgebase`.
3. A finding left unfiled is not carried forward. The next firing starts from the new tip and raises it again only if it is still true and is found again.
4. `lc done STEP filed` once follow-up items are filed. `lc done STEP reviewed` when every finding was read and decided but nothing was filed. `lc done STEP done` when nothing was worth acting on.
5. All three outcomes close the item.
