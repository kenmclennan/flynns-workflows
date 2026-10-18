---
presents: in:plan
detail: [in:source, in:plan, report, outcome]
---

# Review-plan (you + driver)

`plan` has read the source and the knowledgebase and written an ingest plan. Nothing has been written into the knowledgebase yet and no PR exists. Your decision here is the approval the knowledgebase's `CLAUDE.md` asks for before anything lands in a concept doc.

1. `lc show STEP`, then read the `plan` artifact. Check it against the knowledgebase's `CLAUDE.md` at `origin/main`: does each new concept carry one claim, is a fold chosen over a duplicate where a doc already exists, is each supersession justified, is each cross-link a real connection in both directions, and does it reach into other topics.
   The `source` row is the article; open it to read the original beside the plan.
2. If the plan says the source is already mirrored or adds nothing, confirm that, then close with `rejected`.
3. Decide:
   - `lc done STEP approved` - `write` builds exactly this plan and nothing more.
   - `lc done STEP changes --note "<what to change, naming the doc or link>"` - `plan` reworks it in this same pass.
   - `lc done STEP rejected` - the source is not wanted, or is already in. The item ends as abandoned and nothing is written.
4. Do not edit the plan by hand. A change that matters goes back through `changes`, so the artifact on the item stays the one `review` holds the diff against.

@include plain-language
