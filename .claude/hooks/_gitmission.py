"""Branch safety while a mission is active (ADR 0012, MISSION-3). Stdlib only, Python 3.8+.

`check(prog, args, cwd) -> str` returns the reason a `git`/`gh` command must be blocked, or ''. The caller
(guard_bash_policy) only asks while a mission is active. Protected branches: main, master,
`integrations.deploy.production_branch` and `gate.base_branch` from factory.json.

Honest limits (comments, not promises): this reads command text only. git run by a script or a generated
program, shell aliases, `gh api`, `git -c alias.x=...`, refspecs built from variables and the GitHub web UI
are not seen. The real protection is GitHub branch protection plus credential scoping (ADR 0003,
docs/policies/security.md). Errors here fail open (the guard must never wedge a session).
"""
import json
import os
import subprocess

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

GIT_VALUE_GLOBALS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
PUSH_VALUE_FLAGS = {"--repo", "-o", "--push-option", "--receive-pack", "--exec", "--signed"}
MOVERS = {"commit", "merge", "pull", "rebase", "cherry-pick", "revert", "am", "reset"}
NEW_BRANCH_FLAGS = {"-b", "-B", "-c", "-C", "--orphan"}


def protected(root):
    names = {"main", "master"}
    try:
        f = _load(root)
        names.add(((f.get("integrations") or {}).get("deploy") or {}).get("production_branch") or "main")
        names.add((f.get("gate") or {}).get("base_branch") or "main")
    except Exception:  # noqa: BLE001
        pass
    return {n for n in names if n}


def _load(root):
    with open(os.path.join(root or ROOT, "factory.json"), encoding="utf-8") as fh:
        return json.load(fh)


def norm(ref):
    ref = ref.lstrip("+")
    for pre in ("refs/heads/", "heads/"):
        if ref.startswith(pre):
            ref = ref[len(pre):]
    return ref


def head_of(directory):
    try:
        p = subprocess.run(["git", "-C", directory, "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, timeout=10, check=False)
        return p.stdout.strip() if p.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def split_git(args):
    """(directory override, subcommand, rest) from the args after `git`."""
    i, cdir, base = 0, None, None
    while i < len(args):
        a = args[i]
        if a in GIT_VALUE_GLOBALS:
            if a == "-C" and i + 1 < len(args):
                cdir = args[i + 1] if cdir is None or os.path.isabs(args[i + 1]) else os.path.join(cdir, args[i + 1])
            i += 2
            continue
        if not a.startswith("-"):
            return cdir, a, args[i + 1:]
        i += 1
    return cdir, base, []


def positionals(rest, value_flags=()):
    out, skip = [], False
    for a in rest:
        if skip:
            skip = False
        elif a == "--":
            break
        elif a in value_flags:
            skip = True
        elif not a.startswith("-"):
            out.append(a)
    return out


def check(prog, args, cwd, root=None):
    try:
        return _check(prog, list(args), cwd or os.getcwd(), root)
    except Exception:  # noqa: BLE001 - fail open
        return ""


def _check(prog, args, cwd, root):
    prot = protected(root)
    why = "a mission is active: main, master and the production branch are the user's alone (ADR 0012). "
    if prog == "gh":
        pos = positionals(args, {"-R", "--repo"})
        if pos[:2] == ["pr", "merge"]:
            return why + "`gh pr merge` is blocked; the user merges the mission branch."
        return ""
    if prog != "git":
        return ""
    cdir, sub, rest = split_git(args)
    here = cdir if cdir and os.path.isabs(cdir) else os.path.join(cwd, cdir) if cdir else cwd
    cur = lambda: head_of(here)  # noqa: E731
    if sub == "push":
        if "--all" in rest or "--mirror" in rest:
            return why + "`git push --all/--mirror` would push protected branches."
        pos = positionals(rest, PUSH_VALUE_FLAGS)
        specs = pos[1:]
        if not specs:
            return why + "bare `git push` from a protected branch." if cur() in prot else ""
        for s in specs:
            dst = norm(s.split(":", 1)[1]) if ":" in s else norm(s)
            if dst == "HEAD":
                dst = cur()
            if dst in prot:
                return why + "`git push` to `%s` is blocked; push the mission branch instead." % dst
        return ""
    if sub in ("checkout", "switch"):
        for i, a in enumerate(rest):
            if a == "--":
                break
            if a in NEW_BRANCH_FLAGS:
                nxt = rest[i + 1] if i + 1 < len(rest) else ""
                return why + "creating/resetting `%s` is blocked." % nxt if norm(nxt) in prot else ""
        pos = positionals(rest)
        if "--" in rest and sub == "checkout":
            return ""  # `git checkout <tree> -- <path>` restores files, it doesn't switch
        for p in pos:
            if norm(p) in prot:
                return why + "`git %s %s` is blocked; stay on the mission branch." % (sub, p)
        return ""
    if sub == "worktree" and rest[:1] == ["add"]:
        r = rest[1:]
        for i, a in enumerate(r):
            if a in ("-b", "-B"):
                nxt = r[i + 1] if i + 1 < len(r) else ""
                return why + "creating `%s` is blocked." % nxt if norm(nxt) in prot else ""
        pos = positionals(r, {"--reason"})
        if len(pos) > 1 and norm(pos[1]) in prot:
            return why + "`git worktree add` on `%s` is blocked." % pos[1]
        return ""
    if sub == "branch":
        flags = [a for a in rest if a.startswith("-") and a != "--"]
        forced = any(f in ("--force", "--delete") or (not f.startswith("--") and set(f[1:]) & set("fMdD"))
                     for f in flags)
        if forced:
            for p in positionals(rest):
                if norm(p) in prot:
                    return why + "changing or deleting `%s` is blocked." % p
        return ""
    if sub == "update-ref":
        for p in positionals(rest):
            if norm(p) in prot:
                return why + "`git update-ref` on `%s` is blocked." % p
        return ""
    if sub in MOVERS and cur() in prot:
        return why + "`git %s` while HEAD is `%s` is blocked; switch to the mission branch first." % (sub, cur())
    return ""
