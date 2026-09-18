---
engine: true
accepts:
  pr: required
---

# Poll-CI

This stage is owned by the engine, not an agent - no worker ever claims it. Every tick, the engine reads the current head SHA (via git, not the GitHub API) and the check-runs for it. If CI is still pending, nothing happens this tick. Once it concludes, the engine completes this step itself: `succeeded` or `failed`, either way routing to `watch-ci` with a pointer note (the run, and the failing check's name, when it failed). `watch-ci` does the rest - comment handling always, plus log-fetching and judgement on failure.

No `ci-wait:` key: the bounded-wait/rate-limit-bucket machinery `watch-ci.md` needed before this split has no engine-side equivalent - the engine simply checks again next tick, for as long as the PR stays open, exactly like every other per-tick PR fact.
