#!/usr/bin/env python3
"""Release train (AUTO-5, ADR 0010 C5): verify the staging branch as a batch, report it, handle a failed smoke.

  release.py verify                      fresh checkout of the staging tip -> full gate (acceptance suite against the baseline,
                                         every check, review required) in the tree sandbox -> a row in metrics/releases.jsonl
  release.py report                      the latest row in plain words, then the exact commands YOU run to promote
  release.py smoke-failed <sha> [--reason TEXT]
                                         branch revert/<sha> (git revert of the promoted merge) + an issue with the reason

Nothing here merges into, commits on, checks out or pushes the production branch, and nothing pushes anywhere: the user
promotes and pushes (docs/policies/runner.md). Exit 0 ok / verdict pass, 1 verdict fail or revert conflict, 2 refused."""
import argparse
import datetime
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gate  # noqa: E402
import issues as L  # noqa: E402
import runner as R  # noqa: E402
import sandbox as S  # noqa: E402

ROWS = os.path.join("metrics", "releases.jsonl")
EMPTY = "No release verification yet: `python3 scripts/release.py verify` (docs/policies/runner.md)."
Refuse = R.Refuse


def prod_branch(root):
    return (gate.config(root)[1] or {}).get("base_branch", "main")


def git(args, cwd, check=True):
    return R.git(args, cwd, check=check)


def rev(root, ref):
    p = git(["rev-parse", "--verify", "--quiet", ref + "^{commit}"], root, check=False)
    return R.out_of(p) if p.returncode == 0 else None


def rows_file(root):
    return os.path.join(root, ROWS)


def load_rows(root):
    res = []
    try:
        with open(rows_file(root), encoding="utf-8") as fh:
            for ln in fh:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    res.append(r)
    except OSError:
        pass
    return res


def guard(root, staging):
    """Refuse to operate on the production branch (or on a branch that does not exist)."""
    prod = prod_branch(root)
    if staging == prod:
        raise Refuse("%s is the production branch: release.py never operates on it (you promote, docs/policies/runner.md)" % prod)
    if not rev(root, "refs/heads/" + staging):
        raise Refuse("no branch %s: nothing to verify" % staging)
    if not rev(root, "refs/heads/" + prod):
        raise Refuse("no production branch %s" % prod)
    return prod


def last_promotion(root, staging, prod):
    """(sha, datetime) of the newest merge on the production branch (first parent) whose second parent is already in staging."""
    p = git(["log", prod, "--first-parent", "--merges", "--format=%H %P|%cI"], root, check=False)
    for ln in R.out_of(p).splitlines():
        head, _, date = ln.partition("|")
        parts = head.split()
        if len(parts) >= 3 and git(["merge-base", "--is-ancestor", parts[2], staging], root, check=False).returncode == 0:
            return parts[0], datetime.datetime.fromisoformat(date)
    return None, None


def batch(root, staging, prod):
    """Non-merge commits staging has and prod lacks [{sha, subject}], and the issue ids their Refs trailers cite."""
    p = git(["log", "--no-merges", "--format=%h\t%s%n%b%x00", "%s..%s" % (prod, staging)], root, check=False)
    commits, ids = [], []
    for ent in R.out_of(p).split("\0"):
        ent = ent.strip("\n")
        if not ent:
            continue
        head, _, body = ent.partition("\n")
        sha, _, subj = head.partition("\t")
        commits.append({"sha": sha, "subject": subj})
        for m in re.finditer(r"^Refs:\s*(ISS-\d+)\b", body, re.M):
            if m.group(1) not in ids:
                ids.append(m.group(1))
    return commits, sorted(ids)


def cost_since(root, staging, when):
    since = when.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if when else None
    rows = R.load_rows(root, staging)
    return round(R.spent([r for r in rows if since is None or str(r.get("ts", "")) > since]), 4)


def cmd_verify(a, root):
    staging = a.branch or R.settings(root)["staging_branch"]
    prod = guard(root, staging)
    why = S.tree_sandbox_problem()
    if why:
        raise Refuse("cannot verify without the tree sandbox: %s" % why)
    tip = rev(root, "refs/heads/" + staging)
    commits, ids = batch(root, staging, prod)
    promo_sha, promo_when = last_promotion(root, staging, prod)
    t0 = time.monotonic()
    with R.checkout(root, tip, "release-verify") as w:
        v = R.gate_verdict(w.path, prod)
    row = {"ts": R.now(), "kind": "verify", "staging": staging, "prod": prod, "staging_tip": tip[:12], "prod_tip": (rev(root, prod) or "")[:12],
           "commits": commits, "issues": ids, "verdict": v["verdict"], "codes": v.get("codes", []),
           "checks": [{"id": c["id"], "status": c["status"], "codes": c["codes"]} for c in v["checks"]],
           "cost_usd": cost_since(root, staging, promo_when), "last_promotion": promo_sha, "seconds": round(time.monotonic() - t0, 1)}
    S.append_row(rows_file(root), row)
    print(text(row, tip))
    return 0 if row["verdict"] == "pass" else 1


def commands(row):
    return ["git log --oneline %s..%s" % (row["prod"], row["staging"]),
            "git checkout %s && git merge --no-ff %s && git push" % (row["prod"], row["staging"])]


def text(row, current_tip=None):
    ok = row["verdict"] == "pass"
    out = ["release report %s: %s %s the gate as a batch (%d commit(s) ahead of %s)"
           % (row["ts"], row["staging"], "PASSES" if ok else "FAILS", len(row["commits"]), row["prod"])]
    out += ["  %s %s" % (c["sha"], c["subject"]) for c in row["commits"]] or ["  (no commits ahead: nothing to promote)"]
    out.append("issues fixed: %s" % (", ".join(row["issues"]) or "none cited"))
    out.append("verdict: %s%s" % (row["verdict"], " [%s]" % ", ".join(row["codes"]) if row["codes"] else ""))
    out.append("cost since the last promotion: $%.2f" % row["cost_usd"])
    stale = current_tip is not None and not current_tip.startswith(row["staging_tip"])
    if stale:
        out.append("WARNING: %s moved since this verification: run `python3 scripts/release.py verify` again before promoting" % row["staging"])
    if not ok:
        out.append("Do NOT promote: the batch fails the gate (codes above).")
    out.append("To promote, you run (nothing here pushes):" if ok and not stale and row["commits"] else "When it is ready, you promote with:")
    out += ["  " + c for c in commands(row)]
    return "\n".join(out)


def latest(root):
    rows = [r for r in load_rows(root) if r.get("kind") == "verify"]
    return rows[-1] if rows else None


def cmd_report(a, root):
    row = latest(root)
    if not row:
        print(EMPTY)
        return 0
    print(text(row, rev(root, "refs/heads/" + row["staging"])))
    return 0


def file_issue(root, sha, reason, note):
    num = L._next_num(root, L.load(root))
    today = L._today()
    iss = {"num": num, "id": "ISS-%04d" % num, "slug": "smoke-failed-" + sha[:7], "state": "open", "path": "",
           "title": ("post-deploy smoke failed after promoting %s: %s" % (sha[:7], reason or "no reason given"))[:90],
           "meta": {"status": "open", "prd": "-", "item": "-", "fp": "smoke" + sha[:7], "opened": today, "updated": today, "fixed": "-"},
           "sections": {"Suspected root cause": "The promoted change %s (smoke reason: %s)." % (sha[:12], reason or "none given"),
                        "Notes": "- %s\n- No approved PRD is linked: the runner will not pick this up; triage it yourself." % note},
           "tests": {}}
    L.save(root, iss)
    with open(iss["path"], encoding="utf-8") as fh:
        body = fh.read()
    body = re.sub(r"```\npython3 scripts/acceptance.py run --ids[ ]*\n```", "```\n(no failing test: a post-deploy smoke failed)\n```", body)
    with open(iss["path"], "w", encoding="utf-8") as fh:
        fh.write(body)
    return iss["id"]


def cmd_smoke_failed(a, root):
    prod = prod_branch(root)
    full = rev(root, a.sha)
    if not full:
        raise Refuse("unknown commit %s" % a.sha)
    if not rev(root, "refs/heads/" + prod) or git(["merge-base", "--is-ancestor", full, prod], root, check=False).returncode != 0:
        raise Refuse("%s is not on %s: only a promoted commit can be reverted" % (a.sha, prod))
    branch = "revert/" + full[:7]
    if rev(root, "refs/heads/" + branch):
        raise Refuse("branch %s already exists: finish or delete it first" % branch)
    wt = R.wt_dir(root, "release-revert")
    R.remove_wt(root, wt)
    os.makedirs(os.path.dirname(wt), exist_ok=True)
    git(["worktree", "add", "-q", "-b", branch, wt, prod], root)  # a NEW branch at the prod tip: prod itself is never checked out
    conflict = None
    try:
        merge = len(R.out_of(git(["rev-list", "--parents", "-n1", full], root)).split()) > 2
        r = git((["revert", "--no-edit", "-m", "1"] if merge else ["revert", "--no-edit"]) + [full], wt, check=False)
        if r.returncode != 0:
            conflict = (r.stderr or r.stdout).strip()[:200]
            git(["revert", "--abort"], wt, check=False)
    finally:
        R.remove_wt(root, wt)
    if conflict:
        git(["branch", "-D", branch], root, check=False)
        note = "automatic revert of %s conflicted (%s): revert it by hand" % (full[:7], conflict)
        branch = None
    else:
        note = "revert branch %s holds the revert; you review and push it" % branch
    iid = file_issue(root, full, a.reason, note)
    S.append_row(rows_file(root), {"ts": R.now(), "kind": "smoke-failed", "sha": full[:12], "reason": a.reason, "branch": branch, "issue": iid})
    print("smoke failed after %s: filed %s (in issues/open, uncommitted: commit it with your next change)" % (full[:7], iid))
    if conflict:
        print("release: the automatic revert conflicted (%s); no branch created. Revert by hand." % conflict, file=sys.stderr)
        return 1
    print("created branch %s (revert of %s). Review, then push it yourself: git push origin %s" % (branch, full[:7], branch))
    return 0


def open_reverts(root, prod):
    if not rev(root, "refs/heads/" + prod):
        return []
    p = git(["for-each-ref", "--no-merged", prod, "--format=%(refname:short)", "refs/heads/revert"], root, check=False)
    return R.out_of(p).splitlines()


def summary(root):
    """Numbers for `--print` and the Autonomy tab block: staging lead, last verify, days since the last promotion, revert branches."""
    staging, prod = R.settings(root)["staging_branch"], prod_branch(root)
    row = latest(root)
    reverts = open_reverts(root, prod)
    has = rev(root, "refs/heads/" + staging) is not None and rev(root, "refs/heads/" + prod) is not None
    out = {"exists": bool(row) or bool(reverts), "staging": staging, "prod": prod,
           "lead": R.staging_lead(root, {"staging_branch": staging}, prod) if has else None,
           "verdict": row["verdict"] if row else None, "codes": row["codes"] if row else [], "verified_at": row["ts"] if row else None,
           "fresh": None, "days_since_promotion": None, "reverts": reverts}
    if row and has:
        out["fresh"] = (rev(root, "refs/heads/" + staging) or "").startswith(row["staging_tip"])
    if has:
        _, when = last_promotion(root, staging, prod)
        if when:
            out["days_since_promotion"] = max(0, (datetime.datetime.now(datetime.timezone.utc) - when).days)
    return out


def human(st):
    if not st["exists"]:
        return EMPTY
    v = "none yet" if not st["verdict"] else "%s%s%s" % (st["verdict"], " [%s]" % ", ".join(st["codes"]) if st["codes"] else "",
                                                           "" if st["fresh"] in (None, True) else " (stale: staging moved since)")
    days = "never" if st["days_since_promotion"] is None else "%d day(s) ago" % st["days_since_promotion"]
    out = ["release: %s is %s commit(s) ahead of %s; last verify %s; last promotion %s"
           % (st["staging"], "?" if st["lead"] is None else st["lead"], st["prod"], v, days)]
    out += ["open revert branch: %s (review and push it yourself)" % b for b in st["reverts"]]
    return "\n".join(out)


def main(argv=None, root=None):
    ap = argparse.ArgumentParser(prog="release.py", description="Release train (docs/policies/runner.md)")
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("verify")
    s.add_argument("--branch", help="staging branch to verify (default autonomy.staging_branch); never the production branch")
    sub.add_parser("report")
    s = sub.add_parser("smoke-failed")
    s.add_argument("sha")
    s.add_argument("--reason", default="")
    try:
        a = ap.parse_args(argv)
    except SystemExit as ex:
        return 0 if ex.code in (0, None) else 2
    root = os.path.abspath(a.root or root or os.getcwd())
    try:
        return {"verify": cmd_verify, "report": cmd_report, "smoke-failed": cmd_smoke_failed}[a.cmd](a, root)
    except (Refuse, L.Usage) as ex:
        print("release: refused: %s" % ex, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
