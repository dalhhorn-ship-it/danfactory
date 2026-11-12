#!/usr/bin/env python3
"""Issue ledger: failing admitted acceptance tests become files in issues/open/, fixed ones move to issues/fixed/.
Design: docs/decisions/0008-issue-ledger-and-finder.md. Stdlib only, no model calls.

  issues.py find   [--from-json FILE]   file or update issues from failing admitted tests (idempotent)
  issues.py sync   [--from-json FILE]   move issues whose tests all pass to issues/fixed/; reopen regressions
  issues.py merge  ISS-a ISS-b          fold b into a
  issues.py split  ISS-a TEST-ID...     move the given tests of a into a new issue
  issues.py list   [--json]
  issues.py status [--json]             counts for the dashboard

Results come from `acceptance.py run --json` (or --from-json FILE):
  {"tests": [{"id": "<slug>/<module>::<Class>.<method>", "status": "pass|fail|error|skip", "message": "...", "where": "path:line:function"}],
   "admitted": [ids]}
Run from the project root (or set --root). Exit: 0 ok, 2 usage or missing input."""
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FAILING = ("fail", "error")
HEADER_RE = re.compile(r"^>\s*Status:\s*(\w+)\s*·\s*PRD:\s*(.*?)\s*·\s*Item:\s*(.*?)\s*·\s*Fingerprint:\s*(\w*)\s*·\s*Opened:\s*(.*?)\s*·"
                       r"\s*Updated:\s*(.*?)\s*·\s*Fixed:\s*(.*?)\s*$")
FILE_RE = re.compile(r"^ISS-(\d{4,})-(.*)\.md$")
TEST_LINE_RE = re.compile(r"^-\s+`([^`]+)`(?::\s*(.*))?$")
SECTIONS = ("Failing tests", "Repro", "Suspected root cause", "Notes")
EXC_RE = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception|Warning|Exit))\b")
EMPTY = "No issue ledger yet: the finder files issues from failing acceptance tests (ADR 0008)."


class Usage(Exception):
    pass


# ---- fingerprint ----
def slug_of(test_id):
    return test_id.split("/", 1)[0] if "/" in test_id else ""


def normalise(msg):
    """Exception type and message with quoted literals and numbers masked."""
    msg = (msg or "").strip().splitlines()[0] if (msg or "").strip() else ""
    m = EXC_RE.match(msg)
    etype = m.group(1) if m else ""
    body = msg[m.end():].lstrip(": ") if m else msg
    body = re.sub(r"'[^']*'|\"[^\"]*\"", "Q", body)
    body = re.sub(r"\d+", "N", body)
    return etype, " ".join(body.split())


def frame(where):
    """path and function of 'path:line:function' (line numbers move, so they are left out)."""
    parts = (where or "").split(":")
    if len(parts) >= 3:
        return parts[0] + ":" + ":".join(parts[2:])
    return parts[0] if parts else ""


def fingerprint(test):
    etype, body = normalise(test.get("message"))
    raw = "\x1f".join((slug_of(test["id"]), etype, body, frame(test.get("where"))))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


# ---- ledger files ----
def _dir(root, state):
    return os.path.join(root, "issues", state)


def _today():
    return datetime.date.today().isoformat()


def head_sha(root):
    try:
        p = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else "-"
    except OSError:
        return "-"


def parse(text):
    """-> {"title", "meta", "sections"}; meta is None when the header line is missing or malformed."""
    lines = text.splitlines()
    title = re.sub(r"^ISS-\d+:\s*", "", next((ln[2:].strip() for ln in lines if ln.startswith("# ")), ""))
    meta = None
    for ln in lines:
        m = HEADER_RE.match(ln)
        if m:
            meta = dict(zip(("status", "prd", "item", "fp", "opened", "updated", "fixed"), m.groups()))
            break
    secs, cur = {}, None
    for ln in lines:
        if ln.startswith("## "):
            cur = ln[3:].strip()
            secs[cur] = []
        elif cur is not None:
            secs[cur].append(ln)
    return {"title": title, "meta": meta, "sections": {k: "\n".join(v).strip("\n") for k, v in secs.items()}}


def load(root):
    """All ledger issues sorted by number: dicts with num, id, state, path, title, meta, sections, tests {id: message}."""
    out = []
    for state in ("open", "fixed"):
        d = _dir(root, state)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            m = FILE_RE.match(fn)
            if not m:
                continue
            path = os.path.join(d, fn)
            with open(path, encoding="utf-8") as fh:
                p = parse(fh.read())
            if not p["meta"]:
                continue
            tests = {}
            for ln in p["sections"].get("Failing tests", "").splitlines():
                t = TEST_LINE_RE.match(ln.strip())
                if t:
                    tests[t.group(1)] = t.group(2) or ""
            out.append({"num": int(m.group(1)), "id": "ISS-" + m.group(1), "slug": m.group(2), "state": state, "path": path,
                        "title": p["title"], "meta": p["meta"], "sections": p["sections"], "tests": tests})
    out.sort(key=lambda i: i["num"])
    return out


def _slugify(s, n=40):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n].strip("-") or "issue"


def render(iss):
    meta, secs = iss["meta"], iss["sections"]
    tests = "\n".join("- `%s`: %s" % (t, (m or "").replace("\n", " ")) for t, m in sorted(iss["tests"].items()))
    repro = "```\npython3 scripts/acceptance.py run --ids %s\n```" % ",".join(sorted(iss["tests"]))
    body = {"Failing tests": tests, "Repro": repro, "Suspected root cause": secs.get("Suspected root cause", ""),
            "Notes": secs.get("Notes", "")}
    head = "> Status: %s · PRD: %s · Item: %s · Fingerprint: %s · Opened: %s · Updated: %s · Fixed: %s" % (
        meta["status"], meta["prd"], meta["item"], meta["fp"], meta["opened"], meta["updated"], meta["fixed"])
    out = ["# %s: %s" % (iss["id"], iss["title"]), "", head, ""]
    for k in SECTIONS:
        out += ["## " + k, "", body[k].strip("\n"), ""]
    # human sections added by hand under other headings survive too
    for k, v in secs.items():
        if k not in SECTIONS:
            out += ["## " + k, "", v.strip("\n"), ""]
    return "\n".join(out).rstrip("\n") + "\n"


def save(root, iss):
    d = _dir(root, iss["state"])
    os.makedirs(d, exist_ok=True)
    new = os.path.join(d, "%s-%s.md" % (iss["id"], iss["slug"]))
    with open(new, "w", encoding="utf-8") as fh:
        fh.write(render(iss))
    if iss.get("path") and os.path.abspath(iss["path"]) != os.path.abspath(new):
        os.remove(iss["path"])
    iss["path"] = new


def _history_nums(root):
    """Numbers ever used in git history of issues/, so a merged-away number is never reused."""
    try:
        p = subprocess.run(["git", "log", "--all", "--name-only", "--format=", "--", "issues/"], cwd=root, capture_output=True, text=True)
    except OSError:
        return []
    return [int(n) for n in re.findall(r"ISS-(\d{4,})-", p.stdout)] if p.returncode == 0 else []


def _next_num(root, issues):
    return max([i["num"] for i in issues] + _history_nums(root) + [0]) + 1


def _note(iss, text):
    n = iss["sections"].get("Notes", "").strip("\n")
    iss["sections"]["Notes"] = (n + "\n" if n else "") + "- " + text


# ---- results ----
def results(root, from_json):
    if from_json:
        try:
            with open(from_json, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as ex:
            raise Usage("cannot read results from %s: %s" % (from_json, ex))
    else:
        script = os.path.join(root, "scripts", "acceptance.py")
        if not os.path.isfile(script):
            raise Usage("scripts/acceptance.py not found (the acceptance suite is AUTO-2); pass --from-json FILE with `acceptance.py run --json` output")
        p = subprocess.run([sys.executable, script, "run", "--json"], cwd=root, capture_output=True, text=True)
        try:
            data = json.loads(p.stdout)
        except ValueError:
            raise Usage("acceptance.py run --json printed no valid JSON: " + (p.stderr or p.stdout).strip()[-300:])
    if not isinstance(data, dict) or not isinstance(data.get("tests"), list):
        raise Usage('results need {"tests": [...]}')
    tests = {}
    for t in data["tests"]:
        if isinstance(t, dict) and isinstance(t.get("id"), str):
            tests[t["id"]] = {"id": t["id"], "status": str(t.get("status")), "message": str(t.get("message") or "")[:200],
                              "where": str(t.get("where") or "")}
    adm = data.get("admitted")
    admitted = set(adm) if isinstance(adm, list) else set(tests)
    return tests, admitted


def _failing(tests, admitted):
    return {i: t for i, t in tests.items() if t["status"] in FAILING and i in admitted}


# ---- commands ----
def _apply(issue, group):
    """Regenerate the failing-test lines of an issue from the tests now failing for it."""
    issue["tests"] = {t["id"]: t["message"] for t in group}
    issue["meta"]["updated"] = _today()


def cmd_find(root, tests, admitted):
    issues = load(root)
    fail = _failing(tests, admitted)
    by_id_open = {t: i for i in issues if i["state"] == "open" for t in i["tests"]}
    by_id_fixed = {t: i for i in issues if i["state"] == "fixed" for t in i["tests"]}
    assigned, rest = {}, []  # issue id -> tests
    reopened = set()
    for tid in sorted(fail):
        t = fail[tid]
        if tid in by_id_open:
            assigned.setdefault(by_id_open[tid]["id"], []).append(t)
        elif tid in by_id_fixed:  # regression
            iss = by_id_fixed[tid]
            reopened.add(iss["id"])
            assigned.setdefault(iss["id"], []).append(t)
        else:
            rest.append(t)
    groups = {}
    for t in rest:
        groups.setdefault(fingerprint(t), []).append(t)
    by_fp = {}
    for i in issues:
        if i["state"] == "open":
            by_fp.setdefault(i["meta"]["fp"], i)
    created, updated, reopen_list = [], [], []
    by_idx = {i["id"]: i for i in issues}
    new_issues = []
    for fp in sorted(groups, key=lambda f: groups[f][0]["id"]):
        g = groups[fp]
        if fp in by_fp:
            assigned.setdefault(by_fp[fp]["id"], []).extend(g)
            continue
        num = max([_next_num(root, issues)] + [i["num"] + 1 for i in new_issues])
        first = g[0]["id"]
        slug = _slugify("%s-%s" % (slug_of(first) or "issue", first.split("::")[-1].split(".")[-1]))
        etype, body = normalise(g[0]["message"])
        title = (etype + ": " + body if etype else body or g[0]["message"] or first)[:90]
        iss = {"num": num, "id": "ISS-%04d" % num, "slug": slug, "state": "open", "path": "", "title": title,
               "meta": {"status": "open", "prd": slug_of(first) or "-", "item": "-", "fp": fp, "opened": _today(),
                        "updated": _today(), "fixed": "-"},
               "sections": {"Suspected root cause": "_not analysed yet (finder)_", "Notes": ""},
               "tests": {t["id"]: t["message"] for t in g}}
        new_issues.append(iss)
        by_fp[fp] = iss
        created.append(iss["id"])
    for iid, g in sorted(assigned.items()):
        iss = by_idx[iid]
        before = dict(iss["tests"]), iss["state"]
        if iid in reopened:
            iss["state"] = "open"
            iss["meta"]["status"] = "open"
            iss["meta"]["fixed"] = "-"
            _note(iss, "Reopened %s at %s: regression, %s failing again." % (_today(), head_sha(root), ", ".join(sorted(t["id"] for t in g))))
            reopen_list.append(iid)
        _apply(iss, g)
        if (iss["tests"], iss["state"]) != before:
            save(root, iss)
            updated.append(iid)
    for iss in new_issues:
        save(root, iss)
    return {"created": created, "updated": [i for i in updated if i not in reopen_list], "reopened": reopen_list,
            "_failing": len(fail)}


def cmd_sync(root, tests, admitted):
    issues = load(root)
    fixed, reopened = [], []
    sha = head_sha(root)
    for iss in issues:
        if iss["state"] == "open" and iss["tests"] and all(tests.get(t, {}).get("status") == "pass" for t in iss["tests"]):
            iss["state"] = "fixed"
            iss["meta"]["status"] = "fixed"
            iss["meta"]["fixed"] = "%s %s" % (_today(), sha)
            iss["meta"]["updated"] = _today()
            save(root, iss)
            fixed.append(iss["id"])
        elif iss["state"] == "fixed":
            back = sorted(t for t in iss["tests"] if tests.get(t, {}).get("status") in FAILING and t in admitted)
            if back:
                iss["state"] = "open"
                iss["meta"]["status"] = "open"
                iss["meta"]["fixed"] = "-"
                iss["meta"]["updated"] = _today()
                for t in back:
                    iss["tests"][t] = tests[t]["message"]
                _note(iss, "Reopened %s at %s: regression, %s failing again." % (_today(), sha, ", ".join(back)))
                save(root, iss)
                reopened.append(iss["id"])
    return {"fixed": fixed, "reopened": reopened}


def _get(issues, ref):
    ref = ref.upper() if ref[:3].lower() == "iss" else ref
    m = re.match(r"^ISS-(\d+)", ref)
    if m:
        for i in issues:
            if i["num"] == int(m.group(1)):
                return i
    raise Usage("no such issue: " + ref)


def cmd_merge(root, a_ref, b_ref):
    issues = load(root)
    a, b = _get(issues, a_ref), _get(issues, b_ref)
    if a is b:
        raise Usage("cannot merge an issue into itself")
    if a["state"] != "open" or b["state"] != "open":
        raise Usage("both issues must be open")
    a["tests"].update(b["tests"])
    for k in ("Suspected root cause", "Notes"):
        extra = b["sections"].get(k, "").strip()
        if extra and not extra.startswith("_not analysed"):
            _note(a, "From %s (%s): %s" % (b["id"], k.lower(), extra.replace("\n", " ")))
    _note(a, "Merged %s (%s) on %s." % (b["id"], b["title"], _today()))
    a["meta"]["updated"] = _today()
    save(root, a)
    os.remove(b["path"])
    return {"merged": b["id"], "into": a["id"], "tests": len(a["tests"])}


def cmd_split(root, a_ref, ids):
    issues = load(root)
    a = _get(issues, a_ref)
    if a["state"] != "open":
        raise Usage("only an open issue can be split")
    missing = [t for t in ids if t not in a["tests"]]
    if missing:
        raise Usage("not in %s: %s" % (a["id"], ", ".join(missing)))
    if len(ids) >= len(a["tests"]):
        raise Usage("leave at least one test in %s" % a["id"])
    num = _next_num(root, issues)
    moved = {t: a["tests"].pop(t) for t in ids}
    first = sorted(moved)[0]
    new = {"num": num, "id": "ISS-%04d" % num, "slug": _slugify("%s-%s" % (slug_of(first) or "issue", first.split("::")[-1].split(".")[-1])),
           "state": "open", "path": "", "title": a["title"], "meta": dict(a["meta"], opened=_today(), updated=_today()),
           "sections": {"Suspected root cause": "_not analysed yet (finder)_", "Notes": "- Split from %s on %s." % (a["id"], _today())},
           "tests": moved}
    _note(a, "Split %s off to %s on %s." % (", ".join(sorted(moved)), new["id"], _today()))
    a["meta"]["updated"] = _today()
    save(root, a)
    save(root, new)
    return {"from": a["id"], "new": new["id"], "tests": sorted(moved)}


def _age_days(date_s, today=None):
    try:
        return max(0, ((today or datetime.date.today()) - datetime.date.fromisoformat(date_s[:10])).days)
    except ValueError:
        return None


def summary(issues):
    return [{"id": i["id"], "state": i["state"], "title": i["title"], "prd": i["meta"]["prd"], "item": i["meta"]["item"],
             "tests": sorted(i["tests"]), "opened": i["meta"]["opened"], "fixed": i["meta"]["fixed"],
             "path": os.path.relpath(i["path"])} for i in issues]


def git_trend(root):
    """Opened/fixed per day from git history of issues/: files added under issues/open (opened) and issues/fixed (fixed)."""
    try:
        p = subprocess.run(["git", "log", "--no-renames", "--name-status", "--format=%x1e%ad", "--date=short", "--", "issues/"],
                           cwd=root, capture_output=True, text=True)
    except OSError:
        return {}
    if p.returncode != 0:
        return {}
    days = {}
    for rec in p.stdout.split("\x1e")[1:]:
        lines = rec.strip().splitlines()
        if not lines:
            continue
        day = lines[0].strip()
        for ln in lines[1:]:
            parts = ln.split("\t")
            if len(parts) == 2 and parts[0] == "A" and FILE_RE.match(os.path.basename(parts[1])):
                kind = "opened" if parts[1].startswith("issues/open/") else "fixed" if parts[1].startswith("issues/fixed/") else None
                if kind:
                    days.setdefault(day, {"opened": 0, "fixed": 0})[kind] += 1
    return days


def status(root, today=None):
    issues = load(root)
    op = [i for i in issues if i["state"] == "open"]
    fx = [i for i in issues if i["state"] == "fixed"]
    by_prd = {}
    for i in op:
        by_prd[i["meta"]["prd"]] = by_prd.get(i["meta"]["prd"], 0) + 1
    ages = [(a, i["id"]) for i in op for a in [_age_days(i["meta"]["opened"], today)] if a is not None]
    oldest = max(ages) if ages else None
    trend = git_trend(root)
    return {"exists": os.path.isdir(os.path.join(root, "issues")) and bool(issues), "open": len(op), "fixed": len(fx),
            "by_prd": dict(sorted(by_prd.items())),
            "oldest_open": {"id": oldest[1], "days": oldest[0]} if oldest else None,
            "tests_per_issue": {i["id"]: len(i["tests"]) for i in op},
            "per_day": dict(sorted(trend.items())),
            "issues": [{"id": i["id"], "title": i["title"], "prd": i["meta"]["prd"], "tests": len(i["tests"]), "opened": i["meta"]["opened"],
                        "age": _age_days(i["meta"]["opened"], today)} for i in op]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=os.getcwd())
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("find", "sync"):
        s = sub.add_parser(n)
        s.add_argument("--from-json")
    s = sub.add_parser("merge")
    s.add_argument("a")
    s.add_argument("b")
    s = sub.add_parser("split")
    s.add_argument("a")
    s.add_argument("ids", nargs="+")
    for n in ("list", "status"):
        s = sub.add_parser(n)
        s.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    try:
        if a.cmd in ("find", "sync"):
            tests, admitted = results(root, a.from_json)
            r = (cmd_find if a.cmd == "find" else cmd_sync)(root, tests, admitted)
            parts = ["%s %s" % (k, ", ".join(v)) for k, v in r.items() if v and not k.startswith("_")]
            print("%s: %s%s" % (a.cmd, "; ".join(parts) or "nothing to do", " (%d failing admitted test(s))" % r["_failing"] if "_failing" in r else ""))
        elif a.cmd == "merge":
            print(json.dumps(cmd_merge(root, a.a, a.b)))
        elif a.cmd == "split":
            print(json.dumps(cmd_split(root, a.a, a.ids)))
        elif a.cmd == "list":
            rows = summary(load(root))
            if a.json:
                print(json.dumps(rows, indent=1))
            else:
                print("\n".join("%s %-5s %-24s %d test(s)  %s" % (r["id"], r["state"], r["prd"], len(r["tests"]), r["title"]) for r in rows) or EMPTY)
        else:
            st = status(root)
            if a.json:
                print(json.dumps(st, indent=1))
            else:
                print("%d open, %d fixed" % (st["open"], st["fixed"]) if st["exists"] else EMPTY)
    except Usage as ex:
        print("issues.py: %s" % ex, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
