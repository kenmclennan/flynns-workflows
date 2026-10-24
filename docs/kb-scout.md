# Kb-scout

Watches trusted feeds for material worth adding to the knowledgebase (`kenmclennan/knowledgebase`), follows links one hop out, scores what it finds, and raises one inbox item listing the candidates above a threshold. It mirrors nothing and writes nothing to the knowledgebase.

- **Guard** (`scripts/feeds-moved.py`, suggested `0 9 * * 2,5`) fetches every enabled feed and passes when any has entries newer than its high-water mark, or candidates or undecided survivors are waiting. Otherwise nothing is filed and nothing is spent.
- **harvest** is a script stage. New entries become tier 1 candidates; their outbound links become tier 2 candidates with an inbound-link count. Only links in the article body are followed (martinfowler.com `div.paperBody` and `div.appendix`, Substack `div.body.markup`), minus static assets, Amazon and the author sponsorship page; a page with no recognisable body falls back to every link outside `nav`, `header` and `footer`. Sources already in `references/` and sources already accepted or rejected are dropped.
- **evaluate** is the only agent stage. It scores up to `batch-cap` candidates for relevance and novelty against the knowledgebase.
- **rank** is a script stage. It applies `threshold`. `none` closes the item unseen.
- **review-candidates** is the human gate. Accept, reject or defer each survivor; file a `kb-ingest` item per acceptance.
- **record-decisions** is a script stage that writes the verdicts and any new feeds.

## State

One SQLite file, `scout.db`, in the workflow's data directory, with `feeds`, `seen` and `decisions` tables. `scripts/lib/scout_state.py` owns the schema and every read and write; no script contains SQL. A declined source is never kept in the knowledgebase repo.

`python3 scripts/scout-cli.py` (run with `LC_WORKFLOW_DATA_DIR` set) answers questions at the gate: `feeds`, `queue`, `why <url>`, `add-feed <url>`, `disable-feed <url>`, `enable-feed <url>`.

## Operator setup

Config under `workflow-flynns-workflows-kb-scout:`. `threshold`, `batch-cap` and `kb-repo` are required and the install fails without them. `checkout-path` and `qmd-command` are optional and let `evaluate` query the `qmd` index; without them it reads `index.md` files. `fetch-command` is a recorded-response fake for tests.

The install seeds `https://martinfowler.com/feed.atom` and `https://tidyfirst.substack.com/feed`. The feed parser and link extractor are Python's standard `xml.etree.ElementTree` and `html.parser`, so there is nothing to install.

The item must carry the knowledgebase as its `repo` so `harvest` and `evaluate` get a worktree of it. If the engine does not attach that to a guard-filed item, `harvest` parks with a message saying it found no `references/` directory.
