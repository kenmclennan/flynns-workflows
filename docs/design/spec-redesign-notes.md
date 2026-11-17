# Spec Redesign Notes

These notes describe a new spec format and the workflow around it. The workflow will be built in this origin as an experiment. If it works, it replaces `spec-driven` and `bdd-driven` in the `lightcycle` origin.

## Design goals

The spec format and its workflow are designed to meet three goals.

1. **The agent knows what must be true when the change is done.** Each statement in the spec has one reading. The spec gives the reason for each statement, so the agent can decide sensibly where the spec is silent. It also says what must not change.
2. **Running checks decides whether the delivered software meets the spec.** An agent's judgement does not decide it. The agent that builds the change cannot alter the expected results. Some statements cannot be checked by running anything, such as whether a boundary is in the right place. Each statement in the spec therefore says how it is verified: by a check that runs, or by review.
3. **The person who approves the spec is able to make a real decision about it.** They can write it, contribute to it, read it, digest it, understand it, amend it and approve it. The person and the agent normally write the spec together. Whether the person can do these things depends on the spec's language, phrasing, structure, format and ordering, and on the context it gives, not only on its length.

The third goal exists to avoid human-in-the-loop theatre. That is the name the Thoughtworks Technology Radar gives to an approval step where a person signs off work without a real means of judging it.

## The three parts of a spec

A spec describes one change to a system. A person and an agent write it together, and the person approves it before an agent builds the change. It has three parts. Each part answers a different question about the change.

- **Behaviour:** what will the system do differently, as seen by someone using it?
- **Quality:** which property of the system must hold or improve, such as speed, reliability or ease of maintenance, and what figure shows it?
- **Architecture:** which structural decisions does the change make, such as where the code lives and which boundaries it crosses?

Every change has an answer to all three questions, and often one of the answers is short. A new feature is mostly a change of behaviour. It still has to be placed somewhere in the code, and it must not make the system slower or harder to maintain. A refactor is mostly a change of structure. Its answer on behaviour is that nothing a user sees will change.

The parts are kept separate so that each can be reviewed in its own terms. A reviewer judges behaviour by asking whether it is what the user needs, and judges an architectural decision by asking whether it is sound. The human reviewer approves all three parts.

Each part serves one of two goals:

1. Deliver or refine the user's experience of, and satisfaction with, the application.
2. Keep a system that is stable, efficient, cost effective, free of bugs, understandable and maintainable, so we can keep developing on it efficiently.

The table compares the three parts.

| Aspect | Behaviour | Quality | Architecture |
| --- | --- | --- | --- |
| States | What the system does that someone can observe | A property the system must have, with a figure | The structural decisions: where the change lives, which boundaries and contracts it touches, what data it owns |
| Changes that are mostly about this part | New features, changed behaviour, removed features | Performance and reliability work | Structural improvements and refactors |
| A bug fix belongs here when | The fault is in observable behaviour | The fault is in reliability or an implementation detail | Not settled |
| Goal it serves | Goal 1 | Goal 2 | Goal 2 |
| Reason given | The user need, the driver for the capability, or an external force such as a regulatory or legal requirement | The cost of the current state | The reasoning behind each decision, including the options rejected |
| Evidence needed before the change | None for new behaviour. A reproduction for a bug. | A measurement or a reproduction of the current state | Not settled |
| Shown to be done by | The scenarios in the spec, which run | The check in the spec, which runs against a threshold | Not settled |
| What is kept after the merge | The scenarios | The check, so a later change cannot undo the improvement | Not settled |
| When the change does not touch this part | "Behaviour preserved" | "Existing checks still pass" | "No architectural change, follows the existing pattern" |

A part the change does not touch takes one line, or is left out. A small fix should not need three sections.

## The parts of a spec that run

A spec contains statements that run as checks against the system, and prose that does not run.

- **What runs:** the scenarios in the behaviour part, and the checks in the quality part. The text in the spec is what gets executed. Nobody rewrites it into a separate test, so the expected results that the person approved are the ones the system is checked against.
- **What does not run:** the reason for each part, and the architectural decisions that cannot be expressed as a check. These are written for the reader and verified by review.

This follows the established meaning of "executable specification". Dave Farley's phrasing is that "a good acceptance test is an executable specification of the behaviour of the system". The knowledgebase page `specifying-work/write-the-spec-as-a-test-that-runs.md` gives the sources.

Two limits apply to the parts that run. They show only what their examples cover, so behaviour that no scenario describes is unspecified. And a scenario can still be edited to match wrong code, so a change to a scenario needs a person's approval.

## The quality part

The quality part of a spec states a quality goal: a property the system should have after the change. A quality goal has three elements.

1. **Evidence of the current state:** a measurement or a reproduction. For example: the query takes 4 seconds, this module has 14 dependencies, this input crashes.
2. **The target, written as a check:** for example: under 500 ms, no imports from the adapter layer, the input returns an error message.
3. **The constraint:** apart from the target, what a user sees does not change. The existing tests show this.

Two rules follow from this.

- **Evidence comes before the change:** a change that claims to improve a quality shows the current state first. If nobody can produce the evidence, the problem has not been shown to exist.
- **The check stays in the repository:** the target keeps running as a check after the merge, so a later change cannot undo the improvement. Architects call this a fitness function. Lightcycle's ratchet entries already work this way.

A quality scenario and a behaviour scenario have the same shape: a starting state, an event and an outcome. A behaviour outcome is a fact. A quality outcome is a figure with a threshold. One scenario format may be able to serve both parts.

## The plan

An agent needs more than the spec to build a change. It needs to know which files to edit, which call sites are affected, and which claims about the existing code have been checked. These notes call that content the mechanics. In the specs that the `spec-driven` workflow writes today, the mechanics are most of the document, and a person cannot usefully review them.

In the new format the mechanics go in a separate document, the plan. An agent writes the plan from the approved spec by reading the code. The plan may not change the spec. If the planner finds that a part of the spec is wrong, it stops and asks.

## Spec lifecycle

This section describes an approach to explore. It is not settled. It comes from a working agreement on specification-driven development that is not yet in a repository.

A spec describes one change, so its work is finished when the change is delivered. At that point the spec is archived. An archived spec is a record of what was agreed, built and verified. Nobody edits it afterwards, and later work does not read it as the current description of the system.

Some of what a spec says has to stay true after the change is delivered. A scenario, for example, describes behaviour the system should keep. Each statement of that kind is kept in a file that outlives the spec.

| What the spec contains | Where it is kept after the change is delivered |
| --- | --- |
| The scenarios in the behaviour part | In the codebase, as the files that drive the behaviour tests. These may be Gherkin feature files or scenarios in another test language. |
| The checks in the quality part | In the codebase, as checks that run on every change |
| New domain terms | The project's vocabulary or glossary document |
| Architectural decisions | The project's architecture documents |
| Contracts between components | The contract definitions and their tests |
| The reason for each part | Not settled |

### The stages

A change passes through six stages. A later stage can send the work back to an earlier one.

1. **Discover:** find out what is needed and why.
2. **Specify:** the person and the agent write the spec, and the person approves it.
3. **Implement:** an agent builds the change.
4. **Verify:** the scenarios and checks in the spec run against the result.
5. **Reconcile:** check that each statement that has to stay true has reached the file where it is kept.
6. **Archive:** the spec becomes a record and is no longer edited.

Reconciling should be a small step. The files in the table are changed during delivery, so at the end there is only a check that the agreed changes are in place. Nothing is copied out of the spec into new documents.

### A spec as a bundle of files

A spec does not have to be one document. It can be a main document and a set of other files that the main document refers to. For example, the main document can list its Gherkin scenarios by reference, with each scenario in a file of its own.

This removes the need to move scenarios when the spec is archived. A scenario file can be written in the place where it will be kept from the start. The main document refers to it there. When the change is delivered, the main document is archived and the scenario file stays where it is and keeps running.

A later change that alters existing behaviour refers to the existing scenario files and edits them. The person approves those edits as part of approving that change's spec.

## Things to try

These are ideas to test in small experiments before any of them becomes part of the workflow. Each experiment needs a way to tell whether the idea helped.

- **Tests as data:** this is one way to make the scenarios in a spec run. The scenarios are held as tables or plain text, and a small fixed runner executes them against the system. The agent writes the code that connects the runner to the system. It does not write the expected results, so it cannot weaken them. The experiment should show whether a person can read and review scenarios in this form, and whether the agent can build against them. The knowledgebase page is `specifying-work/keep-the-tests-as-data-a-person-can-read-and-review.md`.
- **A spec as a bundle of files:** write the scenarios as separate files in the place where they will be kept, and have the spec's main document refer to them. The "Spec lifecycle" section describes this. The experiment should show whether a person can review a spec that is spread across files, and whether reconciling at the end is as small a step as expected.

## Ruled out

These options were considered and rejected.

- **Linting specs for vague language:** a check of 257 acceptance bullets in recent lightcycle specs found one vague word.
- **Adopting GEARS:** the only source is one vendor's post, with no measurement and no tooling. Its "where, while, when, the subject shall" sentence template can be borrowed on its own.
- **Starting with tests at the use-case level:** not every system has use cases, and the unit of behaviour differs by project.
- **One spec per source file:** a source file is not a unit of behaviour, so a spec organised this way does not match what a reviewer needs to judge.

## Open questions

1. Does the plan need a human gate, or is an agent review enough, with the human reviewer seeing the plan beside the code?
2. What is the first experiment? Proposed: take five or six merged specs and sort their content by hand into behaviour, quality, architecture and mechanics. Then judge whether each change could have been approved from the first three alone.
3. How is improvement measured? Candidates: the number of words read to approve a change, against today's median of about 2,400; the mutation score of the resulting tests; and whether the spec alone tells a later reader what changed.
4. The architecture column has four cells marked "not settled". A dependency rule can be kept as a check. A decision about where data lives may only be reviewable.
5. What form do the tests take? Tests kept as data are listed under "Things to try". Other candidates are a small test language where every scenario must state its expected result, and approved-output files.
6. Where is the reason for a behaviour recorded after the merge, so that it sits beside the tests it explains?
7. How does the spec shrink for a small change? Lightcycle's two existing paths appear to differ by size and risk, which is separate from the three parts.
8. What did the earlier quality-attribute model design (LC-1250) settle, and does this build on it?

## Background reading

In the knowledgebase (`kenmclennan/knowledgebase`):

- `specifying-work/state-a-quality-requirement-as-a-scenario-with-a-measurable-response.md`
- `verifying-behaviour/a-fitness-function-is-an-automated-check-of-an-architectural-aim.md`
- `specifying-work/keep-the-tests-as-data-a-person-can-read-and-review.md`
- `verifying-behaviour/approve-an-output-once-and-keep-it-in-a-file.md`
- `specifying-work/write-the-spec-as-a-test-that-runs.md`
- `specifying-work/ears-write-each-requirement-in-one-of-five-sentence-patterns.md`
- `understanding-and-skill/offloading-versus-surrender-in-ai-work.md`
