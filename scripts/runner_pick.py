"""Fixer runner issue picking: which approved issues are eligible, and the attempt log text.
Split from scripts/runner.py (SIZE-3); `runner` re-exports every name, so `runner.<name>` still works."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gate  # noqa: E402
import issues as L  # noqa: E402

from runner_core import Refuse, now


ITEM_RE = re.compile(r"[A-Z][A-Z0-9]*-\d+")


def in_progress_slugs(root):
    """Slugs of PRDs that are approved AND whose backlog item (the `Backlog:` field of the PRD header) is `[~]` in docs/BACKLOG.md."""
    try:
        with open(os.path.join(root, "docs", "BACKLOG.md"), encoding="utf-8") as fh:
            doing = set(re.findall(r"(?m)^\s*[-*]\s*\[~\]\s+([A-Z][A-Z0-9]*-\d+)\b", fh.read()))
        from obs import sources
        return {p["slug"] for p in sources.prds(root) if p["status"] == "approved" and doing & set(ITEM_RE.findall(p["backlog"]))}
    except Exception:  # noqa: BLE001 - nothing readable: nothing is in progress, so a scheduled run does nothing
        return set()


def approved_for(root, scheduled=False):
    ok = gate.approved_slugs(root)
    return ok & in_progress_slugs(root) if scheduled else ok


def pick_batch(root, n, scheduled=False):
    """Up to n open issues of approved PRDs that share no failing test and no fingerprint (two such issues would edit the same thing)."""
    ok, chosen, tests, fps = approved_for(root, scheduled), [], set(), set()
    for iss in L.load(root):
        if iss["state"] != "open" or iss["meta"]["prd"] not in ok or not iss["tests"]:
            continue
        if tests & set(iss["tests"]) or iss["meta"]["fp"] in fps:
            continue
        chosen.append(iss)
        tests |= set(iss["tests"])
        fps.add(iss["meta"]["fp"])
        if len(chosen) >= n:
            break
    return chosen


def pick_issue(ledger_root, ref, nxt, scheduled=False):
    issues = L.load(ledger_root)
    approved = approved_for(ledger_root, scheduled)
    if ref:
        iss = L._get(issues, ref)
        if iss["state"] == "blocked":
            raise Refuse("%s is parked: `runner.py unpark %s` after you acted on it" % (iss["id"], iss["id"]))
        if iss["state"] != "open":
            raise Refuse("%s is %s, not open" % (iss["id"], iss["state"]))
        if iss["meta"]["prd"] not in approved:
            raise Refuse("the PRD of %s (%s) is not approved%s: no build without an approved PRD (docs/policies/prd-approval.md)"
                         % (iss["id"], iss["meta"]["prd"], " and in progress ([~] in docs/BACKLOG.md), which a scheduled run needs" if scheduled else ""))
        return iss
    for iss in issues:
        if iss["state"] == "open" and iss["meta"]["prd"] in approved and iss["tests"]:
            return iss
    return None


def attempt_log(run_id, model, rows):
    lines = ["Run %s (model %s), %s:" % (run_id, model, now())]
    for r in rows:
        lines.append("- attempt %d: gate %s, review %s, codes [%s], $%.2f, %ss" % (
            r["attempt"], r["gate"], r["review"], ", ".join(r["codes"]) or "-", r["cost_usd"], r["seconds"]))
    return "\n".join(lines)
