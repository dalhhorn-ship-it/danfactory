#!/usr/bin/env python3
"""Parallel build helper (ADR 0012, MISSION-5): ownership map, ownership check, serial gated landing. Stdlib only.

  python3 scripts/slices.py plan  --map DESIGN.md                      # waves and batches of at most build.max_parallel
  python3 scripts/slices.py check <branch> --map DESIGN.md --slice ID --into BRANCH
  python3 scripts/slices.py land  <branch> --map DESIGN.md --slice ID --into BRANCH [--gate-cmd CMD]

The map is a table `| Slice | Owns | Wave | Depends on |` in a design doc; extra columns are ignored, Owns holds backticked
paths or globs (`*` stays inside a directory, `**` crosses them, a trailing `/` means the whole directory).
`check` lists files changed in `into...branch` outside Owns (cross-slice requests) and exits 1. docs/INDEX.md and
docs/knowledge-graph.json are generated, so they never count (and slices must not commit them).
`land` runs in the checkout that has `into` checked out, works in a throwaway detached worktree at the branch tip, and
stops at the first failing step, naming it: (1) check, (2) rebase onto `into` if its tip moved, (3) regenerate docs/INDEX.md
and commit any change, (4) the gate (`python3 scripts/gate.py --base <into>`), (5) `merge --ff-only` into `into`.
The slice branch ref itself is not moved. Exit codes: 0 landed or ok, 1 not merged (reason printed), 2 usage.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GENERATED = ("docs/INDEX.md", "docs/knowledge-graph.json")
HARD_CAP = 4
DEFAULT_PARALLEL = 3
TICKS = re.compile(r"`([^`]+)`")


# ---------------------------------------------------------------- map

def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_map(text):
    """[{id, name, owns, wave, depends}] from the first table whose header has `Slice` and `Owns` columns."""
    lines, out, cols = text.splitlines(), [], None
    for ln in lines:
        if not ln.lstrip().startswith("|"):
            if out:
                break
            cols = None
            continue
        cells = _cells(ln)
        low = [c.lower() for c in cells]
        if cols is None:
            if "slice" in low and "owns" in low:
                cols = {k: low.index(k) for k in ("slice", "owns", "wave", "depends on") if k in low}
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        get = lambda k: cells[cols[k]] if k in cols and cols[k] < len(cells) else ""  # noqa: E731
        name = get("slice").strip("*` ")
        if not name:
            continue
        wave = re.search(r"\d+", get("wave"))
        dep = get("depends on")
        out.append({"id": name.split()[0], "name": name, "owns": TICKS.findall(get("owns")),
                    "wave": int(wave.group()) if wave else 1,
                    "depends": [] if dep in ("", "-", "–", "—") else [d for d in re.split(r"[,\s]+", re.sub(r"\(.*?\)", "", dep)) if d and d not in ("-", "–")]})
    return out


def find_slice(slices, key):
    k = key.strip().lower()
    return next((s for s in slices if s["id"].lower() == k or s["name"].lower() == k), None)


def _glob_re(pat):
    pat = pat[2:] if pat.startswith("./") else pat
    if pat.endswith("/"):
        pat += "**"
    out, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pat.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pat[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pat[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pat[i]), i + 1
    return re.compile("^" + out + "$")


def owns(slice_, path):
    return any(_glob_re(p).match(path) for p in slice_["owns"])


def outside(slice_, files):
    return [f for f in files if f not in GENERATED and not owns(slice_, f)]


def parallel_limit(root):
    """build.max_parallel from factory.json: default 3, at least 1, at most 4."""
    try:
        with open(os.path.join(root, "factory.json"), encoding="utf-8") as fh:
            n = int(((json.load(fh).get("build") or {}).get("max_parallel", DEFAULT_PARALLEL)))
    except (OSError, ValueError, TypeError):
        n = DEFAULT_PARALLEL
    return max(1, min(n, HARD_CAP))


def plan(slices, n):
    """[(wave, [[ids] batch of at most n])]: slices run in wave order; within a wave, chunks of n."""
    out = []
    for w in sorted({s["wave"] for s in slices}):
        ids = [s["id"] for s in slices if s["wave"] == w]
        out.append((w, [ids[i:i + n] for i in range(0, len(ids), n)]))
    return out


# ---------------------------------------------------------------- git

def git(cwd, *args):
    p = subprocess.run(["git", "-c", "user.name=slices", "-c", "user.email=slices@local", "-c", "commit.gpgsign=false", *args],
                       cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def changed_files(root, into, branch):
    rc, out = git(root, "diff", "--name-only", "%s...%s" % (into, branch))
    return rc, [f for f in out.splitlines() if f] if rc == 0 else out


def check(root, branch, slice_, into):
    """(ok, [files outside Owns]) or (False, message string) when git can't compare."""
    rc, files = changed_files(root, into, branch)
    if rc != 0:
        return False, "cannot compare %s...%s: %s" % (into, branch, files)
    bad = outside(slice_, files)
    return not bad, bad


def protected_branches(root):
    """main/master/production/base branch: the same list the mission branch guard uses."""
    sys.path.insert(0, os.path.join(HERE, "..", ".claude", "hooks"))
    import _gitmission
    return _gitmission.protected(root)


def land(root, branch, slice_, into, gate_cmd=None, say=print, allow_protected=False):
    """Land one slice. Returns (ok, reason). Never leaves a worktree behind. Landing into a protected branch
    (main, master, production, base) needs `allow_protected` and is refused while a mission is active."""
    if gate_cmd and os.environ.get("SLICES_TEST_GATE") != "1":
        return False, "--gate-cmd is for tests only (set SLICES_TEST_GATE=1); the gate always runs scripts/gate.py"
    if re.sub(r"^(refs/)?heads/", "", into.lstrip("+")) in protected_branches(root):
        sys.path.insert(0, os.path.join(HERE, "..", ".claude", "hooks"))
        import _mission
        if _mission.active(root):
            return False, "a mission is active: landing into protected branch %s is the user's alone (ADR 0012)" % into
        if not allow_protected:
            return False, "%s is a protected branch: pass --allow-protected to land into it on purpose" % into
    rc, head = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0 or head != into:
        return False, "not on %s: run land from the checkout that has the integration branch checked out (HEAD is %s)" % (into, head)
    ok, bad = check(root, branch, slice_, into)
    if not ok:
        return False, ("cross-slice requests (files outside Owns of slice %s): %s" % (slice_["id"], ", ".join(bad))) if isinstance(bad, list) else bad
    tmp = tempfile.mkdtemp(prefix="slices-")
    wt = os.path.join(tmp, "wt")
    try:
        rc, out = git(root, "worktree", "add", "--detach", wt, branch)
        if rc != 0:
            return False, "worktree: " + out
        _, tip = git(root, "rev-parse", into)
        _, base = git(root, "merge-base", into, branch)
        if tip != base:
            say("stale base: rebasing %s onto %s" % (branch, into))
            rc, out = git(wt, "rebase", into)
            if rc != 0:
                git(wt, "rebase", "--abort")
                return False, "rebase onto %s failed (conflict): %s" % (into, out.splitlines()[-1] if out else "")
        if os.path.isfile(os.path.join(wt, "scripts", "docs_index.py")):
            if subprocess.run([sys.executable, "scripts/docs_index.py"], cwd=wt, capture_output=True, text=True).returncode != 0:
                return False, "docs_index.py failed"
            if git(wt, "status", "--porcelain", "--", *GENERATED)[1]:
                git(wt, "add", *[g for g in GENERATED if os.path.exists(os.path.join(wt, g))])
                rc, out = git(wt, "commit", "-q", "-m", "docs: regenerate index (slice %s)" % slice_["id"])
                if rc != 0:
                    return False, "index commit failed: " + out
        cmd = shlex.split(gate_cmd) if gate_cmd else [sys.executable, "scripts/gate.py", "--base", into]
        g = subprocess.run(cmd, cwd=wt, capture_output=True, text=True)
        if g.returncode != 0:
            tail = (g.stdout + g.stderr).strip().splitlines()[-8:]
            return False, "gate failed (exit %d): %s" % (g.returncode, " | ".join(tail))
        _, sha = git(wt, "rev-parse", "HEAD")
        rc, out = git(root, "merge", "--ff-only", sha)
        if rc != 0:
            return False, "merge --ff-only failed: " + out.splitlines()[-1] if out else "merge --ff-only failed"
        return True, "landed %s (slice %s) at %s" % (branch, slice_["id"], sha[:10])
    finally:
        git(root, "worktree", "remove", "--force", wt)
        shutil.rmtree(tmp, ignore_errors=True)
        git(root, "worktree", "prune")


# ---------------------------------------------------------------- cli

def main(argv=None, root=None):
    ap = argparse.ArgumentParser(prog="slices.py", description="Parallel build: ownership map, check, serial gated landing")
    ap.add_argument("cmd", choices=("plan", "check", "land"))
    ap.add_argument("branch", nargs="?")
    ap.add_argument("--map", required=True, help="design doc holding the slice table")
    ap.add_argument("--slice")
    ap.add_argument("--into")
    ap.add_argument("--gate-cmd", help="tests only (needs SLICES_TEST_GATE=1): override the gate command")
    ap.add_argument("--allow-protected", action="store_true", help="allow --into main/master/production (refused during a mission)")
    ap.add_argument("--root", default=None)
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root or root or os.getcwd())
    mp = a.map if os.path.isabs(a.map) else os.path.join(root, a.map)
    try:
        with open(mp, encoding="utf-8") as fh:
            slices = parse_map(fh.read())
    except OSError as ex:
        print("cannot read map: %s" % ex, file=sys.stderr)
        return 2
    if not slices:
        print("no slice table (| Slice | Owns | Wave | Depends on |) in %s" % a.map, file=sys.stderr)
        return 2
    if a.cmd == "plan":
        n = parallel_limit(root)
        print("max parallel: %d (build.max_parallel, hard cap %d)" % (n, HARD_CAP))
        for w, batches in plan(slices, n):
            print("wave %d: %s" % (w, "; then ".join(" + ".join(b) for b in batches)))
        return 0
    if not (a.branch and a.slice and a.into):
        print("%s needs <branch>, --slice and --into" % a.cmd, file=sys.stderr)
        return 2
    sl = find_slice(slices, a.slice)
    if not sl:
        print("unknown slice %r (have: %s)" % (a.slice, ", ".join(s["id"] for s in slices)), file=sys.stderr)
        return 2
    if a.cmd == "check":
        ok, bad = check(root, a.branch, sl, a.into)
        if ok:
            print("ok: every changed file is owned by slice %s" % sl["id"])
            return 0
        print(("cross-slice requests (outside Owns of %s): %s" % (sl["id"], ", ".join(bad))) if isinstance(bad, list) else bad)
        return 1
    ok, why = land(root, a.branch, sl, a.into, a.gate_cmd, allow_protected=a.allow_protected)
    print(("landed: " if ok else "NOT merged: ") + why)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
