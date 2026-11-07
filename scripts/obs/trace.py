"""Traceability: goal -> PRD -> backlog item -> commits -> components -> tests -> version, plus broken links."""
import re

from . import sources as S

CHAIN_CAP, COMMIT_CAP, TEST_CAP = 20, 10, 8
SLUG_RE = re.compile(r"docs/specs/([\w-]+)\.md")


def ref_keys(message):
    """Tokens after any `Refs:` in a commit message (trailer or inline)."""
    keys = set()
    for m in re.finditer(r"Refs:[ \t]*([^\n]+)", message):
        keys.update(t for t in re.split(r"[\s,;]+", m.group(1)) if t)
    return keys


def _owner(paths, f):
    return next((p for p in paths if f == p or f.startswith(p + "/")), None)


def _item(raw, prd, log, comp_paths, test_paths):
    m = S.ID_RE.match(raw["title"])
    iid = m.group(1) if m else ""
    want = {iid} if iid else {prd["slug"]}
    commits = [c for c in log if ref_keys(c["subject"] + "\n" + c["body"]) & want]
    comps = sorted({o for c in commits for f in c["files"] for o in [_owner(comp_paths, f)] if o})
    tests = sorted({f for c in commits for f in c["files"] if S.is_test(f)})
    if not tests:
        stems = [p.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower() for p in comps]
        tests = sorted(t for t in test_paths if any(len(s) > 2 and s in t.lower() for s in stems))
    broken = []
    if raw["state"] != "dropped":
        if not iid and not commits:
            broken.append("no ID or slug refs")
        if raw["state"] == "done" and not commits:
            broken.append("done, no commits")
        if commits and not tests:
            broken.append("commits, no tests")
    return {"id": iid, "title": raw["title"][len(iid):].strip() if iid else raw["title"], "state": raw["state"],
            "commits": [{"sha": c["sha"], "subject": c["subject"]} for c in commits[:COMMIT_CAP]],
            "commits_total": len(commits), "components": comps, "tests": tests[:TEST_CAP], "tests_total": len(tests),
            "version": commits[0]["version"] if commits else "", "broken": broken}


def build(root, base, arch=None):
    log = S.git_log(root)
    arch = arch or {"layers": {}}
    comp_paths = sorted((e["path"] for e in arch.get("layers", {}).get("application", [])
                         if e["type"] == "application-component" and e.get("path")), key=len, reverse=True)
    test_paths = S.test_files(root)
    items = [(ms["name"], i) for ms in base.get("progress", {}).get("milestones", []) for i in ms["items"]]
    chains, linked_keys = [], set()
    for prd in S.prds(root):
        mine = [i for name, i in items if prd["slug"] in SLUG_RE.findall(i["title"])
                or (prd["backlog"] and name.casefold() == prd["backlog"].casefold())]
        its = [_item(i, prd, log, comp_paths, test_paths) for i in mine]
        for it in its:
            linked_keys.add(it["id"] or prd["slug"])
        broken = (["no items"] if not its else []) + (["approved without date"] if prd["status"] == "approved" and not prd["approved"] else [])
        chains.append({"prd": {k: prd[k] for k in ("slug", "title", "status", "approved")},
                       "items": its, "broken": broken})
    linked = sum(1 for c in log if ref_keys(c["subject"] + "\n" + c["body"]) & linked_keys)
    return {"goal": bool(S.goal_outcome(root)),
            "chains": chains[:CHAIN_CAP], "chains_total": len(chains),
            "prds": len(chains), "items": sum(len(c["items"]) for c in chains),
            "linked_commit_pct": round(100.0 * linked / len(log)) if log else None,
            "unlinked_commits": len(log) - linked, "commits": len(log),
            "broken_total": sum(len(c["broken"]) + sum(len(i["broken"]) for i in c["items"]) for c in chains)}
