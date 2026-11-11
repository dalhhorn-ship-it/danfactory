# PRD: Dashboard in the IBM Carbon design language

> Status: approved · 2026-11-11 · by user in chat · Owner: product-manager · Backlog: Unplanned → DASH-3

## Problem
The dashboard (`scripts/dashboard.py` plus the tabs in `scripts/obs/*.py`) uses a home-grown inline style. The owner asked on 2026-11-11 to "design the dashboard in IBM Carbon". They already publish "Tech Operating Model 1.5 · Key (Carbon light)", so they know and prefer that look. The page has hard constraints that rule out simply installing Carbon: one offline static HTML file, no JS, CSS-only radio tabs, no network requests (no CDN fonts or CSS), light and dark, phone width. It is published as a private claude.ai artifact, and a copy is shipped on the landing page repo lpdan (`public/dashboard/index.html`). "Carbon" here therefore means reimplementing Carbon's visual language with inline CSS, not using Carbon's packages.

## Goal and success measure
Traceability: docs/GOAL.md is still the empty template; same stand-in as docs/specs/eval-visualizations.md (a factory whose state is visible without chat). Success: the dashboard looks like a Carbon product to someone who knows Carbon (same colours, type scale, spacing, tile/table/tag/tab/notification forms, square corners, no shadows), in light and dark, with no loss of function, readability or offline behaviour, and within the size budget.

## Users and user stories
- As the factory owner, I want the dashboard in the Carbon look I already use so that my artifacts feel like one family.
- As the owner reading on a phone, I want the layout to stay usable at narrow width so that the restyle does not cost me mobile reading.
- As the owner in dark mode, I want a proper dark theme (Carbon g100) so that the page matches my system setting.
- As a viewer of the public lpdan copy, I want it to stay a single offline file so that nothing external loads.

## Scope
One slice, restyle only, no change to data or content:
1. **Tokens.** Carbon v11 colour tokens as CSS custom properties: light theme (White or g10, see open question 2) and dark theme g100; background, layer-01/02, border-subtle/strong, text-primary/secondary/helper, link, focus, support colours (error, warning, success, info) and their notification backgrounds. Switching via `prefers-color-scheme` and `data-theme`, as today.
2. **Type.** IBM Plex Sans and Plex Mono names first in the font stacks, then a local system fallback; Carbon productive type scale (body-compact, heading-compact, heading, expressive-heading steps, code) in rem.
3. **Spacing and grid.** Carbon spacing scale (2, 4, 8, 12, 16, 24, 32, 48 px) and 2x grid feel (16px gutters, 32px at wide screens), one breakpoint set matching Carbon (sm 320, md 672, lg 1056) for phone, tablet, desktop.
4. **Components.** Tiles (cards), data tables (compact rows, header row, zebra off, hover off since no JS needed for it), tags (read-only, colour plus text), tabs in line style (CSS-only radio, keyboard focus visible), inline notifications for alerts and data warnings (icon plus text, not colour alone), progress and status indicators, links with Carbon underline and focus ring.
5. **Charts.** Existing inline SVG charts recoloured to the Carbon data-visualisation palette: categorical palette for series, sequential single-hue ramp for the heatmap, with numbers kept in cells; grid lines and axis text use Carbon tokens so charts follow the theme.
6. **Font delivery.** Per open question 1.
7. **Where it ships.** Dashboard output of `scripts/dashboard.py`; lpdan copy per open question 3.
8. **Legal hygiene.** Carbon is Apache-2.0, so reimplementing tokens is fine; keep a short attribution comment (Carbon Design System, Apache-2.0; IBM Plex, SIL OFL 1.1 if embedded) in the HTML source and docs. No IBM logo, no "IBM" in the page title or header; the page is not presented as an IBM product.

## Non-goals
- Carbon React, web components, `@carbon/styles` or any package, CDN or build step (cannot be loaded offline).
- Any JavaScript interaction (dropdowns, modals, sortable tables, theme toggle button). Tabs stay CSS-only.
- Changing content, data, tab structure, information hierarchy or the data.json contract.
- Pixel-identical Carbon: no motion, no components the page does not use.
- IBM logo, IBM wordmark, or implying IBM endorsement.
- Restyling the Tech Operating Model artifact or any other artifact.

## Acceptance criteria
1. Given the token parity list (background, layer-01, layer-02, border-subtle-01, border-strong-01, text-primary, text-secondary, text-helper, text-on-color, link-primary, focus, support-error, support-success, support-warning, support-info, plus the notification backgrounds), when the built CSS is inspected, then each exists as a custom property with the exact Carbon v11 hex for light and for g100, verified by a test that compares against a checked-in token table.
2. Given a browser with a light preference, when the page loads, then it renders the light theme; given dark, g100; given `data-theme="light"` or `"dark"` on the root, then that overrides the system setting.
3. Given every text and meaningful graphical foreground/background pair in both themes (body, secondary, helper, links, tags, notifications, table headers, chart labels, heatmap cells with numbers), when contrast is computed, then text is at least 4.5:1 (3:1 for large text) and non-text indicators at least 3:1, tested in a script over the token pairs.
4. Given the built HTML, when scanned, then it has no `<script>`, no `http(s)://` resource reference (`src`, `href` to external, `@import`, `url(` to remote), no `<link rel=stylesheet>` and no `@font-face` pointing at a remote URL; the page loads with the network disabled in Playwright with zero requests.
5. Given the page, when keyboard-tabbing, then the radio tabs and links show Carbon's focus ring and every tab panel is reachable; tags, status and alerts carry text or an icon, never colour alone.
6. Given the typography, when rendered, then headings, body and table text use the Carbon scale steps defined in the PRD, with Plex first in the stack and a monospace Plex Mono stack for code and numbers where used today.
7. Given tiles, tables, tags, tabs and notifications, when rendered, then corners are square (radius 0, except tag pills which follow Carbon's rounded tag), and there are no box shadows or gradients.
8. Given each chart (all inline SVG including the evals views and the heatmap), when rendered in both themes, then series use the Carbon categorical palette, the heatmap uses a sequential ramp with the number in every cell, and legends are present.
9. Given the HTML size budget (per open question 1: fallback default, at most 20% above today's size; if Plex is embedded, at most 1 MB total), when the dashboard builds, then a test fails above the budget.
10. Given Playwright screenshots at 390x844 (phone) and 1440x900 (desktop), in light and dark, for every tab, when taken, then they are attached to the PR for owner review, show no horizontal scroll at phone width, no clipped or overlapping text, and the owner confirms the look in chat before the item is ticked. (The visual diff against the previous version is informational; there is no pixel-exact gate because the look is meant to change.)
11. Given the existing test suite, when `python3 scripts/metrics.py test` runs, then all existing dashboard output tests still pass without being weakened or skipped, and `bash scripts/check.sh` passes; where a test asserted old class names or colours it is updated in the same change and listed in the PR.
12. Given empty states, warnings and malformed inputs that render today, when the dashboard builds, then they still render, now as Carbon inline notifications or empty-state tiles.
13. Given the lpdan copy (per open question 3), when it is regenerated from the same build, then it is byte-equivalent in structure to the artifact version and passes the same no-network and no-JS checks.

## UX / behaviour notes
- Header: plain text title, no logo; a compact top bar in the Carbon UI-shell style (dark bar in both themes, as Carbon does) is allowed but not required.
- Tabs sit in a line-style bar; on phone the bar scrolls horizontally or wraps, whichever keeps all tabs reachable without JS.
- Tables: compact density, left-aligned text, right-aligned numbers in Plex Mono, and horizontal scroll inside the tile at phone width rather than page overflow.
- Status colours follow Carbon support tokens; red/green are always paired with a word or icon.
- Printing is out of scope.
- Dark theme is g100 (not pure black), matching Carbon.

## Risks and assumptions
- Riskiest: appearance without Plex looks off. Carbon relies on Plex for its character; a system fallback may look generic and shift widths, so the owner may think the restyle "isn't Carbon". Test cheaply first: render one tab with the fallback stack and one with embedded Plex Sans 400/600 and Mono 400 subset, and let the owner pick from two screenshots before the full restyle.
- Size: embedding Plex as base64 woff2 adds roughly 100 to 200 KB per weight; three to four weights could add 0.5 MB to a file that is also re-shipped to lpdan and to the artifact. Subsetting to Latin cuts this a lot.
- Contrast: some Carbon palette colours (light categorical hues, tag backgrounds) fail AA as text; use Carbon's tag text-on-colour pairs and add text labels rather than altering the palette.
- Existing tests may assert old markup or colours; expect some churn in test fixtures.
- Chart recolouring touches every obs tab and the EVAL views still in flight; sequence DASH-3 after in-flight EVAL-4/EVAL-5 chart work lands, or the charts get restyled twice.
- Licensing and trademark: low. Apache-2.0 and OFL allow this; keep attribution, avoid the IBM logo and name.
- Assumption: the CSS-only radio tabs can reach Carbon's line-tab look and focus behaviour without JS.

## Effort and sequencing
- M overall. Tokens, type, spacing and components in one inline stylesheet (S to M); chart recolouring across obs tabs (S); tests for token parity, contrast, no-network and size, plus Playwright screenshots (S to M). Embedding fonts adds S.
- Swimlane: user value (look), no new dependency. Proposed slices if it grows: (1) tokens, type, tiles, tabs, tables, tags, notifications; (2) charts and heatmap palette; (3) lpdan copy.
- Cut for now: UI-shell side navigation, theme toggle, other Carbon themes (g90), motion.
- Architect decides how the stylesheet is organised in `scripts/dashboard.py` and how the token table is kept for the parity test.

## Open questions
1. Fonts: embed IBM Plex (Sans 400/600 and Mono 400, Latin subset, base64 woff2, OFL) or use the local fallback stack (Plex names first, then system fonts)? Recommend fallback first, with a one-tab A/B screenshot of the embedded option so you can decide; embed only if the fallback does not read as Carbon to you, within a 1 MB total budget.
2. Light theme: Carbon White (white page, g10 tiles) or g10 (light grey page, white tiles)? Recommend White, because your Tech Operating Model artifact is "Carbon light" and White is the standard Carbon default; tell me if that artifact uses g10.
3. Does the public lpdan copy (`public/dashboard/index.html`) switch to Carbon as well? Recommend yes, same build, no fork, once the artifact version is accepted; the lpdan sync stays blocked on push access to `dalhhorn-ship-it/lpdan` as for EVAL-3.
4. Sequencing: restyle now or after EVAL-4/EVAL-5 charts land? Recommend after, to avoid restyling the new charts twice; if you want it first, the new charts adopt the Carbon palette from the start.

## Decisions (user, 2026-11-11)
Approved with the recommended answers: fonts = local fallback stack first plus a one-tab A/B screenshot of embedded Plex for the user to decide; light theme = Carbon White; lpdan dashboard copy switches too (same build, via the lpdan handover file); sequencing question moot (EVAL-4/5 already landed).
- Look accepted by the user in chat 2026-11-11 (AC10).
