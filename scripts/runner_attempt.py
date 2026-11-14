"""Fixer runner attempt: one fixer attempt end to end, and the in-process gate verdict it relies on.
Split from scripts/runner.py (SIZE-3); `runner` re-exports every name, so `runner.<name>` still works."""
import os
import secrets
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gate  # noqa: E402
import issues as L  # noqa: E402
import sandbox as S  # noqa: E402

from runner_core import Fail, GATE_LOCK, RUNNER_PROTECTED, WT_LOCK, git, now, out_of
from runner_git import WT, changed_files, checkout, drop_sandbox_artifacts, hidden_protected, remove_wt, revert, wt_dir
from runner_agent import call_claude, fixer_prompt, parse_verdict, review_prompt


DIFF_MAX = 40000

def gate_verdict(path, base):
    """gate.py in-process with review forced to required, in a fresh checkout; the gate module is the runner's own, not the
    fixer's copy, and everything it executes from the checkout runs in the tree sandbox (no network, scrubbed environment)."""
    with GATE_LOCK, S.TreeSandbox(path) as ts:  # the lock: the patched module globals are shared by the parallel fixers
        orig = gate.config

        def cfg(root):
            f, g = orig(root)
            return f, dict(g, review="required")
        gate.config, gate.WRAP = cfg, ts.gate_wrap
        try:
            return gate.run_gate(path, base)
        finally:
            gate.config, gate.WRAP = orig, None


BASE_CHECKS = ["structure", "build", "lint", "tests"]


def base_problem(root, swt, run_id):
    """None when a fresh checkout of the staging tip passes the gate's own-health checks (no fixer change involved), else why not.
    Free: no model call. Runs in the tree sandbox like every evaluation."""
    tip = out_of(git(["rev-parse", "HEAD"], swt)).strip()
    with checkout(root, tip, run_id + "-base") as bt:
        orig = gate.config
        with GATE_LOCK, S.TreeSandbox(bt.path) as ts:
            gate.WRAP = ts.gate_wrap
            try:
                v = gate.run_gate(bt.path, tip, only=BASE_CHECKS)
            finally:
                gate.config, gate.WRAP = orig, None
    return None if v["verdict"] == "pass" else " | ".join(gate_reasons(v))


def gate_reasons(v):
    return ["- gate `%s` [%s]: %s" % (c["id"], ", ".join(c["codes"]), c["detail"][:300]) for c in v["checks"] if c["status"] == "fail"]


def attempt(root, cfg, iss, prd, run_id, k, prev, model, review_model, staging, left, est):
    """One attempt in a fresh worktree. Returns (row, reasons for the next attempt). `left()` is the USD still allowed by the
    caps before this attempt; `est` the cost guess for a call that gives no usage."""
    name = "runner-" + iss["id"]
    wtp, branch = wt_dir(root, name), "fix/" + iss["id"]
    remove_wt(root, wtp)
    os.makedirs(os.path.dirname(wtp), exist_ok=True)
    with WT_LOCK:
        base = out_of(git(["rev-parse", staging], root))
        # from the sha just read, not the branch name: another fixer's ledger commit can move staging in between, and the
        # `reset --soft base` below would then show that commit's files (metrics/runner.jsonl) as the fixer's changes
        git(["worktree", "add", "-q", "-B", branch, wtp, base], root)
    w = WT(root, wtp)
    row = {"ts": now(), "kind": "attempt", "run": run_id, "issue": iss["id"], "attempt": k, "model": model, "review_model": review_model,
           "cost_usd": 0.0, "fixer_cost_usd": 0.0, "review_cost_usd": 0.0, "tokens_in": 0, "tokens_cache": 0, "tokens_out": 0,
           "seconds": 0.0, "gate": "skip", "codes": [], "review": "-", "outcome": "fail", "base": base[:9]}
    t0 = time.time()
    reasons = []

    def done(codes, reason):
        row["codes"] = codes
        row["seconds"] = round(time.time() - t0, 1)
        row["cost_usd"] = round(row["fixer_cost_usd"] + row["review_cost_usd"], 5)
        reasons.extend(reason if isinstance(reason, list) else [reason])
        if codes:  # the full reason goes into the record, so a failure is diagnosed from runner.jsonl, not by rerunning (pilot 2)
            row["detail"] = " | ".join(str(r) for r in (reason if isinstance(reason, list) else [reason]))[:1000]
        return row, reasons

    def left_now():
        return left() - row["fixer_cost_usd"] - row["review_cost_usd"]

    def intact(tree, what, br=None):
        problem = tree.identity(br)
        if problem:
            raise Fail("worktree-tampered", "- the worktree was tampered with %s (%s): attempt lost" % (what, problem))

    try:
        intact(w, "before the fixer", branch)
        cap_now = left_now()
        if cap_now <= 0:
            raise Fail("budget-stop", "budget: nothing left for the fixer")
        rel = "issues/%s/%s" % (iss["state"], os.path.basename(iss["path"]))
        f = call_claude(fixer_prompt(iss, rel, prd, run_id, k, int(cfg["max_attempts"]), prev), model, int(cfg["max_turns"]), wtp, cfg, S.TOOLS,
                        max_budget=cap_now, est=est)
        row["fixer_cost_usd"] = f["cost"]
        if f["estimated"]:
            row["cost_estimated"] = True
        for key in ("tokens_in", "tokens_cache", "tokens_out"):
            row[key] = f["tokens"][key]
        intact(w, "by the fixer", branch)
        if f["rc"] == 124:
            return done(["fixer-timeout"], "- fixer timed out after %ss" % cfg["timeout_s"])
        if not f["has_result"]:
            return done(["fixer-error"], "- fixer produced no result (claude exit %s)" % f["rc"])
        # a commit the fixer made itself (with trailers of its own choosing) is squashed away: only the runner's commit survives
        w.g(["reset", "-q", "--soft", base], check=False)
        drop_sandbox_artifacts(w)
        files = changed_files(w)
        pats = list(gate.config(root)[1].get("protected") or []) + RUNNER_PROTECTED
        hit = sorted(set([p for p in files if gate.matches(p, pats)] + hidden_protected(w, files, pats)))
        if hit:
            revert(w, hit)
            return done(["fixer-touched-protected"], "- you changed protected paths (reverted, attempt lost): " + ", ".join(hit[:6]))
        if not files:
            return done(["no-change"], "- the fixer changed no file")
        msg = "fix(%s): %s\n\nRefs: %s\nFixer-Attempt: %d\nRunner: %s\n" % (iss["id"], iss["title"][:70], iss["id"], k, run_id)
        w.g(["add", "-A"])
        w.g(["commit", "-q", "-m", msg])
        c1 = w.head()
        diff = w.g(["diff", "--stat", "--patch", "%s..%s" % (base, c1)]).stdout
        if len(diff) > DIFF_MAX:  # never review a truncated diff: the unseen part could be anything
            return done(["diff-too-large"], "- the change is too large to review (%d bytes, limit %d): make a smaller change" % (len(diff), DIFF_MAX))
        # what is tested, reviewed and gated is a FRESH checkout of the commit, so ignored or untracked leftovers of the fixer's tree
        # cannot influence a result; fixer-written code runs in the tree sandbox
        # the issue's own tests must pass: the gate's baseline check does not cover tests that were failing when admitted
        try:
            with checkout(root, c1, name + "-tests") as t, S.TreeSandbox(t.path) as ts:
                tests, _adm = L.results(t.path, None, env=ts.acceptance_env())
        except (L.Usage, S.SandboxUnavailable) as ex:
            return done(["acceptance-error"], "- acceptance suite did not run: %s" % str(ex)[:200])
        still = sorted(t for t in iss["tests"] if tests.get(t, {}).get("status") != "pass")
        if still:
            return done(["issue-not-fixed"], ["- issue tests still failing: %s: %s" % (t, (tests.get(t) or {}).get("message", "missing")[:160]) for t in still[:5]])
        cap_now = left_now()
        if cap_now <= 0:
            raise Fail("budget-stop", "budget: nothing left for the reviewer")
        nonce = secrets.token_hex(8)
        with checkout(root, c1, name + "-review") as rtree:
            rv = call_claude(review_prompt(iss, prd, diff, nonce), review_model, int(cfg["review_turns"]), rtree.path, cfg, S.READ_TOOLS,
                             max_budget=cap_now, est=est, reviewer=True)
            row["review_cost_usd"] = rv["cost"]
            if rv["estimated"]:
                row["cost_estimated"] = True
            drop_sandbox_artifacts(rtree)  # the reviewer's Bash sandbox leaves empty mount points here too (smoke run); nothing else is tolerated
            bad = rtree.identity() or ("HEAD moved" if rtree.head() != c1 else None) or ("the tree was modified: " + rtree.dirty()[:100] if rtree.dirty() else None)
            if bad:
                raise Fail("reviewer-modified-tree", "- the reviewer changed the tree it was given (%s): attempt lost" % bad)
        intact(w, "during the review", branch)
        verdict = parse_verdict(rv["text"], nonce) if rv["has_result"] else None
        row["review"] = verdict or "fix-first"
        if verdict is None:
            row["codes"].append("review-unparsed")
        note = " ".join((rv["text"] or "").split())[:400]
        w.g(["commit", "-q", "--amend", "-m", msg + "Review: %s\n" % row["review"]])
        c2 = w.head()
        if out_of(w.g(["rev-parse", c1 + "^{tree}"])) != out_of(w.g(["rev-parse", c2 + "^{tree}"])):
            raise Fail("worktree-tampered", "- the tree changed between review and gate: attempt lost")
        with checkout(root, c2, name + "-gate") as gt:
            v = gate_verdict(gt.path, base)
        row["gate"] = v["verdict"]
        codes = list(v["codes"]) + [c for c in row["codes"] if c not in v["codes"]]
        if v["verdict"] == "pass" and row["review"] == "ship":
            row["outcome"] = "pass"
            return done([], [])
        rs = gate_reasons(v)
        if row["review"] != "ship":
            rs.append("- reviewer said fix-first: " + (note or "no reasons given"))
        return done(codes, rs)
    except Fail as ex:
        return done(row["codes"] + [ex.code], ex.msg)
