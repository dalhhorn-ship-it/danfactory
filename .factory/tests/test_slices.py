"""Parallel build helper (scripts/slices.py, ADR 0012): ownership map parsing, ownership check, serial gated landing in
temp git repos with a fake gate command. No network, no model."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import slices  # noqa: E402

MAP = """# Design

| Slice | Owns | Wave | Depends on | Criteria |
|---|---|---|---|---|
| A approval | `.claude/hooks/_mission.py`, `docs/missions/` | 1 | - | 1-4 |
| B loop | `src/b/**`, `b.txt` | 1 | A (lands after) | 5 |
| C report | `scripts/*.py` | 1 | A | 8 |
| D later | `d.txt` | 2 | A, B | - |
"""


os.environ["SLICES_TEST_GATE"] = "1"


class Repo:
    def __init__(self):
        self.root = tempfile.mkdtemp()
        self.g("init", "-q", "-b", "main")
        self.write("README.md", "hi\n")
        self.write("design.md", MAP)
        self.write("factory.json", "{}")
        self.g("add", "-A")
        self.g("commit", "-qm", "base")

    def g(self, *a):
        p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *a],
                           cwd=self.root, capture_output=True, text=True)
        return p.stdout.strip() + p.stderr.strip()

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(text)

    def branch(self, name, files, frm="main"):
        self.g("checkout", "-q", "-b", name, frm)
        for rel, text in files.items():
            self.write(rel, text)
        self.g("add", "-A")
        self.g("commit", "-qm", name)
        self.g("checkout", "-q", "main")

    def run(self, *args, protected_ok=True):
        if protected_ok and args[:1] == ("land",):
            args = args + ("--allow-protected",)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = slices.main(list(args), root=self.root)
        return rc, buf.getvalue()


class T(unittest.TestCase):
    def repo(self):
        r = Repo()
        self.addCleanup(shutil.rmtree, r.root, True)
        return r

    # ---- map and ownership
    def test_parse_map(self):
        s = slices.parse_map(MAP)
        self.assertEqual([x["id"] for x in s], ["A", "B", "C", "D"])
        self.assertEqual(s[0]["owns"], [".claude/hooks/_mission.py", "docs/missions/"])
        self.assertEqual((s[1]["wave"], s[1]["depends"]), (1, ["A"]))
        self.assertEqual(s[3]["depends"], ["A", "B"])
        self.assertEqual(s[0]["depends"], [])
        self.assertEqual(slices.find_slice(s, "b")["id"], "B")
        self.assertEqual(slices.parse_map("no table here"), [])

    def test_owns_globs(self):
        s = {x["id"]: x for x in slices.parse_map(MAP)}
        self.assertTrue(slices.owns(s["A"], ".claude/hooks/_mission.py"))
        self.assertTrue(slices.owns(s["A"], "docs/missions/x/y.md"))  # trailing slash = directory
        self.assertTrue(slices.owns(s["B"], "src/b/deep/er.py"))
        self.assertFalse(slices.owns(s["B"], "src/c/x.py"))
        self.assertTrue(slices.owns(s["C"], "scripts/a.py"))
        self.assertFalse(slices.owns(s["C"], "scripts/obs/a.py"))  # * does not cross a directory
        self.assertEqual(slices.outside(s["C"], ["scripts/a.py", "docs/INDEX.md", "x.py"]), ["x.py"])  # generated files never count

    def test_parallel_limit_and_plan(self):
        r = self.repo()
        self.assertEqual(slices.parallel_limit(r.root), 3)
        for val, want in ((2, 2), (9, 4), (0, 1), ("x", 3)):
            r.write("factory.json", json.dumps({"build": {"max_parallel": val}}))
            self.assertEqual(slices.parallel_limit(r.root), want, val)
        self.assertEqual(slices.plan(slices.parse_map(MAP), 2), [(1, [["A", "B"], ["C"]]), (2, [["D"]])])
        rc, out = r.run("plan", "--map", "design.md")
        self.assertEqual(rc, 0)
        self.assertIn("wave 1: A + B + C", out)

    # ---- check
    def test_check_flags_files_outside_owns(self):
        r = self.repo()
        r.branch("sb", {"src/b/x.py": "1", "b.txt": "2", "other/z.py": "3", "docs/INDEX.md": "gen"})
        rc, out = r.run("check", "sb", "--map", "design.md", "--slice", "B", "--into", "main")
        self.assertEqual(rc, 1)
        self.assertIn("other/z.py", out)
        self.assertNotIn("src/b/x.py", out)
        self.assertNotIn("INDEX.md", out)
        r.branch("ok", {"src/b/x.py": "1"})
        rc, out = r.run("check", "ok", "--map", "design.md", "--slice", "B", "--into", "main")
        self.assertEqual(rc, 0, out)

    def test_usage_errors(self):
        r = self.repo()
        self.assertEqual(r.run("check", "sb", "--map", "nope.md")[0], 2)
        self.assertEqual(r.run("check", "--map", "design.md")[0], 2)
        self.assertEqual(r.run("check", "sb", "--map", "design.md", "--slice", "Z", "--into", "main")[0], 2)

    # ---- land
    def tip(self, r, ref="main"):
        return r.g("rev-parse", ref)

    def test_land_merges_after_passing_gate_and_cleans_up(self):
        r = self.repo()
        r.branch("sb", {"src/b/x.py": "1"})
        before = self.tip(r)
        rc, out = r.run("land", "sb", "--map", "design.md", "--slice", "B", "--into", "main", "--gate-cmd", "true")
        self.assertEqual(rc, 0, out)
        self.assertNotEqual(self.tip(r), before)
        self.assertTrue(os.path.isfile(os.path.join(r.root, "src/b/x.py")))
        self.assertEqual(r.g("worktree", "list").count("\n"), 0)  # temp worktree removed

    def test_gate_rows_are_copied_to_the_root_checkout(self):
        r = self.repo()
        r.branch("sb", {"src/b/x.py": "1"})
        r.write("fakegate.py", "import os\nos.makedirs('metrics', exist_ok=True)\n"
                "open('metrics/gate.local.jsonl', 'a').write('{\"verdict\": \"pass\"}\\n')\n")
        rc, out = r.run("land", "sb", "--map", "design.md", "--slice", "B", "--into", "main",
                        "--gate-cmd", "python3 %s" % os.path.join(r.root, "fakegate.py"))  # runs with cwd = the throwaway worktree
        self.assertEqual(rc, 0, out)
        rows = open(os.path.join(r.root, "metrics", "gate.local.jsonl")).read().splitlines()
        self.assertEqual([json.loads(x)["verdict"] for x in rows], ["pass"])

    def test_failure_reason_names_the_failing_check(self):
        r = self.repo()
        r.branch("sb", {"src/b/x.py": "1"})
        r.write("fakegate.py", "print('gate: FAIL (1s)')\n[print('  pass c%d 0.1s ok' % i) for i in range(10)]\n"
                "print('  fail tests 1.0s [T1] boom')\n[print('  pass d%d 0.1s ok' % i) for i in range(9)]\nraise SystemExit(1)\n")
        rc, out = r.run("land", "sb", "--map", "design.md", "--slice", "B", "--into", "main",
                        "--gate-cmd", "python3 %s" % os.path.join(r.root, "fakegate.py"))
        self.assertEqual(rc, 1)
        self.assertIn("gate: FAIL", out)
        self.assertIn("fail tests", out)

    def test_failing_gate_does_not_merge(self):
        r = self.repo()
        r.branch("sb", {"src/b/x.py": "1"})
        before = self.tip(r)
        rc, out = r.run("land", "sb", "--map", "design.md", "--slice", "B", "--into", "main", "--gate-cmd", "false")
        self.assertEqual(rc, 1)
        self.assertIn("gate failed", out)
        self.assertEqual(self.tip(r), before)

    def test_cross_slice_change_blocks_land(self):
        r = self.repo()
        r.branch("sb", {"src/b/x.py": "1", "other.py": "2"})
        rc, out = r.run("land", "sb", "--map", "design.md", "--slice", "B", "--into", "main", "--gate-cmd", "true")
        self.assertEqual(rc, 1)
        self.assertIn("other.py", out)

    def test_two_slices_land_serially_second_is_rebased_and_regated(self):
        r = self.repo()
        r.branch("sb", {"src/b/x.py": "1"})
        r.branch("sc", {"scripts/c.py": "2"})  # both from the same base
        marker = os.path.join(r.root, "gate-runs.log")
        gate = "sh -c 'ls src/b/x.py scripts/c.py >> %s 2>&1; true'" % marker  # runs in the temp worktree: records what it sees
        self.assertEqual(r.run("land", "sb", "--map", "design.md", "--slice", "B", "--into", "main", "--gate-cmd", "true")[0], 0)
        rc, out = r.run("land", "sc", "--map", "design.md", "--slice", "C", "--into", "main", "--gate-cmd", gate)
        self.assertEqual(rc, 0, out)
        self.assertIn("rebasing", out)
        with open(marker) as fh:
            seen = fh.read()
        self.assertNotIn("No such file", seen)  # the gate for C saw B's file: re-gated on the rebased tree
        self.assertEqual(r.g("log", "--format=%s", "main").splitlines(), ["sc", "sb", "base"])  # linear, ff-only

    def test_rebase_conflict_is_reported_not_merged(self):
        r = self.repo()
        r.branch("sb", {"b.txt": "mine\n"})
        r.branch("sx", {"b.txt": "theirs\n"})
        self.assertEqual(r.run("land", "sx", "--map", "design.md", "--slice", "B", "--into", "main", "--gate-cmd", "true")[0], 0)
        before = self.tip(r)
        rc, out = r.run("land", "sb", "--map", "design.md", "--slice", "B", "--into", "main", "--gate-cmd", "true")
        self.assertEqual(rc, 1)
        self.assertIn("rebase", out)
        self.assertEqual(self.tip(r), before)
        self.assertEqual(r.g("worktree", "list").count("\n"), 0)

    def test_land_requires_integration_branch_checked_out(self):
        r = self.repo()
        r.branch("sb", {"src/b/x.py": "1"})
        r.g("checkout", "-q", "sb")
        rc, out = r.run("land", "sb", "--map", "design.md", "--slice", "B", "--into", "main", "--gate-cmd", "true")
        self.assertEqual(rc, 1)
        self.assertIn("not on main", out)

    def test_index_is_regenerated_and_committed_before_the_gate(self):
        r = self.repo()
        r.write("docs/a.md", "# A doc\n")
        os.makedirs(os.path.join(r.root, "scripts"))
        shutil.copy(os.path.join(ROOT, "scripts", "docs_index.py"), os.path.join(r.root, "scripts", "docs_index.py"))
        r.g("add", "-A")
        r.g("commit", "-qm", "tools")
        r.branch("sb", {"src/b/x.py": "1"})
        # no index exists yet, so `docs_index.py --check` fails unless land regenerates and commits it first
        rc, out = r.run("land", "sb", "--map", "design.md", "--slice", "B", "--into", "main", "--gate-cmd",
                        "python3 scripts/docs_index.py --check")
        self.assertEqual(rc, 0, out)
        self.assertIn("docs/INDEX.md", r.g("show", "--stat", "--format=", "main"))

    def test_protected_into_needs_allow_protected_and_is_refused_during_a_mission(self):
        r = self.repo()
        r.branch("sb", {"src/b/x.py": "1"})
        before = self.tip(r)
        args = ("land", "sb", "--map", "design.md", "--slice", "B", "--into", "main", "--gate-cmd", "true")
        rc, out = r.run(*args, protected_ok=False)
        self.assertEqual(rc, 1)
        self.assertIn("--allow-protected", out)
        self.assertEqual(self.tip(r), before)
        # a mission that is active refuses even with --allow-protected
        r.g("checkout", "-q", "-b", "mission/demo")
        r.write("docs/missions/demo.md", "# Mission: d\n\n<!-- mission:start -->\nslug: demo\nstatus: active\n"
                "go: \"go\"\ndate: 2026-01-01\nstarted_at: 2026-01-01T00:00:00Z\nbranch: mission/demo\n"
                "milestone: M5\nscope_in: a\nscope_out: b\n<!-- mission:end -->\n")
        r.g("add", "-A")
        r.g("commit", "-qm", "mission")
        r.g("checkout", "-q", "main")
        r.g("merge", "-q", "--ff-only", "mission/demo")
        rc, out = r.run(*args)
        self.assertEqual(rc, 1)
        self.assertIn("mission is active", out)

    def test_gate_cmd_is_refused_without_the_test_env_var(self):
        r = self.repo()
        r.branch("sb", {"src/b/x.py": "1"})
        old = os.environ.pop("SLICES_TEST_GATE")
        try:
            rc, out = r.run("land", "sb", "--map", "design.md", "--slice", "B", "--into", "main", "--gate-cmd", "true")
        finally:
            os.environ["SLICES_TEST_GATE"] = old
        self.assertEqual(rc, 1)
        self.assertIn("tests only", out)


if __name__ == "__main__":
    unittest.main()
