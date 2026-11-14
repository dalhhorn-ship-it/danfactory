"""Acceptance suite execution helpers: the unittest child process, sandbox hook, and JUnit XML parsing.
Split from scripts/acceptance.py (SIZE-3); acceptance re-exports every name here. Self-contained (stdlib only) so the
child process started as `acceptance.py _unittest` can use it without importing the rest. Not importing `config`
on purpose: tests patch `acceptance.config`, and run_custom/run_unittest/run_suite (which call it) stay in acceptance.py."""
import json
import os
import re
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SEVERITY = {"pass": 0, "skip": 1, "fail": 2, "error": 3}


class RunnerError(Exception):
    pass


def write_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")


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


def tree_sandbox(root):
    """A sandbox.TreeSandbox for the code under test when ACCEPTANCE_SANDBOX=1 (the fixer runner sets it), else None.
    The tests then run in bubblewrap without network and with a scrubbed environment; no bwrap means a runner error."""
    if os.environ.get("ACCEPTANCE_SANDBOX") != "1":
        return None
    sys.path.insert(0, HERE)
    import sandbox
    try:
        return sandbox.TreeSandbox(root)
    except sandbox.SandboxUnavailable as ex:
        raise RunnerError(str(ex))


def fresh(path, since):
    """True when `path` is a file written at or after `since` (a result file left over from before the run is not trusted)."""
    try:
        return os.stat(path).st_mtime >= since - 1.0
    except OSError:
        return False


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
