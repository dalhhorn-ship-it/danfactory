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
import subprocess
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULTS = {"dir": "tests/acceptance", "command": "", "reference_command": ""}
BASELINE = "metrics/acceptance-baseline.json"
CRIT_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*\S)")
TEST_NAME_RE = re.compile(r"^test_c(\d+)(?:_|$)")
SEVERITY = {"pass": 0, "skip": 1, "fail": 2, "error": 3}


class RunnerError(Exception):
    pass


# ---------------------------------------------------------------- files and config

def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")


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


# ---------------------------------------------------------------- default runner: unittest in a child process

def _child_unittest(root, accdir, out, ref):
    """Runs inside the child process: import every test module under accdir/<slug>/, run, write outcomes to `out`."""
    import importlib.util
    import io
    import unittest
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != HERE]
    sys.path.insert(0, root)
    if ref:
        sys.path.insert(0, ref)
    tests, errors, info = {}, [], {}
    state = {"mod": ""}
    acc_abs, root_abs = os.path.abspath(accdir) + os.sep, os.path.abspath(root) + os.sep

    def describe(err):
        """(message, where): first line of the exception message (max 200) and the deepest traceback frame inside the
        project but outside the acceptance dir, as path:line:function ('' if none)."""
        msg = (str(err[1]).strip().splitlines() or [""])[0] or err[0].__name__
        where = ""
        for fs in traceback.extract_tb(err[2]):
            f = os.path.abspath(fs.filename)
            if f.startswith(root_abs) and not f.startswith(acc_abs):
                where = "%s:%d:%s" % (os.path.relpath(f, root_abs).replace(os.sep, "/"), fs.lineno, fs.name)
        return msg[:200], where

    def put(tid, status, err=None):
        if tid not in tests or SEVERITY[status] > SEVERITY[tests[tid]]:
            tests[tid] = status
            if err is not None:
                info[tid] = describe(err)

    def tid_of(t):
        return "%s::%s.%s" % (state["mod"], type(t).__name__, t._testMethodName)

    class Result(unittest.TestResult):
        def addSuccess(self, t):
            put(tid_of(t), "pass")

        def addSkip(self, t, reason):
            put(tid_of(t), "skip")

        def addExpectedFailure(self, t, err):
            put(tid_of(t), "pass")

        def addUnexpectedSuccess(self, t):
            put(tid_of(t), "fail")

        def addFailure(self, t, err):
            put(tid_of(t), "fail", err)

        def addError(self, t, err):
            if isinstance(t, unittest.TestCase):
                put(tid_of(t), "error", err)
            else:  # setUpClass / setUpModule holder: nothing ran
                errors.append({"module": state["mod"], "error": "".join(traceback.format_exception_only(err[0], err[1])).strip()[-300:]})

        def addSubTest(self, t, sub, err):
            if err is not None:
                put(tid_of(t), "fail" if issubclass(err[0], t.failureException) else "error", err)

    loader = unittest.TestLoader()
    for slug in sorted(os.listdir(accdir)):
        sdir = os.path.join(accdir, slug)
        if not os.path.isdir(sdir) or slug.startswith((".", "_")):
            continue
        sys.path.insert(1 + (1 if ref else 0), sdir)  # helpers next to the tests, after ref and root
        for fn in sorted(f for f in os.listdir(sdir) if f.startswith("test") and f.endswith(".py")):
            state["mod"] = "%s/%s" % (slug, fn[:-3])
            try:
                spec = importlib.util.spec_from_file_location("acc_%s_%s" % (re.sub(r"\W", "_", slug), fn[:-3]), os.path.join(sdir, fn))
                mod = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = mod
                spec.loader.exec_module(mod)
            except BaseException as ex:  # noqa: BLE001 - import errors and SystemExit are collection errors
                errors.append({"module": state["mod"], "error": "".join(traceback.format_exception_only(type(ex), ex)).strip()[-300:]})
                continue
            suite = loader.loadTestsFromModule(mod)
            keep = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = io.StringIO()
            try:
                suite.run(Result())
            finally:
                sys.stdout, sys.stderr = keep
    rows = []
    for i, st in sorted(tests.items()):
        row = {"id": i, "status": st}
        if i in info:
            row["message"], row["where"] = info[i]
        rows.append(row)
    write_json(out, {"tests": rows, "collection_errors": errors})


def run_unittest(root, ref=None):
    cfg = config(root)
    accdir = os.path.join(root, cfg["dir"])
    if not os.path.isdir(accdir):
        return {"tests": [], "collection_errors": []}
    fd, out = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        cmd = [sys.executable, os.path.abspath(__file__), "_unittest", "--root", root, "--dir", accdir, "--out", out]
        if ref:
            cmd += ["--ref", os.path.abspath(ref)]
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, errors="replace")
        res = read_json(out)
        if not isinstance(res, dict) or "tests" not in res:
            raise RunnerError("unittest runner failed (exit %d): %s" % (p.returncode, _tail(p.stdout + p.stderr)))
        return res
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass


# ---------------------------------------------------------------- custom runner: JUnit XML

def _tail(text, n=4):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return " | ".join(lines[-n:])[-300:]


_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rb", ".java", ".kt", ".rs", ".php", ".cs")
_LOC_RES = (
    re.compile(r'File "([^"]+)", line (\d+)'),                      # python traceback
    re.compile(r"\(?((?:[A-Za-z]:)?[^\s():'\"<>]+\.\w{1,5}):(\d+)(?::\d+)?\)?"),  # pytest, node stack, go
)
_NOISE = ("node_modules", "site-packages", "dist-packages", "<frozen", "/usr/lib/", "/usr/local/lib/", "/lib/python", "/_pytest/", "/pluggy/")


def _pathlike(s):
    return bool(s) and re.match(r"^[\w@.+~/\\:-]+$", s) is not None and ("/" in s or "\\" in s or s.endswith(_EXTS))


def _split_slug(path, slugs):
    """(slug, segments after it) for a path or dotted name containing a slug folder, else None."""
    sep = "/" if ("/" in path or "\\" in path or path.endswith(_EXTS)) else "."
    parts = [p for p in path.replace("\\", "/").split(sep) if p and p != "."]
    for i, p in enumerate(parts):
        if p in slugs:
            return p, parts[i + 1:]
    return None


def _junit_id(cls, name, file, slugs):
    """`<slug>/<module>::<Class>.<name>` from the classname/name (pytest, vitest, jest-junit, go-junit-report) and the file
    attribute or path-like classname when present; falls back to `<classname>::<name>` when no slug folder is in it."""
    hit = _split_slug(cls, slugs) if cls and not _pathlike(cls) else None
    if hit:  # dotted classname (pytest): module then class
        slug, rest = hit
        return "%s/%s::%s" % (slug, rest[0] if rest else slug, ".".join(rest[1:] + [name]))
    for src in (file, cls):
        hit = _split_slug(src, slugs) if _pathlike(src or "") else None
        if hit:
            slug, rest = hit
            if rest and rest[-1].endswith(_EXTS):  # test file path (vitest, jest, pytest xunit1)
                rest[-1] = os.path.splitext(rest[-1])[0]
            return "%s/%s::%s" % (slug, "/".join(rest) or slug, name)  # go: package folder is the module
    return "%s::%s" % (cls, name)


def _module_of(name, slugs):
    """`<slug>/<module>` when `name` is a module or file path inside the slug folders, else None."""
    if not name or not re.match(r"^[\w@.+~/\\:-]+$", name) or not ("." in name or "/" in name or "\\" in name):
        return None
    hit = _split_slug(name.replace("\\", "/"), slugs)
    if not hit or not hit[1]:
        return None
    rest = hit[1]
    if rest[-1].endswith(_EXTS):
        rest = rest[:-1] + [os.path.splitext(rest[-1])[0]]
        return "%s/%s" % (hit[0], "/".join(rest))
    return "%s/%s" % (hit[0], rest[0])


def _where(text, root, accdir):
    """First frame in the project (relative path, outside the acceptance dir) found in failure text, as path:line."""
    root_abs = os.path.abspath(root) if root else ""
    acc_abs = os.path.abspath(accdir) + os.sep if accdir else None
    for line in (text or "").splitlines():
        for rx in _LOC_RES:
            for m in rx.finditer(line):
                f, n = m.group(1).replace("\\", "/"), m.group(2)
                if any(x in f for x in _NOISE):
                    continue
                if os.path.isabs(f):
                    a = os.path.normpath(f)
                    if not root_abs or not (a + os.sep).startswith(root_abs + os.sep):
                        continue
                    f = os.path.relpath(a, root_abs).replace(os.sep, "/")
                elif f.startswith("../") or "://" in f:
                    continue
                f = f[2:] if f.startswith("./") else f
                if acc_abs and (os.path.abspath(os.path.join(root_abs, f)) + os.sep).startswith(acc_abs):
                    continue
                return "%s:%s" % (f, n)
    return ""


def _first_line(el):
    msg = (el.get("message") or "").strip() or (el.text or "").strip()
    return ((msg.splitlines() or [""])[0] or el.get("type") or "")[:200]


def parse_junit(path, slugs, root=None, accdir=None):
    """{"tests": [...], "collection_errors": [{"module", "error"}]} from a JUnit XML file (pytest --junitxml, vitest/jest
    junit reporters, go-junit-report, nested <testsuites>). A testcase id is `<slug>/<module>::<Class>.<name>`, anchored on
    the slug folder in the `file` attribute, a path-like classname (vitest, jest) or a dotted classname (pytest); a Go
    package classname gives the package folder as module. <failure> is fail, <error> is error, <skipped> is skip; the first
    line of the element's message and the first project frame in its text (`where`, path:line) are kept. Collection errors
    (reported as `broken-test` by admit) are: a <testsuite>-level <error>, and an errored testcase with an empty classname
    or named like a module or file in a slug folder (pytest import errors, jest "Test suite failed to run")."""
    import xml.etree.ElementTree as ET
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as ex:
        raise RunnerError("cannot read JUnit XML: %s" % ex)
    tests, errors, info = {}, [], {}

    def collection(module, err):
        if module not in {e["module"] for e in errors}:
            errors.append({"module": module, "error": err[:300]})

    def walk(el, suite_hint):
        for ch in el:
            if ch.tag == "testsuite":
                hint = ch.get("file") or (ch.get("name") if _module_of(ch.get("name") or "", slugs) else None) or suite_hint
                for e in ch.findall("error"):
                    collection(_module_of(hint or "", slugs) or ch.get("name") or "", _first_line(e))
                walk(ch, hint)
            elif ch.tag == "testsuites":
                walk(ch, suite_hint)
            elif ch.tag == "testcase":
                case(ch, suite_hint)

    def case(tc, suite_hint):
        cls, name = tc.get("classname") or "", tc.get("name") or ""
        fail, err, skip = tc.find("failure"), tc.find("error"), tc.find("skipped")
        st = "error" if err is not None else "fail" if fail is not None else "skip" if skip is not None else "pass"
        if st == "error":
            mod = _module_of(name, slugs)
            if not cls or mod:
                collection(mod or name, _first_line(err))
                return
        if not cls and not tc.get("file"):
            return
        tid = _junit_id(cls, name, tc.get("file") or (suite_hint if not _pathlike(cls) else None), slugs)
        if tid not in tests or SEVERITY[st] > SEVERITY[tests[tid]]:
            tests[tid] = st
            info.pop(tid, None)
            el = fail if st == "fail" else err if st == "error" else None
            if el is not None:
                info[tid] = (_first_line(el), _where("\n".join(filter(None, (el.get("message"), el.text))), root, accdir))

    top = tree.getroot()
    if top.tag == "testcase":
        case(top, None)
    else:
        holder = ET.Element("holder")
        holder.append(top)
        walk(holder, None)
    rows = []
    for i, s in sorted(tests.items()):
        row = {"id": i, "status": s}
        if i in info:
            row["message"], row["where"] = info[i]
        rows.append(row)
    return {"tests": rows, "collection_errors": errors}


def run_custom(root, command, ref=None):
    cfg = config(root)
    accdir = os.path.join(root, cfg["dir"])
    slugs = set(os.listdir(accdir)) if os.path.isdir(accdir) else set()
    fd, junit = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    os.unlink(junit)
    env = dict(os.environ, ACCEPTANCE_JUNIT=junit)
    if ref:
        ref = os.path.abspath(ref)
        env["ACCEPTANCE_REFERENCE"] = ref
        env["PYTHONPATH"] = ref + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    try:
        p = subprocess.run(command, cwd=root, shell=True, env=env, capture_output=True, text=True, errors="replace")
        if not os.path.isfile(junit):
            raise RunnerError("command wrote no JUnit file at $ACCEPTANCE_JUNIT (exit %d): %s" % (p.returncode, _tail(p.stdout + p.stderr)))
        return parse_junit(junit, slugs, root, accdir)
    finally:
        try:
            os.unlink(junit)
        except OSError:
            pass


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
    import shutil
    import tempfile
    import time
    sys.path.insert(0, HERE)
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
        out, rc = S.run_claude(second_reading_prompt(a.slug, prd_text, layout), model, int((cfg.get("autonomy") or {}).get("max_turns") or 40),
                               ref, env, 900)
        tok, cost, _turns, has = S.usage_cost(S.parse_events(out))
        for junk in ("PRD.md", "LAYOUT.txt"):
            if os.path.exists(os.path.join(ref, junk)):
                os.remove(os.path.join(ref, junk))
        row = dict(tok, ts=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), kind="second-reading", slug=a.slug,
                   model=model, cost_usd=cost, seconds=round(time.time() - t0, 1), run="second-reading-" + a.slug)
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
