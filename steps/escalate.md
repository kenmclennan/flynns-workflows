---
escalation: true
presents: in:description
detail: [in:description, in:report, outcome]
---

# Escalate (you + driver)

This ingest is not converging: `check` returned `broken` three times in a row, or `review` rejected the diff past the rounds cap. Nothing has been merged. `write` is not going to fix it by itself, and a human has to say whether the plan or the source was the problem.

**Read this before running anything.** `abandoned` has no outgoing route. Completing this step with it, as the item's only open step, closes the item and deletes every branch it recorded, local and remote. `replan` is the only outcome that continues.

1. `lc show STEP` for what routed here. `lc trace ITEM` shows every `check-report` and `review` rejection in order, and the `plan` artifact is on the item (`lc show ITEM`).
2. Read what the sequence says, because the two shapes need opposite responses. The same failure every round means the plan asks for something `write` cannot build as written: a link target that does not exist, a claim the source does not support, a supersession that breaks other docs. Change the plan. A different failure each round is usually a large change being worked through, or a convention the plan never mentioned.
3. Decide:
   - **Replan.** `lc done STEP replan --note "<what the plan got wrong and what to change>"` (-> plan). The branch and its commits stay; the next `write` builds the new plan on top of them.
   - **Abandon.** `lc done STEP abandoned`. The source is not worth the effort, or is wrong for the knowledgebase.
   - **Leave it parked.** Do not run `lc done` at all. This is the right choice whenever you are not sure.

@include plain-language
