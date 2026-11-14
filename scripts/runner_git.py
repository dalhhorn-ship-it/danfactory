"""Fixer runner git plumbing: worktrees, the staging branch, checkouts, protected-path reverts.
Split from scripts/runner.py (SIZE-3); `runner` re-exports every name, so `runner.<name>` still works."""
import contextlib
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gate  # noqa: E402
import sandbox as S  # noqa: E402

from runner_core import BASELINE, Fail, Refuse, SANDBOX_ARTIFACTS, WT_LOCK, git, out_of


def current_branch(root):
    b = out_of(git(["symbolic-ref", "--quiet", "--short", "HEAD"], root, check=False))
    if not b:
        raise Refuse("HEAD is detached: check out the branch the fixes should build on")
    return b


def worktrees(root):
    """{branch: path} of checked-out branches, from `git worktree list --porcelain`."""
    res, path = {}, None
    for ln in out_of(git(["worktree", "list", "--porcelain"], root)).splitlines():
        if ln.startswith("worktree "):
            path = ln[9:]
        elif ln.startswith("branch refs/heads/") and path:
            res[ln[18:]] = path
    return res


def wt_dir(root, name):
    return os.path.join(root, ".claude", "worktrees", name)


def remove_wt(root, path):
    with WT_LOCK:
        if os.path.exists(path):
            git(["worktree", "remove", "--force", path], root, check=False)
            shutil.rmtree(path, ignore_errors=True)
        git(["worktree", "prune"], root, check=False)


def ensure_staging(root, cfg):
    """(path of a worktree with the staging branch checked out, whether it is a temporary one we must remove).
    Creates staging from the current branch if missing and merges the current branch in when it moved ahead."""
    st, cur = cfg["staging_branch"], current_branch(root)
    if st == gate.config(root)[1].get("base_branch", "main"):
        raise Refuse("autonomy.staging_branch must differ from the production branch (%s)" % st)
    if git(["rev-parse", "--verify", "--quiet", "refs/heads/" + st], root, check=False).returncode != 0:
        git(["branch", st, "HEAD"], root)
    where = worktrees(root).get(st)
    temp = False
    if where and os.path.abspath(where) == os.path.abspath(root):
        wt = root
    else:
        wt = wt_dir(root, "runner-staging")
        if where and os.path.abspath(where) != os.path.abspath(wt):
            raise Refuse("branch %s is checked out in %s: check out another branch there first" % (st, where))
        if where:  # leftover of a crashed run: keep its uncommitted rows, drop everything else
            git(["add", S.RUNNER_ROWS], wt, check=False)
            git(["commit", "-q", "-m", "runner: recover rows of an interrupted run"], wt, check=False)
            git(["reset", "-q", "--hard"], wt, check=False)
        else:
            os.makedirs(os.path.dirname(wt), exist_ok=True)
            git(["worktree", "add", "-q", wt, st], root)
        temp = True
    if cur != st and git(["merge-base", "--is-ancestor", cur, st], root, check=False).returncode != 0:
        m = git(["merge", "--no-edit", "-q", cur], wt, check=False)
        if m.returncode != 0:
            git(["merge", "--abort"], wt, check=False)
            if temp:
                remove_wt(root, wt)
            raise Refuse("could not bring %s up to date with %s (%s): merge them yourself" % (st, cur, (m.stderr or m.stdout).strip()[:120]))
    return wt, temp


class WT:
    """A worktree the runner drives. Every git call names the git dir and work tree the runner read from the main repository
    when it created the worktree (explicit -C, --git-dir, --work-tree), never what the worktree's own .git file says. identity()
    detects a worktree whose .git file, git dir, common dir or branch was changed behind our back."""

    def __init__(self, root, path):
        self.root, self.path = root, os.path.realpath(path)
        self.gd = os.path.realpath(out_of(git(["rev-parse", "--absolute-git-dir"], path)))
        self.common = os.path.realpath(out_of(git(["rev-parse", "--path-format=absolute", "--git-common-dir"], path)))
        with open(os.path.join(self.path, ".git"), "rb") as fh:
            self.dotgit = fh.read()

    def g(self, args, check=True):
        return git(["-C", self.path, "--git-dir", self.gd, "--work-tree", self.path] + list(args), self.path, check=check)

    def identity(self, branch=None):
        """None when nothing moved, else what did."""
        try:
            with open(os.path.join(self.path, ".git"), "rb") as fh:
                if fh.read() != self.dotgit:
                    return "the .git file changed"
        except OSError:
            return "the .git file is gone or not a file"
        own = lambda a: os.path.realpath(out_of(git(["-C", self.path] + a, self.path, check=False)))  # noqa: E731
        if own(["rev-parse", "--absolute-git-dir"]) != self.gd:
            return "git-dir moved"
        if own(["rev-parse", "--path-format=absolute", "--git-common-dir"]) != self.common:
            return "git-common-dir moved"
        if branch and out_of(self.g(["symbolic-ref", "--quiet", "HEAD"], check=False)) != "refs/heads/" + branch:
            return "HEAD is not refs/heads/%s" % branch
        return None

    def head(self):
        return out_of(self.g(["rev-parse", "HEAD"], check=False))

    def dirty(self):
        """Anything in the work tree beyond the commit, ignored files included."""
        return out_of(self.g(["status", "--porcelain", "--ignored", "--untracked-files=all"], check=False))


@contextlib.contextmanager
def checkout(root, commit, name):
    """A FRESH detached checkout of `commit` (clean by construction: no ignored or untracked leftovers of the fixer's tree)
    that is removed afterwards. What is tested, reviewed and gated is exactly what would merge."""
    path = wt_dir(root, name)
    remove_wt(root, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with WT_LOCK:
        git(["worktree", "add", "-q", "--detach", path, commit], root)
    try:
        w = WT(root, path)
        w.commit = commit
        if w.head() != commit or w.dirty():
            raise Fail("checkout-not-clean", "a fresh checkout of the commit was not clean: " + w.dirty()[:120])
        yield w
    finally:
        remove_wt(root, path)


def drop_sandbox_artifacts(w):
    untracked = [p for p in out_of(w.g(["ls-files", "--others", "--exclude-standard", "-z"])).split("\0") if p]
    # ignored ones too: a project that git-ignores .env (every project from this template) still gets the empty mount point (pilot 2)
    untracked += [p for p in out_of(w.g(["ls-files", "--others", "--ignored", "--exclude-standard", "-z"])).split("\0") if p]
    for p in untracked:
        full = os.path.join(w.path, p)
        if p in SANDBOX_ARTIFACTS and os.path.isfile(full) and os.path.getsize(full) == 0:
            os.remove(full)
    for p in out_of(w.g(["ls-files", "--others", "--ignored", "--exclude-standard", "-z"])).split("\0"):
        if p and is_bytecode_cache(p):  # hooks inside the agent's session write .pyc caches (pilot 2); never part of what merges
            try:
                os.remove(os.path.join(w.path, p))
            except OSError:
                pass


def changed_files(w):
    tracked = out_of(w.g(["diff", "--name-only", "-z", "HEAD"])).split("\0")
    other = out_of(w.g(["ls-files", "--others", "--exclude-standard", "-z"])).split("\0")
    return sorted({p for p in tracked + other if p})


def is_bytecode_cache(path):
    """A Python bytecode cache file (`__pycache__/x.cpython-313.pyc`): ignored, never committed, never in the evaluated checkout."""
    parts = path.split("/")
    return len(parts) >= 2 and parts[-2] == "__pycache__" and parts[-1].endswith((".pyc", ".pyo"))


def hidden_protected(w, files, pats):
    """Protected paths the plain change list cannot see: ignored untracked files that match, and a changed .gitignore that would
    make a protected path (a tracked one, or a concrete name a protected glob stands for) ignored."""
    hit = [p for p in out_of(w.g(["ls-files", "--others", "--ignored", "--exclude-standard", "-z"])).split("\0") if p and gate.matches(p, pats)]
    caches = [p for p in hit if is_bytecode_cache(p)]
    for p in caches:  # interpreter caches the agent's own hooks wrote; what is evaluated is a fresh checkout, so they cannot count
        try:
            os.remove(os.path.join(w.path, p))
        except OSError:
            pass
    hit = [p for p in hit if p not in caches]
    ignores = [p for p in files if os.path.basename(p) == ".gitignore"]
    if ignores:
        tracked = [p for p in out_of(w.g(["ls-files", "-z"])).split("\0") if p and gate.matches(p, pats)]
        cand = sorted(set(tracked + [re.sub(r"\*+", "x", p) for p in pats]))
        r = w.g(["check-ignore", "--no-index", "--"] + cand, check=False)
        if out_of(r):
            hit += ignores
    return sorted(set(hit))


def revert(w, paths):
    for p in paths:
        if w.g(["ls-files", "--error-unmatch", p], check=False).returncode == 0:
            w.g(["checkout", "HEAD", "--", p], check=False)
        else:
            try:
                os.remove(os.path.join(w.path, p))
            except OSError:
                pass


def commit_ledger(wt, msg):
    git(["add", "-A", "--", "issues", S.RUNNER_ROWS], wt, check=False)
    if os.path.exists(os.path.join(wt, BASELINE)):  # a missing pathspec would fail the whole add
        git(["add", "--", BASELINE], wt, check=False)
    if git(["diff", "--cached", "--quiet"], wt, check=False).returncode != 0:
        git(["commit", "-q", "-m", msg], wt)
