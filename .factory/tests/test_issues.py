"""Issue ledger and finder (AUTO-3, ADR 0008): fixture JSON in the acceptance.py contract, temp git projects."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import issues  # noqa: E402
from obs import tab_autonomy  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


def sh(root, *a):
    subprocess.run(a, cwd=root, check=True, capture_output=True, env=ENV)


def T(tid, status="fail", message="ImportError: cannot import name 'truncate' from 'textkit'", where="tests/acceptance/textkit/test_x.py:3:<module>"):
    return {"id": tid, "status": status, "message": message, "where": where}


def run(root, tests, admitted=None, cmd="find"):
    """Write fixture JSON and call the CLI; returns (exit code, stdout)."""
    f = os.path.join(root, "results.json")
    ids = [t["id"] for t in tests] if admitted is None else admitted
    with open(f, "w") as fh:
        json.dump({"tests": tests, "admitted": ids}, fh)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = issues.main(["--root", root, cmd, "--from-json", f])
    return rc, out.getvalue()


def project():
    d = tempfile.mkdtemp()
    sh(d, "git", "init", "-q")
    sh(d, "git", "commit", "-q", "--allow-empty", "-m", "init")
    return d


def files(root, state):
    p = os.path.join(root, "issues", state)
    return sorted(os.listdir(p)) if os.path.isdir(p) else []


def read(root, state, i=0):
    fn = files(root, state)[i]
    with open(os.path.join(root, "issues", state, fn)) as fh:
        return fh.read()


A, B, C = "textkit/test_a::A.test_one", "textkit/test_a::A.test_two", "textkit/test_b::B.test_three"


class Find(unittest.TestCase):
    def test_title_keeps_identifiers_and_fingerprint_is_stable(self):
        msg = "AttributeError: module 'semverlite' has no attribute 'parse'"
        self.assertEqual(issues.title_of(msg), msg)
        t = {"id": "a/m::C.t", "message": msg, "where": "x.py:3:f"}
        # pinned: fingerprints of existing issues must not change (TD-018)
        self.assertEqual(issues.fingerprint(t), "1429afad32e4")
        self.assertEqual(issues.fingerprint(dict(t, message="AssertionError: 3 != 4")), "9fc648db16fb")
        d = project()
        run(d, [T(A, message=msg)])
        self.assertIn("module 'semverlite' has no attribute 'parse'", read(d, "open").splitlines()[0])

    def test_same_error_and_frame_is_one_issue(self):
        d = project()
        run(d, [T(A), T(B, message="ImportError: cannot import name 'wrap' from 'textkit'")])
        self.assertEqual(len(files(d, "open")), 1)
        txt = read(d, "open")
        self.assertIn("Status: open · PRD: textkit", txt)
        self.assertIn("`%s`" % A, txt)
        self.assertIn("`%s`" % B, txt)
        self.assertIn("acceptance.py run --ids %s %s" % (A, B), txt)
        self.assertIn("## Suspected root cause", txt)

    def test_different_frames_or_errors_are_separate(self):
        d = project()
        run(d, [T(A), T(C, where="tests/acceptance/textkit/test_b.py:9:<module>"),
                T("textkit/test_c::C.test_x", message="AssertionError: 5 != 6", where="x.py:4:test_x")])
        self.assertEqual(len(files(d, "open")), 3)

    def test_numbers_and_literals_masked_line_numbers_ignored(self):
        t1 = T(A, message="AssertionError: 3 != 4", where="a.py:10:f")
        t2 = T(B, message="AssertionError: 30 != 41", where="a.py:99:f")
        self.assertEqual(issues.fingerprint(t1), issues.fingerprint(t2))
        self.assertNotEqual(issues.fingerprint(t1), issues.fingerprint(dict(t2, where="a.py:99:g")))

    def test_idempotent(self):
        d = project()
        run(d, [T(A), T(B)])
        before = (files(d, "open"), read(d, "open"))
        rc, out = run(d, [T(A), T(B)])
        self.assertEqual(rc, 0)
        self.assertEqual((files(d, "open"), read(d, "open")), before)
        self.assertIn("nothing to do", out)

    def test_only_admitted_failures(self):
        d = project()
        run(d, [T(A), T(B), T(C, status="pass"), T("x/y::Z.t", status="skip")], admitted=[A])
        self.assertEqual(len(files(d, "open")), 1)
        self.assertNotIn(B, read(d, "open"))

    def test_update_keeps_human_text_and_regenerates_tests(self):
        d = project()
        run(d, [T(A)])
        p = os.path.join(d, "issues", "open", files(d, "open")[0])
        txt = open(p).read().replace("_not analysed yet (finder)_", "Cause: tests/x.py:3 imports a missing symbol.") + "- human note\n"
        open(p, "w").write(txt)
        run(d, [T(A, message="ImportError: cannot import name 'other' from 'textkit'"), T(B)])
        new = read(d, "open")
        self.assertEqual(len(files(d, "open")), 1)
        self.assertIn("Cause: tests/x.py:3 imports a missing symbol.", new)
        self.assertIn("- human note", new)
        self.assertIn("'other'", new)
        self.assertIn("`%s`" % B, new)

    def test_missing_script_without_json_fails_clearly(self):
        d = project()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = issues.main(["--root", d, "find"])
        self.assertEqual(rc, 2)
        self.assertIn("acceptance.py not found", err.getvalue())

    def test_numbering_is_sequential_across_folders(self):
        d = project()
        run(d, [T(A)])
        run(d, [T(A, status="pass")], cmd="sync")
        run(d, [T(A, status="pass"), T(C, where="b.py:1:g")])
        self.assertEqual(files(d, "fixed")[0][:8], "ISS-0001")
        self.assertEqual(files(d, "open")[0][:8], "ISS-0002")

    def test_pilot_all_tests_of_a_prd_fail_with_one_missing_function(self):
        """Spike idea: the PRD's feature does not exist, every test dies on the same ImportError."""
        d = project()
        tests = [T("textkit/test_truncate::Truncate.test_%d" % i, message="ImportError: cannot import name 'truncate' from 'textkit' (/tmp/p%d/textkit/__init__.py)" % i,
                   where="tests/acceptance/textkit/test_truncate.py:1:<module>") for i in range(8)]
        run(d, tests)
        self.assertEqual(len(files(d, "open")), 1)
        self.assertEqual(read(d, "open").count("- `textkit/"), 8)


class Sync(unittest.TestCase):
    def test_fixed_moves_with_date_and_sha_then_reopens_on_regression(self):
        d = project()
        run(d, [T(A), T(B)])
        run(d, [T(A, status="pass"), T(B)], cmd="sync")
        self.assertEqual(len(files(d, "open")), 1)  # one test still failing
        rc, out = run(d, [T(A, status="pass"), T(B, status="pass")], cmd="sync")
        self.assertEqual((files(d, "open"), len(files(d, "fixed"))), ([], 1))
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=d, capture_output=True, text=True).stdout.strip()
        txt = read(d, "fixed")
        self.assertIn("Status: fixed", txt)
        self.assertRegex(txt, r"Fixed: \d{4}-\d\d-\d\d %s" % sha)
        run(d, [T(A), T(B, status="pass")], cmd="sync")  # regression
        self.assertEqual((len(files(d, "open")), files(d, "fixed")), (1, []))
        txt = read(d, "open")
        self.assertIn("Status: open", txt)
        self.assertIn("Fixed: -", txt)
        self.assertIn("Reopened", txt)

    def test_find_reopens_instead_of_duplicating(self):
        d = project()
        run(d, [T(A)])
        run(d, [T(A, status="pass")], cmd="sync")
        run(d, [T(A)])
        self.assertEqual((len(files(d, "open")), files(d, "fixed")), (1, []))

    def test_missing_test_does_not_count_as_fixed(self):
        d = project()
        run(d, [T(A)])
        run(d, [T(C, status="pass")], cmd="sync")
        self.assertEqual(len(files(d, "open")), 1)


class MergeSplit(unittest.TestCase):
    def test_merge_and_split(self):
        d = project()
        run(d, [T(A), T(C, where="b.py:1:g")])
        self.assertEqual(len(files(d, "open")), 2)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(issues.main(["--root", d, "merge", "ISS-0001", "ISS-0002"]), 0)
        self.assertEqual(len(files(d, "open")), 1)
        self.assertIn("`%s`" % C, read(d, "open"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(issues.main(["--root", d, "split", "ISS-0001", C]), 0)
        self.assertEqual(len(files(d, "open")), 2)
        # finder run afterwards keeps the split (assignment is by test id first)
        run(d, [T(A), T(C, where="b.py:1:g")])
        self.assertEqual(len(files(d, "open")), 2)
        self.assertNotIn("- `%s`" % C, read(d, "open", 0))

    def test_bad_arguments(self):
        d = project()
        run(d, [T(A)])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(issues.main(["--root", d, "merge", "ISS-0001", "ISS-0009"]), 2)
            self.assertEqual(issues.main(["--root", d, "split", "ISS-0001", A]), 2)


class Status(unittest.TestCase):
    def test_counts_and_trend_from_git(self):
        d = project()
        self.assertFalse(issues.status(d)["exists"])
        run(d, [T(A), T(C, where="b.py:1:g")])
        sh(d, "git", "add", "-A")
        sh(d, "git", "commit", "-q", "-m", "ledger")
        run(d, [T(A, status="pass"), T(C, where="b.py:1:g")], cmd="sync")
        sh(d, "git", "add", "-A")
        sh(d, "git", "commit", "-q", "-m", "fix one")
        st = issues.status(d)
        self.assertEqual((st["open"], st["fixed"]), (1, 1))
        self.assertEqual(st["by_prd"], {"textkit": 1})
        self.assertEqual(st["tests_per_issue"], {"ISS-0002": 1})
        self.assertEqual(st["oldest_open"]["id"], "ISS-0002")
        day = list(st["per_day"].values())
        self.assertEqual(sum(x["opened"] for x in day), 2)
        self.assertEqual(sum(x["fixed"] for x in day), 1)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            issues.main(["--root", d, "status", "--json"])
        self.assertEqual(json.loads(out.getvalue())["open"], 1)


class Dashboard(unittest.TestCase):
    def test_empty_state(self):
        d = project()
        data = tab_autonomy.collect(d, {})
        self.assertIn("No issue ledger yet: the finder files issues from failing acceptance tests (ADR 0008).", tab_autonomy.render(data))
        self.assertEqual(tab_autonomy.line(data), "no issue ledger yet")

    def test_render_escapes_and_shows_blocks(self):
        d = project()
        run(d, [T(A, message="AssertionError: <script>alert(1)</script>", where="a.py:1:f")])
        sh(d, "git", "add", "-A")
        sh(d, "git", "commit", "-q", "-m", "ledger")
        data = tab_autonomy.collect(d, {})
        html = tab_autonomy.render(data)
        self.assertNotIn("<script>", html)
        for s in ("Open by PRD", "textkit", "ISS-0001", "Oldest open issue", "Opened (dark)", "<svg"):
            self.assertIn(s, html)
        self.assertIn("1 open, 0 fixed", tab_autonomy.line(data))

    def test_dashboard_registers_the_tab(self):
        import dashboard
        self.assertIn("autonomy", [k for k, _l, _m in dashboard.TABS])


if __name__ == "__main__":
    unittest.main()
