# Review-ci (you + driver)

CI has failed on this item enough times that the phase's author agent kept reworking it without landing a green run - `implement-features` on a code PR, `feature-writer` on a PR of gherkin scenarios. It is not converging on its own; a human needs to look at the accumulated failure notes and decide what happens next. `lc show STEP` carries `.phase`, which tells you which PR this is.

1. `lc show STEP` - the forwarded note carries the latest failing job/test; `lc trace ITEM` shows every prior `ci-failed` note in sequence, so you can see whether it is the same failure repeating or a new one each time.
2. Decide: fix it by hand and push to the branch yourself; leave it blocked; abandon the item; or re-arm the author - `lc new step "<implement-features|feature-writer>: <title>" --parent ITEM` (or `lc set STEP --state ready` style unblock) once you know what should change, with a note on what to try differently so the next pass does not repeat the same failure.
3. `lc done STEP reviewed` either way - reviewing it is the acknowledgement.
