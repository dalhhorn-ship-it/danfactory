#!/usr/bin/env python3
"""Optional packs (ADR 0011, SIZE-2). Stdlib only.

  python3 scripts/pack.py status            which packs are in and the lines each adds
  python3 scripts/pack.py add <name>        fetch the pack's files from the template at factory.json template.ref, run its tests
  python3 scripts/pack.py remove <name>     delete the pack's files, set packs.<name> false

A pack is packs/<name>.json: {"files": [...], "tests": [...], "description": ...}. The template repo itself always keeps
every pack's files (add and remove refuse there). `add` fetches ONLY the manifest's files, with git, from
template.source_repo ("owner/repo", a URL or a local path) at template.ref, which must be a full 40-hex commit SHA and is
verified after the fetch (same pattern as scripts/install-skill.sh; nothing is piped into a shell). The manifest used is the one at that commit.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
from _common import template_mode  # noqa: E402

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")


class PackError(Exception):
    pass


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_factory(root, f):
    with open(os.path.join(root, "factory.json"), "w", encoding="utf-8") as fh:
        json.dump(f, fh, indent=2)
        fh.write("\n")


def safe_rel(p):
    n = os.path.normpath(p)
    if os.path.isabs(n) or n.startswith("..") or n in (".", "") or ".git" in n.split(os.sep):
        raise PackError("manifest path not allowed: %r" % p)
    return n


def manifest(root, name):
    if not NAME_RE.match(name or ""):
        raise PackError("invalid pack name %r" % name)
    m = read_json(os.path.join(root, "packs", name + ".json"))
    if not isinstance(m, dict) or not isinstance(m.get("files"), list):
        raise PackError("unknown pack %r (no packs/%s.json)" % (name, name))
    return m


def parse_manifest(text, name):
    try:
        m = json.loads(text)
        assert isinstance(m["files"], list) and all(isinstance(x, str) for x in m["files"])
        assert isinstance(m.get("tests", []), list)
        return m
    except Exception:  # noqa: BLE001
        raise PackError("packs/%s.json at the pinned commit is not a valid manifest" % name)


def lines_of(path):
    try:
        with open(path, "rb") as fh:
            return fh.read().count(b"\n")
    except OSError:
        return 0


def installed(f, name):
    return bool((f.get("packs") or {}).get(name))


def set_flag(root, name, value):
    f = read_json(os.path.join(root, "factory.json"), {})
    f.setdefault("packs", {})[name] = value
    write_factory(root, f)


def reindex(root):
    subprocess.run([sys.executable, os.path.join(root, "scripts", "docs_index.py")], cwd=root, capture_output=True, check=False)


def source_url(src):
    src = (src or "").strip()
    if not src:
        raise PackError("factory.json template.source_repo is empty")
    if re.match(r"^[\w.-]+/[\w.-]+$", src) and not os.path.exists(src):
        return "https://github.com/" + src
    return src


def git(args, cwd, **kw):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, **kw)


def fetch_files(url, ref, name, tmp):
    """Fetch commit `ref` of `url` into a throwaway repo and return (manifest, {path: (bytes, executable)}). Verified."""
    src = os.path.join(tmp, "src")
    os.makedirs(src)
    for cmd in (["init", "--quiet"], ["remote", "add", "origin", url]):
        if git(cmd, src).returncode:
            raise PackError("git %s failed" % cmd[0])
    p = git(["fetch", "--quiet", "--depth", "1", "--filter=blob:none", "origin", ref], src, text=True)
    if p.returncode:
        raise PackError("could not fetch %s from %s (is template.ref a commit that exists there?): %s" % (ref, url, p.stderr.strip()[-300:]))
    head = git(["rev-parse", "FETCH_HEAD"], src, text=True).stdout.strip()
    if head != ref:
        raise PackError("fetched commit %s does not match pinned %s" % (head, ref))

    def blob(path):
        p = git(["cat-file", "blob", "FETCH_HEAD:" + path], src)
        if p.returncode:
            raise PackError("%s is not in the template at %s" % (path, ref[:10]))
        return p.stdout

    man = parse_manifest(blob("packs/%s.json" % name).decode("utf-8", "replace"), name)
    files = {}
    for rel in man["files"]:
        rel = safe_rel(rel)
        mode = git(["ls-tree", "FETCH_HEAD", "--", rel], src, text=True).stdout.split(" ")[0]
        files[rel] = (blob(rel), mode == "100755")
    return man, files


def run_tests(root, tests):
    """Run the pack's test modules, one process each in parallel (like scripts/run_tests.py); test_runner goes last and alone
    because its Parallel class is timing sensitive. Returns (exit code, tail of the output)."""
    mods = [os.path.splitext(os.path.basename(t))[0] for t in tests if t.endswith(".py")]
    env = dict(os.environ, PYTHONPATH=os.path.join(root, ".factory", "tests"))
    cmd = [sys.executable, "-W", "ignore::ResourceWarning", "-m", "unittest", "-q"]
    start = lambda ms: [(m, subprocess.Popen(cmd + [m], cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)) for m in ms]  # noqa: E731
    rc, tail = 0, ""
    for group in ([m for m in mods if m != "test_runner"], [m for m in mods if m == "test_runner"]):
        for m, pr in start(group):
            out = pr.communicate()[0]
            if pr.returncode:
                rc, tail = pr.returncode, "%s:\n%s" % (m, out[-1200:])
    return rc, tail


def prune_dirs(root, rels):
    for rel in sorted(rels, key=len, reverse=True):
        d = os.path.dirname(os.path.join(root, rel))
        while d.startswith(root + os.sep) and os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
            d = os.path.dirname(d)


def cmd_add(root, name, out=print):
    if template_mode(root=root):
        raise PackError("this is the template repo itself; it keeps every pack's files (nothing to add)")
    local = manifest(root, name) if os.path.isfile(os.path.join(root, "packs", name + ".json")) else None
    f = read_json(os.path.join(root, "factory.json"), {})
    if installed(f, name) and local and all(os.path.isfile(os.path.join(root, safe_rel(x))) for x in local["files"]):
        out("pack %s is already installed" % name)
        return 0
    t = f.get("template") or {}
    ref = str(t.get("ref") or "").strip()
    if not SHA_RE.match(ref):
        raise PackError("factory.json template.ref must be a full 40-hex commit SHA of %s (bootstrap.sh records it; "
                        "set it to a template commit that has this pack)" % (t.get("source_repo") or "the template"))
    url = source_url(t.get("source_repo"))
    tmp = tempfile.mkdtemp(prefix="pack-")
    written, backup = [], {}
    try:
        man, files = fetch_files(url, ref, name, tmp)
        for rel, (data, exe) in files.items():
            dest = os.path.join(root, rel)
            if os.path.isfile(dest):
                with open(dest, "rb") as fh:
                    backup[rel] = fh.read()
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as fh:
                fh.write(data)
            if exe:
                os.chmod(dest, 0o755)
            written.append(rel)
        os.makedirs(os.path.join(root, "packs"), exist_ok=True)
        with open(os.path.join(root, "packs", name + ".json"), "w", encoding="utf-8") as fh:
            json.dump(man, fh, indent=1)
            fh.write("\n")
        rc, tail = run_tests(root, man.get("tests", []))
        if rc:
            raise PackError("the pack's tests failed; nothing installed.\n" + tail)
    except BaseException:
        for rel in written:  # roll back: restore what was overwritten, delete what is new
            if rel in backup:
                with open(os.path.join(root, rel), "wb") as fh:
                    fh.write(backup[rel])
            else:
                os.remove(os.path.join(root, rel))
        prune_dirs(root, [r for r in written if r not in backup])
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    set_flag(root, name, True)
    reindex(root)
    out("pack %s installed: %d files from %s@%s, tests passed" % (name, len(files), url, ref[:10]))
    return 0


def cmd_remove(root, name, out=print):
    if template_mode(root=root):
        raise PackError("this is the template repo itself; it keeps every pack's files (nothing to remove)")
    m = manifest(root, name)
    gone = []
    for rel in m["files"]:
        rel = safe_rel(rel)
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            os.remove(p)
            gone.append(rel)
    prune_dirs(root, gone)
    set_flag(root, name, False)
    reindex(root)
    out("pack %s removed: %d files deleted" % (name, len(gone)))
    return 0


def status(root):
    f = read_json(os.path.join(root, "factory.json"), {})
    tm = template_mode(root=root, factory=f)
    rows = []
    d = os.path.join(root, "packs")
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not fn.endswith(".json"):
            continue
        name = fn[:-5]
        m = read_json(os.path.join(d, fn), {}) or {}
        files = [x for x in m.get("files", []) if isinstance(x, str)]
        present = [x for x in files if os.path.isfile(os.path.join(root, x))]
        rows.append({"name": name, "installed": tm or installed(f, name), "files": len(files), "present": len(present),
                     "lines": sum(lines_of(os.path.join(root, x)) for x in present),
                     "description": m.get("description", "")})
    return rows, tm


def cmd_status(root, out=print):
    rows, tm = status(root)
    if not rows:
        out("no packs (packs/*.json)")
    for r in rows:
        state = "in (template keeps the full tree)" if tm else ("installed" if r["installed"] else "not installed")
        out("%s: %s, %d/%d files present, %d lines%s" % (r["name"], state, r["present"], r["files"], r["lines"],
            "" if r["installed"] else "; add with: python3 scripts/pack.py add %s" % r["name"]))
    return 0


def main(argv=None, root=ROOT):
    a = list(sys.argv[1:] if argv is None else argv)
    try:
        if a[:1] == ["status"] and len(a) == 1:
            return cmd_status(root)
        if len(a) == 2 and a[0] in ("add", "remove"):
            return (cmd_add if a[0] == "add" else cmd_remove)(root, a[1])
        print(__doc__.strip().split("\n\n")[0], file=sys.stderr)
        return 2
    except PackError as ex:
        print("pack: %s" % ex, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
