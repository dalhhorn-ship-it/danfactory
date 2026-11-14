#!/usr/bin/env python3
"""Find the template commit a project was made from (NEW-1, TD-022). Stdlib only; needs git, and network only when
the template is a remote.

  python3 scripts/template_ref.py [ROOT]    print the 40-hex ref (or nothing offline); notes go to stderr

Order: (1) the copy's HEAD, when that commit exists upstream; (2) the newest of the last 200 upstream commits whose
files equal the copy's template files (git blob hashes); (3) the upstream main head, with a note; (4) offline: nothing,
with a note (pack.py resolves it again at `add` time against .factory/template-files.txt).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "obs"))
import tplfiles  # noqa: E402

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DEPTH = 200
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0")


def source_url(src):
    src = (src or "").strip()
    if not src:
        raise ValueError("factory.json template.source_repo is empty")
    if re.match(r"^[\w.-]+/[\w.-]+$", src) and not os.path.exists(src):
        return "https://github.com/" + src
    return src


def _git(args, cwd, timeout=120):
    try:
        return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=ENV, check=False)
    except (OSError, subprocess.SubprocessError) as ex:
        return subprocess.CompletedProcess(args, 255, "", str(ex))


def _tree(repo, commit):
    p = _git(["ls-tree", "-r", commit], repo)
    out = {}
    for line in p.stdout.splitlines():
        meta, _, path = line.partition("\t")
        mode, kind, sha = (meta.split() + ["", "", ""])[:3]
        if kind == "blob" and mode in ("100644", "100755"):
            out[path] = sha
    return out


def resolve(root, source, wanted=None, exact=True, head=None, out=None):
    """Return (ref, note). ref is "" when it cannot be found (offline); note is a one-line explanation or "".
    wanted: {path: blob hash} of the template files (default: every regular file of root); exact: the upstream tree must
    hold exactly these files (bootstrap) rather than at least these (pack.py, after bootstrap pruned the list)."""
    url = source_url(source)
    if head is None:
        p = _git(["rev-parse", "HEAD"], root)
        head = p.stdout.strip() if p.returncode == 0 and SHA_RE.match(p.stdout.strip()) else ""
    tmp = tempfile.mkdtemp(prefix="tplref-")
    try:
        _git(["init", "--quiet"], tmp)
        _git(["remote", "add", "origin", url], tmp)
        ls = _git(["ls-remote", url, "HEAD"], tmp, timeout=40)
        if ls.returncode or not ls.stdout.strip():
            return "", "could not reach %s; template.ref left empty (pack.py resolves it when you add a pack)" % url
        main_head = ls.stdout.split()[0]
        if head:
            if _git(["fetch", "--quiet", "--depth", "1", "--filter=blob:none", "origin", head], tmp).returncode == 0:
                return head, ""
        f = _git(["fetch", "--quiet", "--depth", str(DEPTH), "--filter=blob:none", "origin", "HEAD"], tmp, timeout=300)
        if f.returncode:
            return main_head, "could not read the history of %s; using its main head %s" % (url, main_head[:10])
        want = wanted if wanted is not None else tplfiles.snapshot(root)
        if want:
            commits = _git(["rev-list", "--max-count=%d" % DEPTH, "FETCH_HEAD"], tmp).stdout.split()
            for c in commits:
                tree = _tree(tmp, c)
                if exact and tree == want or not exact and all(tree.get(n) == h for n, h in want.items()):
                    return c, ""
        return main_head, "no upstream commit among the last %d matches this copy's template files; using the main head %s of %s" % (
            DEPTH, main_head[:10], url)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    root = os.path.abspath(a[0] if a else ".")
    import json
    try:
        with open(os.path.join(root, "factory.json"), encoding="utf-8") as fh:
            src = (json.load(fh).get("template") or {}).get("source_repo")
        ref, note = resolve(root, src)
    except (OSError, ValueError) as ex:
        print("template_ref: %s" % ex, file=sys.stderr)
        return 1
    if note:
        print("template ref: " + note, file=sys.stderr)
    print(ref)
    return 0


if __name__ == "__main__":
    sys.exit(main())
