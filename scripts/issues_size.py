"""Size issues for the issue ledger (FISH-6, docs/decisions/0013-size-issues.md). Stdlib only, no model calls.

An issue has a source: `test` (the default, a failing admitted acceptance test) or `size` (a product file over
`budgets.size.file_lines_max`). A size issue names one file in its header (`Source: size · File: <path>`) and has no tests; its
machine-run closing check is "the file is at or under the max". `issues.py find` files one size issue per over-budget file (never a
duplicate, a fixed one is reopened instead) and `issues.py sync` closes it when the check holds and reopens it when the file grows
over again. That tests still pass is ensured by the merge gate (and the runner's gate), not re-run here.
Split out of scripts/issues.py to keep it under the size budget; it uses issues.py helpers through `import issues` at call time."""
import os
import hashlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _size():
    try:
        from obs import size
        return size
    except ImportError:
        return None


def is_size(iss):
    return iss["meta"].get("source") == "size"


def fingerprint(path):
    return hashlib.sha256(("size\x1f" + path).encode("utf-8")).hexdigest()[:12]


def _factory(root):
    import gate
    return gate.read_json(os.path.join(root, "factory.json"), {}) or {}


def line_counts(root):
    """({product path: lines}, max) for the tracked product files now, or ({}, None) when obs/size.py is absent."""
    size = _size()
    if size is None:
        return {}, None
    return {p: n for p, n in size.current_files(root) if size.is_product(p)}, size.budgets(_factory(root))["file_lines_max"]


def check_holds(root, iss, counts=None, mx=None):
    """The closing check of a size issue: its file is at or under the max (a file that no longer exists counts)."""
    if counts is None:
        counts, mx = line_counts(root)
    if mx is None:
        return False
    return counts.get(iss["meta"]["file"], 0) <= mx


def _text(path, n, mx):
    return {"Failing tests": "_none: this issue closes when `%s` is at or under %d lines (it has %d)._" % (path, mx, n),
            "Repro": "```\nwc -l %s\n```" % path}


def _reopen(L, root, iss, sha, n, mx):
    iss["state"] = "open"
    iss["meta"].update(status="open", fixed="-", updated=L._today())
    L._note(iss, "Reopened %s at %s: %s has %d lines again (max %d)." % (L._today(), sha, iss["meta"]["file"], n, mx))
    L.save(root, iss)


def find(root, issues):
    """File one size issue per over-budget product file. -> {"created": [ids], "reopened": [ids]}; `issues` is L.load(root)."""
    import issues as L
    counts, mx = line_counts(root)
    out = {"created": [], "reopened": []}
    if mx is None:
        return out
    by_file = {}
    for i in issues:
        if is_size(i):
            by_file.setdefault(i["meta"]["file"], []).append(i)
    sha, nums = L.head_sha(root), [L._next_num(root, issues)]
    for path in sorted(p for p, n in counts.items() if n > mx):
        have = by_file.get(path, [])
        live = [i for i in have if i["state"] in ("open", "blocked")]
        if live:  # a parked issue still owns its file
            continue
        if have:
            iss = have[-1]
            _reopen(L, root, iss, sha, counts[path], mx)
            out["reopened"].append(iss["id"])
            continue
        num = nums[0]
        nums[0] += 1
        today = L._today()
        iss = {"num": num, "id": "ISS-%04d" % num, "slug": L._slugify("split-" + path), "state": "open", "path": "",
               "title": "Split %s (%d lines, max %d)" % (path, counts[path], mx),
               "meta": {"status": "open", "prd": "-", "item": "-", "fp": fingerprint(path), "opened": today, "updated": today,
                        "fixed": "-", "source": "size", "file": path},
               "sections": dict(_text(path, counts[path], mx), **{
                   "Suspected root cause": "_not analysed yet (finder)_",
                   "Notes": "- Split it along its existing seams into modules under the max; behaviour must not change and every test must still pass."}),
               "tests": {}}
        L.save(root, iss)
        out["created"].append(iss["id"])
    return out


def sync(root, issues):
    """Close open size issues whose file is at or under the max; reopen fixed ones whose file is over again."""
    import issues as L
    counts, mx = line_counts(root)
    out = {"fixed": [], "reopened": []}
    if mx is None:
        return out
    sha = L.head_sha(root)
    for iss in issues:
        if not is_size(iss):
            continue
        ok = check_holds(root, iss, counts, mx)
        if iss["state"] == "open" and ok:
            iss["state"] = "fixed"
            iss["meta"].update(status="fixed", fixed="%s %s" % (L._today(), sha), updated=L._today())
            L.save(root, iss)
            out["fixed"].append(iss["id"])
        elif iss["state"] == "fixed" and not ok:
            _reopen(L, root, iss, sha, counts.get(iss["meta"]["file"], 0), mx)
            out["reopened"].append(iss["id"])
    return out
