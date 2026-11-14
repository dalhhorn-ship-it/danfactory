#!/usr/bin/env python3
"""Locked acceptance suite: map criteria to tests, admit tests, run them, ratchet a baseline. Stdlib only, Python 3.8+.
Design: docs/decisions/0007-merge-gate-and-acceptance-suite.md. Policy: docs/policies/merge-gate.md.

  python3 scripts/acceptance.py map <slug> [--strict]
  python3 scripts/acceptance.py admit <slug> [--reference-dir DIR]
  python3 scripts/acceptance.py second-reading <slug> [--model M]   # spends money: an agent writes a throwaway reference, then admit
  python3 scripts/acceptance.py run [--json] [--ids ID ...]
  python3 scripts/acceptance.py baseline [--allow-shrink]
  python3 scripts/acceptance.py status [--json]

Test id: `<slug>/<module>::<Class>.<method>` (or `<slug>/<module>::<function>`). Tests live in <acceptance.dir>/<slug>/.
Criterion links come from method names `test_c<N>_...` and are recorded in <dir>/manifest.json:
  {"prds": {slug: {"prd": path, "criteria": {"<n>": [ids]}}},
   "admitted": {id: {prd, criterion, date, sha, before: "fail", reference: "second-reading"|"reference"|null}},
   "questions": {slug: [text]}}
Baseline: metrics/acceptance-baseline.json {"passing": [ids], "date", "sha"}; only grows unless --allow-shrink.

Runners: default is stdlib unittest (run in a child process: per-test outcomes including subTest failures; an import or
setUpClass error is a collection error, an error inside a test body is a test error). A custom runner is the shell command
factory.json acceptance.command, which writes JUnit XML to $ACCEPTANCE_JUNIT ($ACCEPTANCE_REFERENCE = second-reading dir).
Exit codes: 0 ok, 1 a check failed (rejected tests, unmapped with --strict, failing admitted tests), 2 usage or runner error.
`run --json` prints one JSON object (the contract gate.py reads):
  {"tests": [{"id", "status": "pass|fail|error|skip", "message"?, "where"?}], "admitted": [ids],
   "collection_errors": [{"module", "error"}]}
`message` and `where` appear on fail/error tests of the default runner: the first line of the assertion or exception
message (max 200 chars) and the deepest traceback frame inside the project but outside the acceptance dir, as
"path:line:function" ("" if none). Custom (JUnit) runners give `message` (failure/error element) and `where` as "path:line" (first project frame in its text).
"""
import argparse
import ast
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from acceptance_exec import (HERE, SEVERITY, RunnerError, _child_unittest, _tail, fresh, parse_junit, tree_sandbox,  # noqa: E402,F401
                             write_json)

ROOT = os.path.dirname(HERE)
DEFAULTS = {"dir": "tests/acceptance", "command": "", "reference_command": ""}
BASELINE = "metrics/acceptance-baseline.json"
CRIT_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*\S)")
TEST_NAME_RE = re.compile(r"^test_c(\d+)(?:_|$)")


# ---------------------------------------------------------------- files and config

def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def config(root):
    f = read_json(os.path.join(root, "factory.json"), {}) or {}
    c = dict(DEFAULTS)
    c.update(f.get("acceptance") or {})
    return c


def manifest_path(root):
    return os.path.join(root, config(root)["dir"], "manifest.json")


def load_manifest(root):
    m = read_json(manifest_path(root), {})
    m = m if isinstance(m, dict) else {}
    for k in ("prds", "admitted", "questions"):
        if not isinstance(m.get(k), dict):
            m[k] = {}
    return m


def git_sha(root):
    try:
        p = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True)
        return p.stdout.strip() or None if p.returncode == 0 else None
    except OSError:
        return None


def today():
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------- criteria and static test scan

def criteria_of(root, slug):
    """{"1": text, ...} from the numbered list under `## Acceptance criteria` in docs/specs/<slug>.md ({} if none)."""
    try:
        with open(os.path.join(root, "docs", "specs", slug + ".md"), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return {}
    out, inside = {}, False
    for ln in lines:
        if re.match(r"^##\s+acceptance criteria\b", ln, re.I):
            inside = True
        elif re.match(r"^##\s", ln):
            inside = False
        elif inside:
            m = CRIT_RE.match(ln)
            if m and not ln.startswith((" ", "\t")):
                out[m.group(1)] = m.group(2)
    return out


def scan_tests(root, slug):
    """Test ids of a slug found statically (AST): [(id, criterion or None)], sorted. No test code runs."""
    d = os.path.join(root, config(root)["dir"], slug)
    res = []
    try:
        files = sorted(f for f in os.listdir(d) if f.startswith("test") and f.endswith(".py"))
    except OSError:
        return res
    for fn in files:
        mod = fn[:-3]
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
        except (OSError, SyntaxError, ValueError):
            continue  # a broken module is reported by `admit` as broken-test
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name.startswith("test"):
                        res.append(("%s/%s::%s.%s" % (slug, mod, node.name, sub.name), sub.name))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                res.append(("%s/%s::%s" % (slug, mod, node.name), node.name))
    out = []
    for tid, name in res:
        m = TEST_NAME_RE.match(name)
        out.append((tid, m.group(1) if m else None))
    return sorted(out)


def do_map(root, slug):
    """Update the manifest mapping for a slug from test names. Returns (unmapped_criteria, unmapped_tests, mapped_ids)."""
    man = load_manifest(root)
    crit = criteria_of(root, slug)
    found = scan_tests(root, slug)
    existing = set(i for i, _ in found)
    old = ((man["prds"].get(slug) or {}).get("criteria")) or {}
    mapping = {}
    for n, ids in old.items():  # keep explicit entries whose test still exists
        keep = [i for i in ids if i in existing]
        if keep:
            mapping[str(n)] = keep
    for tid, n in found:
        if n is not None and tid not in mapping.setdefault(n, []):
            mapping[n].append(tid)
    mapping = {n: sorted(ids) for n, ids in mapping.items() if ids}
    man["prds"][slug] = {"prd": "docs/specs/%s.md" % slug, "criteria": mapping}
    write_json(manifest_path(root), man)
    mapped = {i for ids in mapping.values() for i in ids}
    unmapped_c = sorted((n for n in crit if n not in mapping), key=int)
    unmapped_t = sorted(existing - mapped)
    return unmapped_c, unmapped_t, mapped


def unmapped_criteria(root, man=None):
    """{slug: [criterion numbers with no mapped test]} for PRDs in the manifest that have criteria."""
    man = man or load_manifest(root)
    res = {}
    for slug, rec in man["prds"].items():
        crit = criteria_of(root, slug)
        mapping = (rec or {}).get("criteria") or {}
        miss = sorted((n for n in crit if not mapping.get(n)), key=int)
        if miss:
            res[slug] = miss
    return res


def run_unittest(root, ref=None):
    cfg = config(root)
    accdir = os.path.join(root, cfg["dir"])
    if not os.path.isdir(accdir):
        return {"tests": [], "collection_errors": []}
    # the result file lives in a directory only this process created, outside the tree under test
    odir = tempfile.mkdtemp(prefix="acceptance-out-")
    out = os.path.join(odir, "result.json")
    ts = tree_sandbox(root)
    try:
        cmd = [sys.executable, os.path.abspath(__file__), "_unittest", "--root", root, "--dir", accdir, "--out", out]
        if ref:
            cmd += ["--ref", os.path.abspath(ref)]
        t0 = time.time()
        if ts:
            p = subprocess.run(ts.argv(cmd, False, [odir]), cwd=root, env=ts.env, capture_output=True, text=True, errors="replace")
        else:
            p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, errors="replace")
        res = read_json(out) if fresh(out, t0) else None
        if not isinstance(res, dict) or "tests" not in res:
            raise RunnerError("unittest runner failed (exit %d): %s" % (p.returncode, _tail(p.stdout + p.stderr)))
        return res
    finally:
        shutil.rmtree(odir, ignore_errors=True)
        if ts:
            ts.close()


def run_custom(root, command, ref=None):
    cfg = config(root)
    accdir = os.path.join(root, cfg["dir"])
    slugs = set(os.listdir(accdir)) if os.path.isdir(accdir) else set()
    jdir = tempfile.mkdtemp(prefix="acceptance-junit-")  # runner-owned, outside the tree under test, nothing in it before the run
    junit = os.path.join(jdir, "junit.xml")
    ts = tree_sandbox(root)
    env = dict(ts.env if ts else os.environ, ACCEPTANCE_JUNIT=junit)
    if ref:
        ref = os.path.abspath(ref)
        env["ACCEPTANCE_REFERENCE"] = ref
        env["PYTHONPATH"] = ref + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    try:
        t0 = time.time()
        if ts:
            p = subprocess.run(ts.argv(command, True, [jdir] + ([ref] if ref else [])), cwd=root, env=env, capture_output=True, text=True,
                               errors="replace")
        else:
            p = subprocess.run(command, cwd=root, shell=True, env=env, capture_output=True, text=True, errors="replace")
        if not os.path.isfile(junit) or not fresh(junit, t0):
            raise RunnerError("command wrote no fresh JUnit file at $ACCEPTANCE_JUNIT (exit %d): %s" % (p.returncode, _tail(p.stdout + p.stderr)))
        return parse_junit(junit, slugs, root, accdir)
    finally:
        shutil.rmtree(jdir, ignore_errors=True)
        if ts:
            ts.close()


def run_suite(root, ref=None, reference_command=False):
    """Result dict {"tests", "collection_errors"} from the configured runner."""
    cfg = config(root)
    if reference_command:
        return run_custom(root, cfg["reference_command"])
    if cfg["command"]:
        return run_custom(root, cfg["command"], ref)
    return run_unittest(root, ref)


# ---------------------------------------------------------------- commands

def status_map(res):
    return {t["id"]: t["status"] for t in res.get("tests") or []}


def cmd_map(a, root):
    if not os.path.isfile(os.path.join(root, "docs", "specs", a.slug + ".md")):
        print("no PRD at docs/specs/%s.md" % a.slug, file=sys.stderr)
        return 2
    uc, ut, mapped = do_map(root, a.slug)
    crit = criteria_of(root, a.slug)
    print("%s: %d criteria, %d tests mapped" % (a.slug, len(crit), len(mapped)))
    for n in uc:
        print("  unmapped criterion %s: %s" % (n, crit[n][:100]))
    for t in ut:
        print("  test mapped to no criterion: %s" % t)
    return 1 if (uc and a.strict) else 0


def cmd_admit(a, root):
    cfg = config(root)
    if not os.path.isfile(os.path.join(root, "docs", "specs", a.slug + ".md")):
        print("no PRD at docs/specs/%s.md" % a.slug, file=sys.stderr)
        return 2
    uc, ut, mapped = do_map(root, a.slug)
    man = load_manifest(root)
    crit_of = {i: n for n, ids in man["prds"][a.slug]["criteria"].items() for i in ids}
    cands = sorted(i for i in mapped if i not in man["admitted"])
    if not cands:
        print("nothing to admit for %s (%d already admitted)" % (a.slug, len(mapped)))
        return 0
    try:
        before = run_suite(root)
        ref_res, kind = None, None
        if a.reference_dir or cfg["reference_command"]:
            kind = "second-reading" if a.reference_dir else "reference"
            ref_res = run_suite(root, ref=a.reference_dir, reference_command=not a.reference_dir)
    except RunnerError as ex:
        print("runner error: %s" % ex, file=sys.stderr)
        return 2
    broken = {e["module"]: e["error"] for e in before.get("collection_errors") or []}
    bst = status_map(before)
    rst = status_map(ref_res) if ref_res is not None else None
    rejected, ok = [], []
    for tid in cands:
        mod = tid.split("::")[0]
        st = bst.get(tid)
        if mod in broken:
            rejected.append((tid, "broken-test", broken[mod]))
        elif st is None:
            rejected.append((tid, "broken-test", "test not found by the runner"))
        elif st == "pass":
            rejected.append((tid, "passes-without-behaviour", "passes before the build"))
        elif st == "skip":
            rejected.append((tid, "skipped", "test is skipped"))
        elif rst is not None and rst.get(tid) != "pass":
            rejected.append((tid, "fails-on-reference", "status on %s: %s; the test or the PRD is wrong, ask the user" % (kind, rst.get(tid) or "missing")))
        else:
            ok.append(tid)
    sha, day = git_sha(root), today()
    for tid in ok:
        man["admitted"][tid] = {"prd": a.slug, "criterion": crit_of.get(tid), "date": day, "sha": sha, "before": "fail", "reference": kind}
    write_json(manifest_path(root), man)
    print("admitted %d, rejected %d (of %d candidates)" % (len(ok), len(rejected), len(cands)))
    for tid, code, why in rejected:
        print("  REJECT %s [%s] %s" % (tid, code, why))
    if kind is None:
        print("warning: no second reading and no reference_command: admitted with reference null. "
              "At rigor L2+ a second reading is required: have a separate agent write a throwaway implementation from the PRD "
              "into a scratch dir, then run `admit %s --reference-dir DIR`." % a.slug)
    return 1 if rejected else 0


SKIP_DIRS = (".git", "tests", "test", "docs", "issues", "metrics", "scripts", ".claude", ".factory", ".github", "evals", "node_modules",
             "__pycache__", ".venv", "venv", "dist", "build")


def public_layout(root):
    """Source files of the project (paths, plus public def/class signatures of Python files): no bodies, no tests, no docs."""
    lines = []
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for f in sorted(files):
            rel = os.path.relpath(os.path.join(base, f), root).replace(os.sep, "/")
            if f.endswith((".md", ".json", ".lock", ".txt", ".yml", ".yaml", ".sh", ".toml", ".cfg", ".ini")) or f.startswith("."):
                continue
            lines.append(rel)
            if f.endswith(".py"):
                try:
                    with open(os.path.join(base, f), encoding="utf-8") as fh:
                        tree = ast.parse(fh.read())
                except (OSError, SyntaxError):
                    continue
                for n in tree.body:
                    if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not n.name.startswith("_"):
                        sig = "def %s(%s)" % (n.name, ", ".join(x.arg for x in n.args.args)) if isinstance(n, ast.FunctionDef) else "class " + n.name
                        lines.append("    " + sig)
    return "\n".join(lines) or "(no source files yet)"


def second_reading_prompt(slug, prd_text, layout):
    return ("You write a THROWAWAY reference implementation from a product requirements document alone. It is used once, to check that "
            "acceptance tests written by someone else can pass; it is deleted afterwards.\n\n"
            "Rules:\n- Read only what is in this directory (PRD.md and LAYOUT.txt). You cannot see the real implementation or the tests.\n"
            "- Write the implementation into THIS directory at the paths LAYOUT.txt lists (plus new files where the PRD needs them), as a "
            "complete package: it replaces the real one on the import path, so include every public function the layout names and every "
            "function or behaviour the PRD asks for. Python standard library only.\n- Implement exactly what the acceptance criteria say, "
            "nothing else. Do not write tests. No network.\n\nPRD (%s):\n%s\n\nLAYOUT.txt (public layout of the project, signatures only):\n%s\n"
            % (slug, prd_text, layout))


def cmd_second_reading(a, root):
    sys.path.insert(0, HERE)
    import runner
    import sandbox as S
    prd = os.path.join(root, "docs", "specs", a.slug + ".md")
    if not os.path.isfile(prd):
        print("no PRD at docs/specs/%s.md" % a.slug, file=sys.stderr)
        return 2
    problem = S.sandbox_problem()
    if problem:
        print("second-reading: " + problem, file=sys.stderr)
        return 2
    cfg = read_json(os.path.join(root, "factory.json"), {}) or {}
    model = a.model or (cfg.get("autonomy") or {}).get("model") or "sonnet"
    acfg = runner.settings(root)
    rows = runner.load_rows(root, acfg["staging_branch"])
    left = float(acfg["daily_budget_usd"]) - runner.spent(rows, runner.today())
    est = runner.estimate(rows, acfg)
    if left <= 0 or left < est:  # same daily cap as the fixer runner, checked before the paid call
        print("second-reading: daily budget: $%.2f spent today plus ~$%.2f for this call would pass the $%.2f cap"
              % (runner.spent(rows, runner.today()), est, float(acfg["daily_budget_usd"])), file=sys.stderr)
        return 3
    tmp = tempfile.mkdtemp(prefix="second-reading-")
    try:
        ref, home, scratch = (os.path.join(tmp, d) for d in ("ref", "home", "tmp"))
        for d in (ref, home, scratch):
            os.makedirs(d)
        with open(prd, encoding="utf-8", errors="replace") as fh:
            prd_text = fh.read()
        layout = public_layout(root)
        with open(os.path.join(ref, "PRD.md"), "w", encoding="utf-8") as fh:
            fh.write(prd_text)
        with open(os.path.join(ref, "LAYOUT.txt"), "w", encoding="utf-8") as fh:
            fh.write(layout + "\n")
        env = S.scrubbed_env(os.environ, home, scratch)
        t0 = time.time()
        try:
            out, rc = S.run_claude(second_reading_prompt(a.slug, prd_text, layout), model, int((cfg.get("autonomy") or {}).get("max_turns") or 40),
                                   ref, env, 900, max_budget=left)
        except FileNotFoundError:  # claude is not installed: nothing was spent
            out, rc = "", 127
        except Exception:  # noqa: BLE001 - the money may be spent: record an estimate below
            out, rc = "", 125
        tok, cost, _turns, has = S.usage_cost(S.parse_events(out))
        estimated = not has and cost <= 0 and rc != 127
        if estimated:
            cost = round(min(est, left), 5)
        for junk in ("PRD.md", "LAYOUT.txt"):
            if os.path.exists(os.path.join(ref, junk)):
                os.remove(os.path.join(ref, junk))
        row = dict(tok, ts=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), kind="second-reading", slug=a.slug,
                   model=model, cost_usd=cost, seconds=round(time.time() - t0, 1), run="second-reading-" + a.slug)
        if estimated:
            row["cost_estimated"] = True
        S.append_row(os.path.join(root, S.RUNNER_ROWS), row)
        print("second-reading: model %s, $%.2f, %.0fs%s" % (model, cost, time.time() - t0, "" if has else " (no result from the agent, claude exit %s)" % rc))
        if not has:
            return 2
        args = argparse.Namespace(slug=a.slug, reference_dir=ref)
        return cmd_admit(args, root)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def suite_report(root, ids=None):
    res = run_suite(root)
    man = load_manifest(root)
    tests = res.get("tests") or []
    if ids:
        tests = [t for t in tests if t["id"] in set(ids)]
    return {"tests": tests, "admitted": sorted(man["admitted"]), "collection_errors": res.get("collection_errors") or []}


def cmd_run(a, root):
    try:
        rep = suite_report(root, a.ids)
    except RunnerError as ex:
        if a.json:
            print(json.dumps({"error": str(ex), "tests": [], "admitted": sorted(load_manifest(root)["admitted"]), "collection_errors": []}))
        else:
            print("runner error: %s" % ex, file=sys.stderr)
        return 2
    st = {t["id"]: t["status"] for t in rep["tests"]}
    bad = [i for i in rep["admitted"] if st.get(i) != "pass" and (not a.ids or i in a.ids)]
    if a.json:
        print(json.dumps(rep))
    else:
        counts = {}
        for s in st.values():
            counts[s] = counts.get(s, 0) + 1
        print("acceptance: %d tests (%s), %d admitted" % (len(st), ", ".join("%d %s" % (n, s) for s, n in sorted(counts.items())) or "none", len(rep["admitted"])))
        for e in rep["collection_errors"]:
            print("  collection error in %s: %s" % (e["module"], e["error"]))
        for i in bad:
            print("  admitted but not passing: %s (%s)" % (i, st.get(i, "missing")))
    return 1 if bad or rep["collection_errors"] else 0


def cmd_baseline(a, root):
    try:
        rep = suite_report(root)
    except RunnerError as ex:
        print("runner error: %s" % ex, file=sys.stderr)
        return 2
    adm = set(rep["admitted"])
    now = {t["id"] for t in rep["tests"] if t["status"] == "pass" and t["id"] in adm}
    path = os.path.join(root, BASELINE)
    old = set((read_json(path, {}) or {}).get("passing") or [])
    new = now if a.allow_shrink else (old | now)
    lost = sorted(old - new)
    write_json(path, {"passing": sorted(new), "date": today(), "sha": git_sha(root)})
    print("baseline: %d passing (%d added, %d removed)%s" % (len(new), len(new - old), len(lost),
                                                              "" if a.allow_shrink or not (old - now) else "; %d old id(s) kept although not passing" % len(old - now)))
    return 0


def build_status(root, rep):
    man = load_manifest(root)
    st = {t["id"]: t["status"] for t in rep["tests"]}
    out = {}
    for slug, rec in sorted(man["prds"].items()):
        crit = criteria_of(root, slug)
        mapping = (rec or {}).get("criteria") or {}
        adm = sorted(i for i, r in man["admitted"].items() if (r or {}).get("prd") == slug)
        out[slug] = {"criteria": len(crit), "mapped": sum(1 for n in crit if mapping.get(n)),
                     "admitted_criteria": len({r.get("criterion") for i, r in man["admitted"].items()
                                               if (r or {}).get("prd") == slug and str(r.get("criterion")) in crit}),
                     "admitted": len(adm), "passing": sum(1 for i in adm if st.get(i) == "pass"),
                     "failing": sum(1 for i in adm if st.get(i) != "pass"),
                     "questions": list(man["questions"].get(slug) or [])}
    return out


def cmd_status(a, root):
    try:
        rep = suite_report(root)
    except RunnerError as ex:
        print("runner error: %s" % ex, file=sys.stderr)
        return 2
    s = build_status(root, rep)
    if a.json:
        print(json.dumps(s, indent=2))
        return 0
    if not s:
        print("no acceptance suite yet (no PRD in the manifest)")
    for slug, r in s.items():
        print("%s: %d criteria, %d mapped, %d with admitted test, %d admitted tests (%d passing, %d failing), %d open question(s)" % (
            slug, r["criteria"], r["mapped"], r["admitted_criteria"], r["admitted"], r["passing"], r["failing"], len(r["questions"])))
        for q in r["questions"]:
            print("  question: %s" % q)
    return 0


def main(argv=None, root=ROOT):
    ap = argparse.ArgumentParser(prog="acceptance.py", description="Locked acceptance suite (docs/policies/merge-gate.md)")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("map", help="map criteria to tests, report gaps")
    p.add_argument("slug")
    p.add_argument("--strict", action="store_true", help="exit 1 when a criterion has no test")
    p = sub.add_parser("admit", help="admit tests that fail before the build (and pass on a second reading)")
    p.add_argument("slug")
    p.add_argument("--reference-dir", metavar="DIR", help="throwaway implementation from the PRD alone, put first on the import path")
    p = sub.add_parser("second-reading", help="an agent writes a throwaway reference from the PRD alone, then admit --reference-dir")
    p.add_argument("slug")
    p.add_argument("--model")
    p = sub.add_parser("run", help="run the suite")
    p.add_argument("--json", action="store_true")
    p.add_argument("--ids", nargs="+", help="only report these test ids")
    p = sub.add_parser("baseline", help="record passing admitted tests (only grows)")
    p.add_argument("--allow-shrink", action="store_true")
    p = sub.add_parser("status", help="per PRD: criteria, mapped, admitted, passing, questions")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("_unittest")  # internal: the child process of the default runner
    p.add_argument("--root")
    p.add_argument("--dir")
    p.add_argument("--out")
    p.add_argument("--ref")
    try:
        a = ap.parse_args(argv)
    except SystemExit as ex:
        return 0 if ex.code in (0, None) else 2
    if a.cmd is None:
        ap.print_usage(sys.stderr)
        return 2
    if a.cmd == "_unittest":
        _child_unittest(a.root, a.dir, a.out, a.ref)
        return 0
    return {"map": cmd_map, "admit": cmd_admit, "second-reading": cmd_second_reading, "run": cmd_run, "baseline": cmd_baseline, "status": cmd_status}[a.cmd](a, root)


if __name__ == "__main__":
    sys.exit(main())
