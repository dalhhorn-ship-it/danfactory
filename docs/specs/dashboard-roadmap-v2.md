# PRD: Dashboard roadmap v2 (global sequence, Next up, sequence rationale)

> Status: approved · 2026-11-07 · by user in chat · Owner: product-manager · Backlog: Unplanned → "Dashboard roadmap v2"

## Problem
The Roadmap tab numbers open items per lane, so "what do we build next?" has two answers (value 1 and foundation 1). It shows every milestone as full columns even when finished, so the page gets longer and noisier as work completes. It gives no reason for the order, and cards don't show whether the PRD gate has been passed. The downstream project lpdan (/home/user/dalhhorn-ship-it/lpdan) hit all of this in real use and fixed it locally (commit 4ed7806 there). Those fixes should flow back into the template so every new project gets them.

## Goal and success measure
Traceability: the project is still in phase `brainstorm` and docs/GOAL.md is not agreed, so this is template tooling work. It traces to the template's own purpose (README.md, docs/policies/*): a factory where plan, PRD gate and delivery are visible at a glance (docs/policies/prd-approval.md covers tooling changes; async-delivery keeps stakeholders informed without chat). Proposed GOAL-equivalent: a user opening the Roadmap tab can name the next open item, and why it is next, within 5 seconds.
Success: the template dashboard reproduces lpdan's behaviour (items 1-5 below) and the sequence-refresh rule is in the operating docs.

## Users and user stories
- As the product owner, I want one global "next up" order so that I know what is being built next.
- As the product owner, I want a one-line reason for the order so that I can challenge it.
- As a reader, I want finished milestones collapsed so that the page shows what is still ahead.
- As the product owner, I want to see which items have an approved PRD so that I know what is blocked on my approval.

## Scope
1. `> Sequence: <rationale>` line directly under a milestone heading in docs/BACKLOG.md, written by product-manager; parsed and shown as that milestone column's subtitle.
2. One global sequence number across both lanes and all milestones (1 = next up overall); done items show a check mark.
3. Milestones with all items done render as a single line "Done: <name> (n/n)" instead of columns.
4. "Next up" strip above the roadmap: top 3 open items in global order, showing short title (cut before " AC:"), size and lane.
5. Within a cell, open cards first, done cards after (stable order otherwise).
6. Process rule: after every completed slice, product-manager re-proposes the build sequence (reorders open items, updates `> Sequence:`) before the dashboard refresh; dashboard artifact is republished to the same URL. Documented in docs/OPERATING-MODEL.md (and the template it is generated from), docs/operating-model/AGENT-ROUTING.md (Plan row), the product-manager agent notes, and .claude/skills/dashboard/SKILL.md.
7. OPTIONAL (recommend include, small): when a backlog item links to docs/specs/<slug>.md, the card shows a PRD badge, "draft" or "approved", read from that file's `Status:` line. Missing file or no link: no badge.
   Note: item 7 is cut first if the slice grows.

## Non-goals
- No JavaScript; static HTML as today.
- No new data files beyond docs/BACKLOG.md, docs/TECH-DEBT.md (and the linked PRDs, read-only).
- No drag-and-drop or in-page editing; reordering happens by editing BACKLOG.md.
- No automatic sequencing algorithm; order is the product-manager's judgement.
- No change to lane assignment (tags) or to the tech-debt column behaviour.
- No change to other dashboard tabs.

## Acceptance criteria
1. Given a milestone in BACKLOG.md with a `> Sequence: X` line, when the dashboard renders, then that column shows X as a subtitle; given no such line, then no subtitle and no error.
2. Given open items in both lanes across several milestones, when rendered, then open items carry numbers 1..N unique across the whole roadmap, ordered by milestone then file order, and done items carry no number.
3. Given tech-debt items in the final column, when rendered, then they continue the same global numbering after all backlog items.
4. Given a milestone whose items are all done (dropped items ignored), when rendered, then it appears as one line "Done: <name> (n/n)" and has no column; given a milestone with at least one open item, then it renders as full columns.
5. Given every milestone is done and no debt is open, when rendered, then the page shows the Done lines and an empty-state message, with no error.
6. Given at least 3 open items, when rendered, then the Next up strip lists exactly the three lowest-numbered open items with size and lane; given fewer, it lists those that exist; given none, the strip is omitted.
7. Given an item title containing " AC:", when shown in the Next up strip, then the title is cut before " AC:"; the full title remains on the roadmap card.
8. Given a cell with done and open cards interleaved in the file, when rendered, then open cards appear first and done cards after, each group in file order.
9. (Optional) Given an item linking docs/specs/<slug>.md whose Status line starts with "draft" or "approved", when rendered, then the card shows that badge; given a missing file or no link, then no badge and no error.
10. Given the repo's test suite, when `python3 scripts/metrics.py test` runs, then it passes, with new tests covering ACs 1-8 (and 9 if included).
11. Given docs/OPERATING-MODEL.md, AGENT-ROUTING.md and the dashboard SKILL.md, when read, then each states the "re-propose sequence after every slice, then refresh the dashboard to the same URL" rule.
12. Output stays valid, escaped HTML (rationale and titles are escaped) and the page works without JavaScript.

## UX / behaviour notes
- Numbering is by position in the proposed order, so reordering BACKLOG.md items is the only control the product-manager needs.
- Rationale subtitles should be one sentence; long text wraps rather than widening the column.
- A blocked item keeps its number and its "blocked" badge.
- Empty/error states: no milestones, no open items and unreadable PRD links all degrade quietly.

## Risks and assumptions
- Riskiest: the rule in item 6 is only followed if it is in the agent routing and skill text, so it needs to be where agents read it (covered by AC 11). Test by dry-running one slice.
- Parsing `> Sequence:` must not break existing BACKLOG.md files without it (AC 1).
- Global numbering mixes lanes, so foundation items can look as important as value items; the rationale line is the mitigation.
- Item 7 couples the dashboard to the PRD file format (Status line); acceptable since the template owns that format.
- Assumption: lpdan's design is right for the template; it was proven on one project only.

## Effort and sequencing
- Size: M (one render/data change plus tests and doc edits). Without optional item 7: S-M.
- Swimlane: technical foundation (template tooling).
- No dependencies. Suggested slices: (a) global numbering + open-first + tests; (b) Sequence line + Done collapse + Next up strip; (c) process rule docs; (d) optional PRD badge.
- Reference implementation: /home/user/dalhhorn-ship-it/lpdan/scripts/dashboard.py roadmap()/render_roadmap() (read-only reference; adapt rather than copy blindly).

## Open questions
Not answered at approval; built with the PRD's recommended defaults: badge included, Next up = 3, tech debt numbered globally, dropped items ignored for the Done collapse, re-sequence rule on by default.

1. Include the optional PRD status badge (item 7) in this slice, or defer?
2. Next up strip size: keep 3, as lpdan does?
3. Should tech-debt cards be numbered in the global sequence (AC 3), or stay unnumbered as a separate "to schedule" pool?
4. Should the Done collapse also apply when a milestone is all done except dropped items (AC 4 assumes yes)?
5. Is it fine to log the "re-propose after every slice" rule in OPERATING-MODEL.md for new projects by default, or should it be opt-in?
