---
presents: in:plan
detail: [in:source, in:plan, report, outcome]
---

# Confirm-skip (you + driver)

`plan` found nothing to deliver: the source is already in the knowledgebase, or adds nothing it lacks. Nothing has been written and no PR exists. Closing an item with nothing delivered is a human call, so it stops here.

1. `lc show STEP`, then read the `plan` artifact, which names the existing doc that covers the source. Open the `source` row beside it.
2. Confirm that the named existing doc really covers the source.
3. Decide:
   - `lc done STEP rejected` - the item ends as abandoned and nothing is written.
   - `lc done STEP changes --note "<what the source does add>"` - `plan` reworks it in this same pass.
4. Do not edit the plan by hand.

@include plain-language
