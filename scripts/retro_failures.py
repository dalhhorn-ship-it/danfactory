#!/usr/bin/env python3
"""Recurring agent failures for the retro skill (docs/specs/teach-agents-to-fish.md, FISH-7). Stdlib only, no model, no network.

Gathers three kinds, each a candidate for exactly one fix class (context / tool / guardrail), chosen later with the user:
  blocked  issues parked in issues/blocked/ (only when the autonomy pack's ledger exists)
  gate     gate fail codes recurring at least `autonomy.learn_threshold` times in the window (metrics/gate.local.jsonl)
  guard    write-guard blocks in metrics/guard.local.jsonl on one path recurring at least that often

Without the pack the first kind is simply empty; this script imports nothing from the pack (learn.py, issues.py).

  python3 scripts/retro_failures.py [--root DIR] [--threshold N] [--window DAYS] [--json]
"""
import argparse
import datetime
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
GATE = "metrics/gate.local.jsonl"
GUARD = "metrics/guard.local.jsonl"
CLASSES = ("context", "tool", "guardrail")
HINT = {"blocked": "needs a person's decision; ask what the agent lacked",
        "gate": "the same rule keeps rejecting changes",
        "guard": "agents keep trying a path the guard protects"}


def rows(root, rel):
    out = []
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            for ln in fh:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    out.append(r)
    except OSError:
        pass
    return out


def recent(r, window, now):
    try:
        d = datetime.datetime.fromisoformat(str(r.get("ts")).replace("Z", "+00:00"))
    except ValueError:
        return False
    if not d.tzinfo:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return (now - d).days <= window


def blocked(root):
    """Parked issues. The ledger belongs to the autonomy pack; no issues/blocked/ means none (not an error)."""
    d = os.path.join(root, "issues", "blocked")
    out = []
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not fn.endswith(".md"):
            continue
        with open(os.path.join(d, fn), encoding="utf-8", errors="replace") as fh:
            title = next((ln[2:].strip() for ln in fh if ln.startswith("# ")), fn)
        out.append({"kind": "blocked", "subject": fn[:-3], "count": 1, "detail": title[:90]})
    return out


def gate_codes(root, threshold, window, now):
    n, last = {}, {}
    for r in rows(root, GATE):
        if r.get("verdict") == "fail" and recent(r, window, now):
            for c in r.get("codes") or []:
                n[str(c)] = n.get(str(c), 0) + 1
                last[str(c)] = str(r.get("ts"))[:10]
    return [{"kind": "gate", "subject": c, "count": k, "detail": "last %s" % last[c]}
            for c, k in sorted(n.items(), key=lambda kv: (-kv[1], kv[0])) if k >= threshold]


def guard_blocks(root, threshold, window, now):
    per = {}
    for r in rows(root, GUARD):
        if r.get("path") and recent(r, window, now):
            per.setdefault(str(r["path"]), []).append(r)
    return [{"kind": "guard", "subject": p, "count": len(v), "detail": str(v[-1].get("why") or "")[:90]}
            for p, v in sorted(per.items(), key=lambda kv: (-len(kv[1]), kv[0])) if len(v) >= threshold]


def settings(root):
    try:
        with open(os.path.join(root, "factory.json"), encoding="utf-8") as fh:
            cfg = json.load(fh).get("autonomy")
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def num(v, default):
    """A positive int setting, else the default (a bad config must not crash retro)."""
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else default


def gather(root, threshold=None, window=None):
    cfg = settings(root)
    th = threshold if threshold is not None else num(cfg.get("learn_threshold"), 3)
    wd = window if window is not None else num(cfg.get("learn_window_days"), 14)
    now = datetime.datetime.now(datetime.timezone.utc)
    return blocked(root) + gate_codes(root, th, wd, now) + guard_blocks(root, th, wd, now)


def render(items):
    if not items:
        return "No recurring agent failures in the data (blocked issues, gate fail codes, guard blocks)."
    out = ["Recurring agent failures. Give each exactly one class: " + " / ".join(CLASSES) + ", plus a proposed backlog item.", ""]
    for n, it in enumerate(items, 1):
        out.append("%d. [%s] %s x%d: %s (%s)" % (n, it["kind"], it["subject"], it["count"], it["detail"], HINT[it["kind"]]))
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--root", default=ROOT)
    p.add_argument("--threshold", type=int)
    p.add_argument("--window", type=int)
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    items = gather(os.path.abspath(a.root), a.threshold, a.window)
    print(json.dumps(items, indent=1) if a.json else render(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
