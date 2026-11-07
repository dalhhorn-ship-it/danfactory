# Design: dashboard observability tabs

> Status: accepted · 2026-11-07 · Owner: software-architect · PRD: docs/specs/dashboard-observability-tabs.md · ADR: docs/decisions/0003-dashboard-observability-design.md

How the observability tabs get built. This note covers the shared layout for all three slices and spells out Slice 1 in detail. Stdlib Python only, no JS, no network.

## Module layout
`scripts/dashboard.py` only wires the tabs. New code goes in a package next to it (dashboard.py already puts `scripts/` on `sys.path`):

| File | Responsibility | Slice |
|---|---|---|
| `scripts/obs/__init__.py` | empty | 1 |
| `scripts/obs/sources.py` | read repo facts: GOAL outcome, PRD headers (`# PRD:` + `> Status:` line), ADR headers, wrangler config, git log with files, tags, test files | 1 (2 and 3 extend it) |
| `scripts/obs/model.py` | build the architecture model: generated layers, merge with curated, drift, read/write `docs/architecture.json` | 1 |
| `scripts/obs/svg.py` | lay out the layered SVG diagram deterministically | 1 |
| `scripts/obs/trace.py` | traceability chains and broken links | 1 |
| `scripts/obs/tab_architecture.py`, `tab_traceability.py` | each has `collect(root, base) -> dict`, `render(data) -> str` (panel HTML), `line(data) -> str` (one `--print` row) | 1 |
| `scripts/obs/tab_decisions.py`, `tab_gates.py`, `tab_docs.py` | same interface | 2 |
| `scripts/obs/tab_flow.py`, `tab_cost.py`, `tab_hotspots.py` | same interface | 3 |
| `scripts/archmodel.py` | thin CLI: `--write` refreshes docs/architecture.json, `--print` dumps it to stdout | 1 |

Rules:
- Every function takes `root`; nothing reads a module-level ROOT. That lets tests run against temporary repos.
- obs modules never import `dashboard` (no import cycles). `base` is the dict that `dashboard.collect()` already builds, so the tabs reuse the backlog and versions it parsed.
- Target under 250 lines per module.

Wiring in dashboard.py:
- Add a `TABS` list of `(key, label, module|None)`.
- `collect()` adds `d[key] = module.collect(ROOT, d)`.
- Generate the radio inputs, the nav labels and the `:checked`/`:focus-visible` CSS selectors from `TABS`. They are hand-written today.
- `summary()` appends `module.line(d[key])`.
- Overview and Roadmap markup stay unchanged.

## Model file: `docs/architecture.json` (ADR 0003, Q4)
```
{"schema": 1,
 "curated":   {"roots": [], "exclude": [], "elements": [...], "relations": [...]},   # hand-edited, preserved verbatim
 "generated": {"source": "scan|codegraph", "elements": [...], "relations": [...]}}  # rewritten by archmodel.py
```
- **Element:** `{"id", "type", "name", "layer", "path"?, "attrs"?}`. The id is `<prefix>:<key>`, for example `goal:outcome`, `req:<prd-slug>`, `adr:0003`, `app:src/billing`, `if:http`, `data:users`, `node:<worker>`, `svc:DB`.
- **ArchiMate subset.** Motivation: `goal`, `requirement`, `principle`. Application: `application-component`, `application-interface`, `data-object`. Technology: `node`, `technology-service`.
- **Relations:** `{"type", "source", "target"}`. Types: `realization`, `influence`, `serving`, `access`, `assignment`, `association`.
- **Determinism:** lists are sorted by id (relations by type, then source, then target). Written with `json.dump(sort_keys=True, indent=1)`, with no timestamps and no absolute paths. `--write` loads the file, replaces only `generated` and rewrites. Two runs with no repo change give identical bytes, and `curated` stays intact (AC5).
- **Curated keys:**
  - `roots`: source roots, which override the auto-detected ones.
  - `exclude`: path prefixes to skip.
  - `elements` and `relations`: the designed intent.
  - A curated element with the same `path` (application) or `id` as a generated element overrides its name and type.

## How each layer is derived
**Motivation**
- `goal:outcome` comes from the GOAL.md `## Outcome` section. It is skipped while that section is still a `_placeholder_`.
- Each PRD in `docs/specs/*.md` (title `# PRD:`, so design notes like this one are excluded) becomes a `requirement`. Attrs: status, approval date, AC count. It has a `realization` relation to the goal.
- Each ADR `docs/decisions/NNNN-*.md` (not 0000) becomes a `principle`. Attr: status. Where the ADR text mentions a component path, it gets an `influence` relation to that component.

**Application**
- **Source roots:** curated `roots`, or else the first that exists of `src/ app/ worker/ lib/ packages/ functions/`.
  - Paths owned by the template are excluded (`.claude/ .factory/ docs/ scripts/ templates/ dashboard/ metrics/ node_modules/`).
  - Exception: in the un-bootstrapped template (`project.name` empty), the root is `scripts/`, so the factory shows up as a demo (Q2, PM confirmed 2026-11-07).
- **Components:** each immediate child of a root, either a directory or a source file (`.py .ts .tsx .js .mjs`). For example `app:src/billing` or `app:scripts/dashboard.py`.
- **Component-to-component relations:** a regex scan for relative imports (`from "./x"`, `import x` / `from x import` when `x` is a sibling module) gives `serving` relations.
- **Interfaces:** the Worker entry (`main` in the wrangler config) gives `if:http`, linked by `serving` from the component that holds the entry file.
- **Data objects:** `CREATE TABLE` names in `migrations/*.sql`, accessed (`access`) by components whose source mentions the table name.
- **Codegraph:** when `integrations.codegraph` is true and the CLI is present, import edges come from codegraph instead of the regex scan (`source: "codegraph"`). This is spike S1. If it doesn't work out, keep the scan and log a TECH-DEBT item.

**Technology**
- Read `wrangler.jsonc`/`wrangler.json` (strip `//` and `/* */` comments outside strings and trailing commas, then `json.loads`), or `wrangler.toml` (with `tomllib`).
- The Worker `name` becomes a `node`.
- Each binding becomes a `technology-service` named `<BINDING> (<kind>)`. Kinds: `d1_databases`, `kv_namespaces`, `r2_buckets`, `queues.producers/consumers`, `durable_objects.bindings`, `services`, `ai`, `assets`.
- The node gets an `assignment` relation to the entry component, and each service is `serving` the components whose source mentions the binding name.
- Binding names only, never `vars` values or ids.

**Drift (AC4)**
- `designed_not_built`: curated application elements whose `path` doesn't exist.
- `built_not_designed`: generated components with no curated match. This list is only shown once there is at least one curated component; before that the tab says "no intent modelled yet", so drift doesn't flag every component.
- `unused_bindings`: bindings never mentioned in the source.
- `model_stale`: the committed `generated` section differs from the fresh one.

## SVG diagram (`obs/svg.py`)
- **Layout:** three bands stacked top to bottom: Motivation, Application, Technology. Each band has a left label and a grid of fixed-size boxes (150x44, 6 per row, 20px gaps). Band height grows with the number of rows.
- **Determinism:** the order within a band is (type order, id). Coordinates are integers.
- **Caps:** at most 24 elements per band; the rest become one "+N more" box.
- **Edges:** only edges between bands are drawn, as straight lines from the bottom centre of one box to the top centre of the other. Edges inside a band, and all relations, are listed in a capped table under the diagram.
- **Styling:** classes only (`am-mot`, `am-app`, `am-tech`, `drift`), colours from new CSS variables in both themes. Drift elements get a dashed border. Names are truncated to 20 characters, with the full name in `<title>`.
- **Accessibility:** `role="img"` plus an `aria-label` summary.
- **Phone:** `width:100%; min-width:960px` (640px made the labels illegible at 375px) inside `.scroll`, so it scrolls sideways on a phone without breaking the page.

## Traceability keys (ADR 0003)
| Link | Rule |
|---|---|
| goal → PRD | every PRD links to `goal:outcome` (a single goal for now) |
| PRD → item | the item mentions `docs/specs/<slug>.md`, or the item sits in the milestone named by the PRD's `Backlog:` field |
| item → commits | the item title starts with an ID `[A-Z][A-Z0-9]{1,5}-\d+` (e.g. `OBS-1`), and the commit message contains `Refs: OBS-1` (a trailer or anywhere). Fallback: `Refs: <prd-slug>` |
| commit → components | files changed in the commit (`git log --name-only`, one call, last 500 commits), mapped to components by path prefix |
| → tests | test files changed in the item's commits; otherwise test files whose path or stem contains the component's stem (`test_*.py`, `*_test.py`, `*.test.ts`, `*.spec.ts`, `tests/**`) |
| → version | the first tag at or after the commit, from one `git log --format=%H%x1f%D` walk (assumes linear history; documented) |

**Broken links (AC3):**
- PRD with no item
- item with no ID and no slug match
- done item with no commit
- item with commits but no tests
- approved PRD with no `approved · date`

## data.json additions (additive only)
- `architecture`: `{source, layers:{motivation:[el], application:[el], technology:[el]}, relations:[rel], drift:{designed_not_built, built_not_designed, unused_bindings, model_stale, intent_modelled}, counts:{...}}`. Each `el` adds `origin` (generated/curated/both) and `drift` (bool).
- `traceability`: `{chains:[{prd:{slug,title,status,approved}, items:[{id,title,state,commits:[{sha,subject}],components,tests,version,broken:[...]}], broken:[...]}], linked_commit_pct, unlinked_commits, broken_total}`
- Lists are capped (top 20 chains, 10 commits per item) with `*_total` counts.

## --print rows (one per tab)
- `| Architecture | 1 goal · 2 reqs · 3 principles, 7 components, 4 bindings; drift 2 |`
- `| Traceability | 2 PRDs → 4 items, 31% commits linked, 3 broken links |`

## Empty states (AC2)
- **Architecture:** "No architecture yet. Motivation fills from docs/GOAL.md, docs/specs/ (PRDs) and docs/decisions/ (ADRs); Application from source roots (src/, app/, worker/... or `curated.roots` in docs/architecture.json); Technology from wrangler.jsonc/toml." This is shown per band, so a partial model still renders.
- **Traceability:** "No PRDs yet: a chain appears when product-manager writes one in docs/specs/ and backlog items reference it. Link commits with `Refs: <ITEM-ID>`."

## Test strategy
- **Where:** `.factory/tests/test_observability.py`, stdlib `unittest`. It is picked up by `scripts/check.sh` (`unittest discover -s .factory/tests`). `metrics.py test` runs `commands.test`, which is empty in the template, so check.sh is the runner here.
- **Unit tests (pure functions on strings or dicts):**
  - wrangler jsonc/toml parsing
  - PRD and ADR header parsing
  - item-ID extraction
  - SVG output: deterministic, escaped, capped
  - empty-state rendering
- **Integration tests:** one `setUpClass` builds a temporary repo with `git init` and about 4 commits (GOAL, a PRD, BACKLOG with `OBS-1`, `src/a.ts`, `src/b.ts`, a test file, `wrangler.jsonc` with a D1 binding, a tag), runs `model.build` and `trace.build` against it once, and asserts:
  - the full chain
  - one broken link
  - drift in both directions
  - `--write` run twice gives identical bytes with curated preserved
- **Existing test:** `Dashboard.test_build_writes_artefacts` gets an assertion for `tab-architecture`/`tab-traceability` and the new data.json keys.
- **Budget:** the new tests add under 2 s, with no network and no codegraph (the codegraph path is mocked by passing `source` in). The inner loop is `python3 -m unittest .factory/tests/test_observability.py -q`.

## Risks and spikes
- **S1 (30 min, Slice 1):** find out which codegraph CLI output gives file-level imports. If none is usable, use the scan only and log TD.
- **S1 outcome (2026-11-07):** codegraph is not installed in this environment, so no file-level import output could be checked; the regex scan is used (`source: "scan"`), logged as TD-001.
- **S2 (30 min, end of Slice 1), PENDING (TD-002; no product repo available when Slice 1 was built):** run `archmodel.py --print` on one real product repo. If components are noisy, tune the root rules or rely on `curated.roots`/`exclude`.
- **S3 (Slice 3, before Cost):** attribution spike on `metrics/tokens.jsonl` (PRD risk 1).
- **Page size:** measure `index.html` after each slice (target under 400 KB).

## Slice 1 build order (one developer run; split after step 5 if needed)
1. **Conventions (docs only).**
   - docs/BACKLOG.md format line: optional item ID `ABC-n`. Give the M1 items IDs `OBS-0`…`OBS-3`.
   - One line in `.claude/agents/developer.md` and in the `ship` skill: commit messages carry `Refs: <ITEM-ID>`.
   - One line in `.claude/agents/product-manager.md`: new items get an ID.
2. **`scripts/obs/__init__.py` + `sources.py`** (GOAL, PRDs, ADRs, wrangler, git log with files, tags, test files). Unit tests.
3. **`model.py` + `scripts/archmodel.py`.** Generated layers, curated merge, drift, deterministic write. Integration tests (temp repo). Commit the first `docs/architecture.json` (template demo: `scripts/` components).
4. **`trace.py`.** Chains and broken links. Integration tests against the same temp repo.
5. **`svg.py` + `tab_architecture.py`.** Diagram, drift list, relations table, empty states, `line()`. Unit tests.
6. **`tab_traceability.py`.** Chain table with broken-link flags, capped; empty state; `line()`. Unit tests.
7. **`dashboard.py` wiring:**
   - `TABS`, generated tab inputs/labels/CSS, and a scrollable tab bar on narrow screens
   - ArchiMate CSS variables for light and dark
   - `collect()`/`summary()` additions, docstring
   - extend the Dashboard test
8. **Docs and checks:**
   - `.claude/skills/dashboard/SKILL.md` (new tabs)
   - `docs-sync` skill: run `scripts/archmodel.py --write`
   - `python3 scripts/docs_index.py`
   - tick OBS-1 in BACKLOG
   - `bash scripts/check.sh` green
   - check `index.html` size, and that light/dark and a 375px width render
