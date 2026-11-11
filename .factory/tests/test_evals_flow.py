"""Evals tab backlog flow (EVAL-5): history parsing, bands, coverage and lapse, warnings, sparse states. No model calls."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from obs import evals_flow as F  # noqa: E402
from obs import evals_views as V  # noqa: E402

TASK = lambda tid, covers: {"id": tid, "covers": covers}  # noqa: E731


def run_row(task, sid, ok, ts):
    return {"task": task, "set": sid, "pass": ok, "ts": ts + "T10:00:00Z"}


def repo(steps):
    """steps: [(date, backlog text, commit message)] -> temp git repo."""
    r = tempfile.mkdtemp()
    for i, (day, text, msg) in enumerate(steps):
        os.makedirs(os.path.join(r, "docs"), exist_ok=True)
        with open(os.path.join(r, "docs", "BACKLOG.md"), "w") as fh:
            fh.write(text)
        env = dict(os.environ, GIT_AUTHOR_DATE=day + "T12:00:00Z", GIT_COMMITTER_DATE=day + "T12:00:00Z")
        cmds = ([["init", "-q"]] if i == 0 else []) + [["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q", "-m", msg]]
        for a in cmds:
            subprocess.run(["git"] + a, cwd=r, check=True, capture_output=True, env=env)
    return r


B1 = "- [ ] AB-1 One\n"
B2 = "- [ ] AB-1 One\n- [ ] AB-2 Two\n- [x] plain item no id\n"
B3 = "- [x] AB-1 One\n- [ ] AB-2 Two\n"
B4 = "- [x] AB-1 One\n- [x] AB-2 Two\n- [-] AB-9 dropped\n"


class Flow(unittest.TestCase):
    def setUp(self):
        self.r = repo([("2026-01-01", B1, "add backlog"), ("2026-01-03", B2, "more\n\nRefs: AB-2"),
                       ("2026-01-05", B3, "tick one"), ("2026-01-08", B4, "tick two")])

    def test_parse_ids_only_and_drops(self):
        self.assertEqual(sorted(F.parse_backlog(B4)), ["AB-1", "AB-2"])
        self.assertEqual(F.parse_backlog(""), {})

    def test_history_dates(self):
        items, ok = F.history(self.r, "2026-01-10")
        self.assertTrue(ok)
        self.assertEqual((items["AB-1"]["todo"], items["AB-1"]["doing"], items["AB-1"]["done"]), ("2026-01-01", "2026-01-05", "2026-01-05"))
        self.assertEqual((items["AB-2"]["todo"], items["AB-2"]["doing"], items["AB-2"]["done"]), ("2026-01-03", "2026-01-03", "2026-01-08"))

    def test_bands_sum_to_items_that_exist(self):
        items, ok = F.history(self.r, "2026-01-10")
        fl = F.build(items, ok, [], [], 0.1, "2026-01-10")
        for p in fl["points"]:
            self.assertEqual(p["sum"], p["todo"] + p["doing"] + p["done"] + p["covered"])
        by = {p["date"]: p for p in fl["points"]}
        self.assertEqual(by["2026-01-01"]["todo"], 1)
        self.assertEqual((by["2026-01-03"]["todo"], by["2026-01-03"]["doing"]), (1, 1))
        self.assertEqual((by["2026-01-05"]["done"], by["2026-01-05"]["doing"]), (1, 1))
        self.assertEqual(by["2026-01-10"]["done"], 2)
        self.assertEqual(fl["total"], 2)

    def test_covered_by_passing_latest_set_and_lapse(self):
        items, ok = F.history(self.r, "2026-01-10")
        rows = [run_row("t", "s1", True, "2026-01-06"), run_row("t", "s2", False, "2026-01-09")]
        fl = F.build(items, ok, [TASK("t", ["AB-1"])], rows, 0.1, "2026-01-10")
        by = {p["date"]: p for p in fl["points"]}
        self.assertEqual(by["2026-01-06"]["covered"], 1)  # passing latest set
        self.assertEqual(by["2026-01-09"]["covered"], 0)  # regressed: coverage lapses
        self.assertEqual(by["2026-01-10"]["done"], 2)
        self.assertEqual(fl["covered_ids"], [])
        fl = F.build(items, ok, [TASK("t", ["AB-1"])], rows[:1], 0.1, "2026-01-10")
        self.assertEqual(fl["points"][-1]["covered"], 1)
        self.assertEqual(fl["covered_ids"], ["AB-1"])

    def test_threshold_tolerates_flaky(self):
        items, ok = F.history(self.r, "2026-01-10")
        rows = [run_row("t", "s1", True, "2026-01-06")] * 9 + [run_row("t", "s1", False, "2026-01-06")]
        self.assertEqual(F.build(items, ok, [TASK("t", ["AB-1"])], rows, 0.1, "2026-01-10")["points"][-1]["covered"], 1)
        self.assertEqual(F.build(items, ok, [TASK("t", ["AB-1"])], rows, 0.05, "2026-01-10")["points"][-1]["covered"], 0)

    def test_unknown_cover_ids_are_warned_not_fatal(self):
        items, ok = F.history(self.r, "2026-01-10")
        fl = F.build(items, ok, [TASK("t", ["AB-1", "NOPE-7"])], [], 0.1, "2026-01-10")
        self.assertEqual(len(fl["warnings"]), 1)
        self.assertIn("NOPE-7", V.flow(fl))
        self.assertIn("<svg", V.flow(fl))
        self.assertNotIn("<script", V.flow(fl))

    def test_render_chart_table_and_legend(self):
        items, ok = F.history(self.r, "2026-01-10")
        h = V.flow(F.build(items, ok, [], [], 0.1, "2026-01-10"))
        self.assertIn('role="img"', h)
        self.assertIn("<table>", h)
        self.assertIn("approximate", h)
        self.assertIn("Done and covered", h)


class Sparse(unittest.TestCase):
    def test_few_dates_quiet_sentence(self):
        r = repo([("2026-01-01", B1, "x")])
        items, ok = F.history(r, "2026-01-01")
        h = V.flow(F.build(items, ok, [], [], 0.1, "2026-01-01"))
        self.assertIn("Too little history", h)
        self.assertNotIn("<svg", h)

    def test_no_git_and_no_backlog(self):
        c = tempfile.mkdtemp()
        fl = F.collect(c, [TASK("t", ["X-1"])], [], 0.1)
        self.assertFalse(fl["ok"])
        self.assertEqual(fl["warnings"], [])
        self.assertIn("No backlog history", V.flow(fl))

    def test_no_git_with_backlog_file(self):
        c = tempfile.mkdtemp()
        os.makedirs(os.path.join(c, "docs"))
        with open(os.path.join(c, "docs", "BACKLOG.md"), "w") as fh:
            fh.write(B3)
        fl = F.collect(c, [], [], 0.1, "2026-02-01")
        self.assertTrue(fl["ok"])
        self.assertEqual(fl["total"], 2)
        self.assertIn("Too little history", V.flow(fl))

    def test_zero_items_with_git(self):
        r = repo([("2026-01-01", "# Backlog\n", "x")])
        h = V.flow(F.collect(r, [], [], 0.1))
        self.assertIn("No backlog", h)

    def test_malformed_input_does_not_raise(self):
        fl = F.collect(tempfile.mkdtemp(), [{"id": "t"}], [{"junk": 1}], 0.1)  # task without covers key
        self.assertIn("Backlog flow", V.flow(fl))

    def test_real_repo(self):
        from obs import evals_data
        fl = F.collect(ROOT, evals_data.load_tasks(ROOT), [], 0.1)
        self.assertIn("Backlog flow", V.flow(fl))
        for p in fl.get("points", []):
            self.assertEqual(p["sum"], p["todo"] + p["doing"] + p["done"] + p["covered"])
