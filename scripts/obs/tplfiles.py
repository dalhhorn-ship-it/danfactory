"""Template-owned files (NEW-2): bootstrap lists each template file it keeps with its git blob hash in
.factory/template-files.txt ("<hash> <path>" per line). A listed file whose hash is unchanged is upstream's, not the
project's: the dashboard leaves it out of size flags, code markers and hotspots. An edited file counts as project code.
Stdlib only; shared by scripts/bootstrap.sh, scripts/pack.py, scripts/template_ref.py and the dashboard."""
import hashlib
import os
import subprocess

LIST = os.path.join(".factory", "template-files.txt")
SKIP_TOP = (".git", "node_modules", "__pycache__")


def blob_hash(path):
    """git blob hash of a regular file (the same value `git hash-object` prints), or None."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def tracked(root):
    """Regular files of the copy: git ls-files, or a walk when it is not a git repo."""
    try:
        p = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True, text=True, timeout=30, check=False)
        names = [x for x in p.stdout.split("\0") if x] if p.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        names = []
    if not names:
        for d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_TOP]
            names += [os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/") for f in files]
    return sorted(n for n in names if n != LIST.replace(os.sep, "/") and os.path.isfile(os.path.join(root, n)) and not os.path.islink(os.path.join(root, n)))


def snapshot(root):
    """{path: blob hash} of every regular file of the copy."""
    out = {}
    for n in tracked(root):
        h = blob_hash(os.path.join(root, n))
        if h:
            out[n] = h
    return out


def write(root, pairs):
    p = os.path.join(root, LIST)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        for n in sorted(pairs):
            fh.write("%s %s\n" % (pairs[n], n))


def read(root):
    """{path: hash} from the list; {} when there is none (the template repo itself, old projects)."""
    out = {}
    try:
        with open(os.path.join(root, LIST), encoding="utf-8") as fh:
            for line in fh:
                h, _, n = line.rstrip("\n").partition(" ")
                if len(h) == 40 and n:
                    out[n] = h
    except OSError:
        pass
    return out


def prune(root):
    """Keep only the entries whose file still exists with the recorded hash (bootstrap rewrites some files)."""
    pairs = read(root)
    keep = {n: h for n, h in pairs.items() if blob_hash(os.path.join(root, n)) == h}
    write(root, keep)
    return len(keep)


def owned(root):
    """Paths still identical to the template's version."""
    return {n for n, h in read(root).items() if blob_hash(os.path.join(root, n)) == h}


if __name__ == "__main__":
    import sys
    cmd, r = (sys.argv[1:] + ["", "."])[:2]
    if cmd == "snapshot":
        write(r, snapshot(r))
    elif cmd == "prune":
        print(prune(r))
    else:
        sys.exit("usage: tplfiles.py snapshot|prune [root]")
