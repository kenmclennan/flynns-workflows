# Review-rounds (you + driver)

A reviewer has rejected this phase's work enough times that the author is not converging on its own. Rather than let the reject/rework loop run unbounded and unseen, the cap routes it here so a human decides what happens next.

**Read this before running anything.** This stage has no outgoing route. `lc done STEP <anything>` therefore creates no next step, and if this is the item's only open step the engine cascades: the item closes and every branch it recorded is deleted, **local and remote**, including the head branch of the open PR under review. That is the correct behaviour only when you mean to abandon the whole Blueprint delivery. It is not an acknowledgement, and there is no undo.

1. `lc show STEP` for the latest rejection; `lc trace ITEM` shows every prior `rejected` note at this stage in sequence, so you can see whether it is the same finding recurring or new ground each round. Those mean opposite things: the same finding twice is the author fixing the instance rather than the class, or a reviewer whose note names the defect without naming the remedy; new ground each round is a large piece of work being swept properly and may just need another pass.
2. Read the reviewer's own reflections (`lc show` on the reject steps) before deciding. A reviewer that keeps finding the same shape is evidence about the step prompts, not only about this item.
3. Decide, and use the matching mechanism - they are not interchangeable:
   - **Send it back to the author.** Create the next step FIRST, while this one is still open, so the cascade cannot fire: `lc new step "<title>" --parent ITEM --step <implement-features|feature-writer>` (the `--step` flag is what assigns the role; a role prefix in the title does nothing). Put what to change in its note. Only then `lc done STEP reviewed`. Be aware the cap counter does not reset - the count of prior rejections at the reviewing stage still stands, so the next single rejection escalates here again immediately.
   - **Leave it parked.** Do nothing. Do not run `lc done` at all - the step stays in the inbox and the item stays alive. This is the right choice whenever you are not sure.
   - **Abandon the whole item.** `lc done ITEM merged` (or your chosen reason) closes it deliberately and tears down its worktrees and branches. Do this on the item, never by completing this step and letting the cascade do it silently.
4. If the rounds exposed a defect in the step prompts themselves, that is a separate change to the origin - do not fix it inside this item.
