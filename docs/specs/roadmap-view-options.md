# PRD: Roadmap view options (6-month timeline, proposed Gantt, release view)

> Status: approved · 2026-11-11 · by user in chat · 2026-11-11 · Owner: product-manager · Backlog: Unplanned → DASH-4

## Problem
The Roadmap tab has one view: lanes × milestones with a global build sequence (docs/specs/dashboard-roadmap-v2.md). It answers "what is next and why" but not "when" or "in which release". The product owner asked on 2026-11-11 for "more fancy roadmap views as an option, e.g. 6 month view, Gantt chart proposed, release version view". Today the data is thin: BACKLOG.md has sizes, order and IDs; milestone `(target: YYYY-MM-DD)` dates are all empty; items carry no dates; there are no git tags. Any new view must be honest about that.

## Goal and success measure
Traceability: docs/GOAL.md is not agreed yet (phase `brainstorm`), so this is template tooling, like DASH-1/DASH-2: plan and delivery visible at a glance for stakeholders. Proposed GOAL-equivalent: a reader can switch the Roadmap tab to a time view or a release view in one click, and sees what is estimated versus what is fact.
Success: three opt-in views render from existing repo data, with clear empty states; the current view stays the default and is unchanged.

## Relation to the earlier "Now/Then/Later" decision
On 2026-11-07 the user declined a Now/Then/Later roadmap (docs/specs/dashboard-delivery-backflow.md, question 3: "no", because it competed with the global numbered sequence). This PRD is different: these are opt-in alternative views of the same data, selected by the user; the existing Roadmap (lanes × milestones, global sequence, Next up) remains the default and is not replaced, re-ranked or duplicated as a competing backlog.

## Users and user stories
- As the product owner, I want a 6-month timeline so that I see which milestones and items land in which month.
- As the product owner, I want a proposed Gantt so that I can sanity-check how long the open sequence might take, knowing it is an estimate.
- As a stakeholder, I want a release view so that I see what shipped in each version and what is planned for the next.
- As the product owner, I want to pick the view (and a default) without JavaScript so that the page still works offline and on a phone.

## Scope
1. View switcher inside the Roadmap tab: CSS-only radio sub-tabs (same technique as the existing tabs) with options "Sequence" (current), "6-month", "Gantt (proposed)", "Releases". Default is "Sequence", overridable by a `dashboard.roadmap_view` key in factory.json (values: sequence, months, gantt, releases).
2. **6-month timeline**: months as columns (window anchored per open question 4); milestones with a `(target: YYYY-MM-DD)` are placed in their month; done items are placed by their actual done date (git history); open items without a date are listed in an "Unscheduled" strip, never guessed into a month. Today marker.
3. **Proposed Gantt**: one bar per item in BACKLOG.md sequence order (done items first at actual dates, then open items). Open-item bars are estimated: duration from size via a configurable mapping (`dashboard.size_days`, default per open question 1), scheduled sequentially with a WIP assumption (`dashboard.wip`, default 1). Done items use actual start (first commit referencing the ID) and done dates, derived with the same history logic as scripts/obs/evals_flow.py `history()` and trace.py `ref_keys`. Today line. Dependencies drawn only if declared (an optional `(after: ABC-n)` marker); none inferred. Estimated bars are visibly different (hatched or dashed, label "estimated") and the panel carries a "Proposed, not a commitment" caption plus the assumptions in use (mapping, WIP, working days only).
4. **Release view**: items grouped by release. A release is a git tag `vX.Y.Z` (date from the tag) and/or an optional `(release: vX.Y)` marker on a backlog item or milestone heading for planned releases. Each group shows status (shipped / planned), item count, and a changelog-style list (ID, short title). Items with no release go to "Unassigned". Done items in a tagged release are inferred only by an explicit marker or by the done date falling between tags (open question 3).
5. Inline SVG for timeline and Gantt; horizontal scroll inside the panel on narrow screens; labels remain readable text. No JS, no network, no external fonts.
6. Styling uses the shared design tokens, so it follows the Carbon restyle (see Effort and sequencing).
7. Docs: backlog-format notes (new optional markers `(release: …)`, `(after: …)`, size mapping and view keys in factory.json) in the dashboard SKILL.md and docs where BACKLOG conventions live.

## Non-goals
- No drag-and-drop or in-page editing; plans change by editing BACKLOG.md.
- No sync with external PM tools (Jira, Linear, GitHub Projects).
- No resource or capacity planning per person; WIP is one team-level number.
- No automatic dependency inference.
- No change to the default Sequence view, lane assignment, global numbering or the other tabs.
- No commitments: estimated dates are never written back to BACKLOG.md.
- No Now/Then/Later view (declined 2026-11-07).

## Acceptance criteria
1. Given the Roadmap tab, when rendered with no factory.json setting, then "Sequence" is selected and its markup and numbers are identical to today's; given `dashboard.roadmap_view` is `gantt`, then Gantt is selected on load; given an unknown value, then Sequence is selected and no error is raised.
2. Given the page is opened with JavaScript disabled, when the user clicks a sub-tab label, then the matching view shows and the others hide (CSS only); the sub-tabs are keyboard-focusable and the selected one is visibly marked.
3. Given a milestone with `(target: 2026-12-15)` and the window covers December, when the 6-month view renders, then the milestone appears in the December column; given no milestone has a target, then the view shows an empty-state message ("No dates yet: add (target: YYYY-MM-DD) to a milestone") plus any done items at their actual dates, and no error.
4. Given open items without a date, when the 6-month view renders, then they are listed under "Unscheduled" and appear in no month column.
5. Given today is 2026-11-11, when the 6-month view renders, then a today marker sits at that date within the window.
6. Given open items with sizes S, M, L and the default mapping, when the Gantt renders, then bars appear in BACKLOG.md order, each with width proportional to its estimated working days, laid out with at most `wip` bars in parallel, starting from today.
7. Given `dashboard.size_days` overrides in factory.json, when the Gantt renders, then durations use the override; given an item with no size, then it uses the M value and is marked "size missing".
8. Given any estimated bar, when rendered, then it is visually distinct from actual bars, the panel shows the words "proposed" and "estimated" and lists the mapping and WIP in use.
9. Given done items with history, when the Gantt renders, then their bars span first-reference date to done date from git history; given no git history (fresh repo or shallow clone), then done items are shown as a milestone dot at "unknown date" in a labelled list and no error occurs.
10. Given an item with `(after: ABC-n)`, when the Gantt renders, then a dependency connector is drawn and the item does not start before its predecessor ends; given no such markers, then no connectors are drawn.
11. Given git tags `v0.1.0` and `v0.2.0` and items marked `(release: v0.2)`, when the Releases view renders, then it lists one group per release (newest first), shows shipped with the tag date or planned, and a changelog list of IDs and short titles per group.
12. Given no git tags and no release markers, when the Releases view renders, then it shows an empty state explaining both ways to define a release, and still lists done items under "Unassigned"; no error.
13. Given a repo where git is unavailable or tags cannot be read, when the dashboard renders, then all views degrade to their empty states and the Sequence view is unaffected.
14. Given a 375px-wide screen, when the 6-month or Gantt view renders, then the chart scrolls horizontally inside its own container and the page itself does not scroll sideways.
15. Given titles, release names and IDs from BACKLOG.md and tags, when rendered into HTML/SVG, then all text is escaped; output has no script, no external requests.
16. Given the repo's test suite, when `python3 scripts/metrics.py test` runs, then it passes, with new tests covering ACs 1, 3, 4, 6, 7, 9, 11, 12 and 13.
17. Given the Carbon restyle is merged, when the new views render, then they use its tokens in light and dark mode (no hard-coded colours that clash).

## UX / behaviour notes
- Sub-tabs sit at the top of the Roadmap panel, labelled "Sequence | 6-month | Gantt (proposed) | Releases". The Next up strip stays only on the Sequence view.
- Empty states are explicit and say what to add to BACKLOG.md; sparse data is the expected case today.
- Estimated vs actual: solid fill is fact (from git or markers), hatched/outlined is estimate. Colour is never the only cue (also a text label).
- Working days only: bars skip weekends in the estimate; the axis is calendar dates.
- The Gantt window is as long as the estimated plan needs, with a cap (e.g. 12 months) and a "continues beyond" marker, so one huge backlog does not make an unreadable chart.
- Done items collapse to the same "Done" convention as today where there are many (details to the architect).

## Risks and assumptions
- Riskiest: fake precision. Size-to-days mapping and WIP are guesses, and a dated bar reads like a promise. Mitigation: labelled "proposed/estimated", assumptions shown on the panel, hatched style, no write-back, and day granularity shown as weeks. Cheap test: show the Gantt to the user with this repo's real backlog before the other views are polished.
- Done-item dates depend on commits referencing IDs; items done without a referencing commit get a degenerate (one-day) bar. Mitigation: AC 9 labelling.
- Release view depends on the team starting to tag releases; until then it is mostly empty. Mitigation: planned releases via marker, empty state with instructions.
- Adding markers to BACKLOG.md items makes titles noisier and must not break existing parsing (parsers in dashboard.py and obs/evals_flow.py must ignore unknown parentheses). Cover with tests.
- Collision with the Carbon restyle (DASH-3, draft) in the same render code and CSS. Mitigation: sequencing below.
- Assumption: the user wants these views as occasional extras, not as the main planning surface.

## Effort and sequencing
- Size: L overall. Suggested slices, each shippable alone: (a) sub-tab switcher plus factory.json default, Sequence unchanged (S); (b) Releases view (S-M, least estimation risk, most useful once tags exist); (c) 6-month timeline (M); (d) proposed Gantt with mapping, WIP, history and optional `after` (M-L). Risk-first alternative: do (d) first for the fake-precision test; recommended order is (a), (d), (c), (b) only if the user wants the risk test first, otherwise (a), (b), (c), (d).
- Dependencies: recommend building after DASH-3 (Carbon restyle) so the sub-tabs, SVG colours and tables use its tokens once instead of being restyled twice; if DASH-3 is delayed, build slice (a) on current CSS variables and keep colours in variables.
- Swimlane: value (stakeholder visibility), tag #feature.
- Reuse: history derivation from scripts/obs/evals_flow.py `history()` and trace.py `ref_keys`; tab radio technique in scripts/dashboard.py (tab markup near `TABS`, roadmap() at line 294, render_roadmap() at line 421).

## Open questions
Recommended defaults are marked; unanswered questions are built with them.

1. Size to days mapping: recommend S = 1, M = 3, L = 8 working days, configurable under `dashboard.size_days` in factory.json. Alternatives: S 2 / M 5 / L 10 if your slices tend to run longer.
2. Capacity and parallelism: recommend WIP = 1 (one item at a time, sequential bars), configurable under `dashboard.wip`; items in different lanes do not run in parallel unless WIP is raised. OK?
3. Release marker syntax: recommend an optional `(release: v0.2)` on an item or milestone heading, plus git tags `vX.Y.Z` for shipped releases; an item without a marker belongs to the first tag created after its done date. Or do you prefer tags only?
4. 6-month window anchor: recommend today minus 1 month through today plus 5 months (rolling), so recent history and the next half-year are visible. Alternative: current month plus 5, or calendar half-years.
5. Default view: recommend "Sequence" stays the default; the other views are opt-in via the sub-tabs or `dashboard.roadmap_view`. Should any project default to a different view?

## Decisions (user, 2026-11-11)
Approved with the recommended answers: S=1, M=3, L=8 working days (`dashboard.size_days`); WIP=1 (`dashboard.wip`); optional `(release: vX.Y)` marker plus git tags vX.Y.Z; rolling window today-1 month to +5 months; Sequence stays the default view. Build after DASH-3 using its Carbon tokens.
