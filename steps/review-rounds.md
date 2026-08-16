# Review-rounds (you + driver)

A reviewer has rejected this phase's work enough times that the author is not converging on its own. Rather than let the reject/rework loop run unbounded and unseen, the cap routes it here so a human decides what happens next.

1. `lc show STEP` for the latest rejection; `lc trace ITEM` shows every prior `rejected` note at this stage in sequence, so you can see whether it is the same finding recurring or new ground each round. Those mean opposite things: the same finding twice is the author fixing the instance rather than the class, or a reviewer whose note names the defect without naming the remedy; new ground each round is a large piece of work being swept properly and may just need another pass.
2. Read the reviewer's own reflections (`lc show` on the reject steps) before deciding. A reviewer that keeps finding the same shape is evidence about the step prompts, not only about this item.
3. Decide: send it back with your own note on what to change; accept it as-is and move the phase on by hand; leave it blocked; or abandon the item. If the rounds exposed a defect in the step prompts themselves, that is a separate change to the origin - do not fix it inside this item.
4. `lc done STEP reviewed` either way - reviewing it is the acknowledgement.
