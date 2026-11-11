# PRD: Upstream from lpdan: two lost security protections and `docs_index.py --related`

> Status: approved · 2026-11-11 · by user in chat ("Ok plz do", in the lpdan session, after the scope below was proposed) · Owner: product-manager · Backlog: Unplanned / UPS-1

## Problem
The lpdan sync to template 1.2.0 (lpdan ADR 0006) found that three things were in lpdan but not in the template:
1. `scripts/adopt_scan.py` writes repo-derived text (package name, stack, findings, paths) into a Markdown report unsanitised. A crafted `package.json` name with a line break can inject lines into ADOPTION-REPORT.md. lpdan fixed this as its SEC-001.
2. `.claude/hooks/guard_bash_policy.py` misses a deploy command passed to a shell through a pipe: `echo "npx wrangler deploy" | sh`, `printf … | bash`, `cat <<EOF | bash`. lpdan fixed this as its SEC-003.
3. `scripts/docs_index.py --related DOC` lists a doc's neighbours in the knowledge graph, with summaries. It was built in lpdan (2edcba8) and is not upstream yet.

## Goal and success measure
Downstream projects don't lose these protections at their next sync, and lpdan's TD-011 drift goes away. A regression test for each of the three fails on the old code and passes on the new.

## Scope
- Copy the three files from lpdan. Each lpdan file is the template's 9cb70c5 version plus only the change above.
- Tests: `BashPolicy.test_blocks_text_piped_to_a_shell` in `.factory/tests/test_template.py`, `AdoptSecurity.test_scan_report_sanitises_repo_text`, and a `Related` class in `.factory/tests/test_docs_links.py`.
- The graph nodes in `docs/knowledge-graph.json` now carry a `summary` (needed by `--related`), so the graph is regenerated.

## Non-goals
- lpdan's index-first agent prompts and the token-economy policy line. lpdan's backlog says to measure them over 5 sessions before upstreaming.

## Acceptance criteria
1. Each new test fails against origin/main 00e573a and passes with the change (verified 2026-11-11).
2. `python3 scripts/metrics.py test` is green and `bash scripts/check.sh` is ok.
