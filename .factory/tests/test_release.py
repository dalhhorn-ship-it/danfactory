"""Release train (AUTO-5, ADR 0010 C5): scripts/release.py verify / report / smoke-failed and the Autonomy tab block.
Temp git repos; no model calls. The gate itself is replaced by a stub verdict (its own tests live in test_gate.py)."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import release  # noqa: E402
import runner  # noqa: E402
from obs import tab_autonomy  # noqa: E402


def sh(cwd, *a):
    p = subprocess.run(["git", "-c", "user.name=t0", "-c", "user.email=t0@t0", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
                       + list(a), cwd=cwd, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def verdict(ok=True):
    return {"verdict": "pass" if ok else "fail", "codes": [] if ok else ["acceptance-regressed"],
            "checks": [{"id": "tests", "status": "pass", "codes": [], "detail": ""},
                       {"id": "acceptance", "status": "pass" if ok else "fail", "codes": [] if ok else ["acceptance-regressed"], "detail": "x"}]}


class Repo:
    def __init__(self):
        self.root = tempfile.mkdtemp()
        sh(self.root, "init", "-q", "-b", "main")
        self.write("app.py", "A = 1\n")
        self.write(".gitignore", ".claude/worktrees/\n")
        sh(self.root, "add", "-A")
        sh(self.root, "commit", "-q", "-m", "base")
        sh(self.root, "branch", "staging")
        self.base = sh(self.root, "rev-parse", "HEAD")

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def fix(self, n, issue=True):
        """A runner-style fix merged into staging with --no-ff (checked out in a temp worktree)."""
        wt = tempfile.mkdtemp()
        shutil.rmtree(wt)
        sh(self.root, "worktree", "add", "-q", wt, "staging")
        with open(os.path.join(wt, "app%d.py" % n), "w") as fh:
            fh.write("X = %d\n" % n)
        sh(wt, "add", "-A")
        sh(wt, "commit", "-q", "-m", "fix %d" % n, "-m", "Refs: ISS-%04d" % n if issue else "no refs")
        sh(self.root, "worktree", "remove", "--force", wt)

    def run(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = release.main(list(args), root=self.root)
        return rc, out.getvalue(), err.getvalue()

    def rows(self):
        p = os.path.join(self.root, "metrics", "releases.jsonl")
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh.read().splitlines()]

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


@contextlib.contextmanager
def stub_gate(ok=True, seen=None):
    def fake(path, base):
        if seen is not None:
            seen.update(path=path, base=base, files=sorted(os.listdir(path)))
        return verdict(ok)
    with mock.patch.object(runner, "gate_verdict", fake), mock.patch.object(release.S, "tree_sandbox_problem", lambda *a, **k: None):
        yield


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.addCleanup(self.r.cleanup)

    def test_verify_pass_writes_row_and_never_touches_main(self):
        self.r.fix(1)
        self.r.fix(2)
        seen = {}
        with stub_gate(True, seen):
            rc, out, _ = self.r.run("verify")
        self.assertEqual(rc, 0, out)
        row = self.r.rows()[0]
        self.assertEqual((row["kind"], row["verdict"], row["staging"], row["prod"]), ("verify", "pass", "staging", "main"))
        self.assertEqual(len(row["commits"]), 2)
        self.assertEqual(row["issues"], ["ISS-0001", "ISS-0002"])
        self.assertEqual(seen["base"], "main", "gated against the production branch")
        self.assertIn("app2.py", seen["files"], "the fresh checkout holds the staging tip")
        self.assertEqual(sh(self.r.root, "rev-parse", "main"), self.r.base)
        self.assertEqual(sh(self.r.root, "branch", "--show-current"), "main")
        self.assertEqual(sh(self.r.root, "worktree", "list").count("\n"), 0, "verification checkout removed")

    def test_verify_fail_is_exit_1_with_codes_and_a_warning(self):
        self.r.fix(1)
        with stub_gate(False):
            rc, out, _ = self.r.run("verify")
        self.assertEqual(rc, 1)
        self.assertIn("acceptance-regressed", out)
        self.assertIn("Do NOT promote", out)
        self.assertEqual(self.r.rows()[0]["verdict"], "fail")

    def test_refuses_to_operate_on_the_production_branch(self):
        with stub_gate():
            rc, _, err = self.r.run("verify", "--branch", "main")
        self.assertEqual(rc, 2)
        self.assertIn("production branch", err)
        self.assertEqual(self.r.rows(), [])
        self.assertEqual(sh(self.r.root, "rev-parse", "main"), self.r.base)

    def test_refuses_when_staging_branch_configured_as_production(self):
        self.r.write("factory.json", json.dumps({"autonomy": {"staging_branch": "main"}}))
        with stub_gate():
            rc, _, err = self.r.run("verify")
        self.assertEqual(rc, 2, err)

    def test_refuses_without_the_tree_sandbox(self):
        with mock.patch.object(release.S, "tree_sandbox_problem", lambda *a, **k: "no bwrap"):
            rc, _, err = self.r.run("verify")
        self.assertEqual(rc, 2)
        self.assertIn("no bwrap", err)

    def test_cost_counts_only_since_the_last_promotion(self):
        self.r.fix(1)
        rows = [{"ts": "2000-01-01T00:00:00Z", "kind": "attempt", "cost_usd": 3.0}, {"ts": "2999-01-01T00:00:00Z", "kind": "attempt", "cost_usd": 0.4}]
        self.r.write("metrics/runner.jsonl", "".join(json.dumps(x) + "\n" for x in rows))
        with stub_gate():
            self.r.run("verify")
        self.assertAlmostEqual(self.r.rows()[-1]["cost_usd"], 3.4)  # never promoted: everything counts
        sh(self.r.root, "merge", "-q", "--no-ff", "-m", "promote", "staging")
        self.r.fix(2)
        with stub_gate():
            self.r.run("verify")
        self.assertAlmostEqual(self.r.rows()[-1]["cost_usd"], 0.4)


class NoPushTests(unittest.TestCase):
    def test_script_never_pushes_or_merges(self):
        with open(os.path.join(ROOT, "scripts", "release.py"), encoding="utf-8") as fh:
            code = "\n".join(ln for ln in fh.read().splitlines() if not ln.lstrip().startswith(("#", "\"\"\"")) and "git push" not in ln)
        for forbidden in ('"push"', '"merge"', '"checkout"', '"switch"', '"reset"'):
            self.assertNotIn(forbidden, code)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.addCleanup(self.r.cleanup)

    def test_report_empty_state(self):
        rc, out, _ = self.r.run("report")
        self.assertEqual(rc, 0)
        self.assertIn("No release verification yet", out)

    def test_report_in_plain_words_with_exact_commands_and_no_side_effects(self):
        self.r.fix(1)
        with stub_gate():
            self.r.run("verify")
        rc, out, _ = self.r.run("report")
        self.assertEqual(rc, 0)
        for s in ("PASSES the gate", "ISS-0001", "verdict: pass", "cost since the last promotion",
                  "git checkout main && git merge --no-ff staging && git push"):
            self.assertIn(s, out)
        self.assertEqual(sh(self.r.root, "rev-parse", "main"), self.r.base)

    def test_report_warns_when_staging_moved_after_verify(self):
        self.r.fix(1)
        with stub_gate():
            self.r.run("verify")
        self.r.fix(2)
        _, out, _ = self.r.run("report")
        self.assertIn("moved since this verification", out)


class SmokeFailedTests(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.addCleanup(self.r.cleanup)
        self.r.fix(1)
        sh(self.r.root, "merge", "-q", "--no-ff", "-m", "promote staging", "staging")
        self.merge = sh(self.r.root, "rev-parse", "HEAD")
        self.main_tip = self.merge

    def test_creates_revert_branch_and_files_an_issue_without_touching_main(self):
        rc, out, _ = self.r.run("smoke-failed", self.merge, "--reason", "GET / returned 500")
        self.assertEqual(rc, 0, out)
        b = "revert/" + self.merge[:7]
        self.assertEqual(sh(self.r.root, "rev-parse", "main"), self.main_tip, "main untouched")
        self.assertEqual(sh(self.r.root, "branch", "--show-current"), "main")
        self.assertTrue(os.path.exists(os.path.join(self.r.root, "app1.py")), "main's working tree untouched")
        tree = sh(self.r.root, "ls-tree", "--name-only", b)
        self.assertNotIn("app1.py", tree, "the merge is reverted on the branch")
        self.assertIn("Revert", sh(self.r.root, "log", "-1", "--format=%s", b))
        issues = os.listdir(os.path.join(self.r.root, "issues", "open"))
        self.assertEqual(len(issues), 1)
        text = open(os.path.join(self.r.root, "issues", "open", issues[0])).read()
        self.assertIn("GET / returned 500", text)
        self.assertEqual(sh(self.r.root, "worktree", "list").count("\n"), 0)
        self.assertEqual(self.r.rows()[-1]["branch"], b)
        self.assertIn("push it yourself", out)

    def test_second_call_refuses_existing_branch(self):
        self.r.run("smoke-failed", self.merge)
        rc, _, err = self.r.run("smoke-failed", self.merge)
        self.assertEqual(rc, 2)
        self.assertIn("already exists", err)

    def test_refuses_a_commit_not_on_main(self):
        self.r.fix(2)
        tip = sh(self.r.root, "rev-parse", "staging")
        rc, _, err = self.r.run("smoke-failed", tip)
        self.assertEqual(rc, 2)
        self.assertIn("not on main", err)

    def test_conflicting_revert_files_issue_and_leaves_no_branch(self):
        self.r.write("app1.py", "X = 99\n")  # a later change to the same file makes the revert conflict
        sh(self.r.root, "add", "-A")
        sh(self.r.root, "commit", "-q", "-m", "later edit")
        rc, _, err = self.r.run("smoke-failed", self.merge, "--reason", "boom")
        self.assertEqual(rc, 1)
        self.assertIn("conflicted", err)
        self.assertEqual(sh(self.r.root, "branch", "--list", "revert/*"), "")
        self.assertEqual(len(os.listdir(os.path.join(self.r.root, "issues", "open"))), 1)


class SummaryAndTabTests(unittest.TestCase):
    def setUp(self):
        self.r = Repo()
        self.addCleanup(self.r.cleanup)

    def test_empty_state(self):
        st = release.summary(self.r.root)
        self.assertFalse(st["exists"])
        self.assertIn("No release verification yet", release.human(st))
        self.assertIn("No release verification yet", tab_autonomy.render_release(st))
        self.assertEqual(tab_autonomy.release_line(st), "")

    def test_block_shows_lead_verdict_days_and_open_revert_branches(self):
        self.r.fix(1)
        with stub_gate(False):
            self.r.run("verify")
        sh(self.r.root, "branch", "revert/abc1234")
        sh(self.r.root, "checkout", "-q", "revert/abc1234")
        self.r.write("r.txt", "r")
        sh(self.r.root, "add", "r.txt")
        sh(self.r.root, "commit", "-q", "-m", "revert work")
        sh(self.r.root, "checkout", "-q", "main")
        st = release.summary(self.r.root)
        self.assertEqual((st["lead"], st["verdict"], st["fresh"], st["days_since_promotion"], st["reverts"]),
                         (1, "fail", True, None, ["revert/abc1234"]))
        h = tab_autonomy.render_release(st)
        for s in ("1 commit(s), not promoted", "fail [acceptance-regressed]", "never promoted", "revert/abc1234"):
            self.assertIn(s, h)
        self.assertIn("release:", tab_autonomy.line({"issues": {"exists": False}, "release": st}))
        self.assertIn("revert/abc1234", release.human(st))

    def test_days_since_promotion_and_collect_never_fails(self):
        self.r.fix(1)
        sh(self.r.root, "merge", "-q", "--no-ff", "-m", "promote", "staging")
        st = release.summary(self.r.root)
        self.assertEqual((st["days_since_promotion"], st["lead"]), (0, 0))
        d = tab_autonomy.collect(self.r.root, None)
        self.assertIn("release", d)
        self.assertEqual(tab_autonomy.collect_release("/nonexistent/x")["exists"], False)


if __name__ == "__main__":
    unittest.main()
