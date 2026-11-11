"""Evals dashboard tab (EVAL-2): no model calls, temp repos only."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import dashboard  # noqa: E402
from obs import tab_evals  # noqa: E402


def row(task, sid, ok, gates=None, **kw):
    r = {"task": task, "set": sid, "pass": ok, "gates": gates or {"g1": ok}, "ts": "2026-11-11T10:00:00Z",
         "model": "haiku", "tokens_in": 10, "tokens_cache": 80, "tokens_out": 10, "cost_usd": 0.1, "error": None}
    r.update(kw)
    return r


def repo(rows=None, raw=None, baseline=None):
    r = tempfile.mkdtemp()
    os.makedirs(os.path.join(r, "metrics"))
    if rows is not None or raw is not None:
        with open(os.path.join(r, "metrics", "evals.jsonl"), "w") as fh:
            fh.write(raw if raw is not None else "".join(json.dumps(x) + "\n" for x in rows))
    if baseline is not None:
        with open(os.path.join(r, "metrics", "evals-baseline.json"), "w") as fh:
            json.dump(baseline, fh)
    return r


class EvalsTab(unittest.TestCase):
    def test_empty_states(self):
        for r in (repo(), repo(rows=[]), repo(raw="\n\nnot json\n[1]\n")):
            d = tab_evals.collect(r, {})
            self.assertTrue(d["empty"])
            self.assertIn("python3 scripts/evals.py run", tab_evals.render(d))
            self.assertIn("no evals run yet", tab_evals.line(d))

    def test_malformed_line_skipped(self):
        raw = json.dumps(row("a", "s1", True)) + "\n{broken\n" + json.dumps(row("a", "s1", False)) + "\n"
        d = tab_evals.collect(repo(raw=raw), {})
        self.assertEqual((d["tasks"]["a"]["runs"], d["tasks"]["a"]["passes"]), (2, 1))

    def test_aggregation_per_task_and_gate_latest_set_only(self):
        rows = [row("a", "s1", False), row("a", "s2", True, {"g1": True, "g2": True}),
                row("b", "s2", False, {"g1": True, "g2": False}), row("b", "s2", True, {"g1": True, "g2": True}),
                row("c", "s2", False, error="no result event")]
        d = tab_evals.collect(repo(rows), {})
        self.assertEqual(d["set"], "s2")
        self.assertEqual(d["tasks"]["a"]["rate"], 1.0)
        self.assertEqual(d["tasks"]["b"]["passes"], 1)
        self.assertNotIn("c", d["tasks"])  # infra error not counted
        self.assertEqual(d["gates"]["g1"]["runs"], 3)
        self.assertEqual(d["gates"]["g2"]["passes"], 2)
        self.assertEqual((d["passes"], d["runs"], d["errors"]), (2, 4, 1))
        self.assertEqual(d["tasks"]["a"]["tokens_per_pass"], 100)
        self.assertEqual(d["cost_per_pass"], 0.1)
        self.assertEqual([t["set"] for t in d["trend"]], ["s1", "s2"])
        self.assertEqual(d["last_run"], "2026-11-11")
        html = tab_evals.render(d)
        self.assertIn("<svg", html)
        self.assertNotIn("<script", html)

    def test_flaky_flag(self):
        d = tab_evals.collect(repo([row("a", "s", True), row("a", "s", False), row("b", "s", True), row("c", "s", False)]), {})
        self.assertEqual(d["flaky"], ["a"])
        self.assertIn("flaky", tab_evals.render(d))

    def test_regression_with_and_without_baseline(self):
        rows = [row("a", "s2", False), row("a", "s2", False)]
        d = tab_evals.collect(repo(rows), {})
        self.assertIsNone(d["baseline"])
        self.assertIn("no baseline", tab_evals.line(d))
        self.assertIn("no baseline", tab_evals.render(d))
        base = {"set": "s1", "tasks": {"a": {"runs": 2, "passes": 2, "rate": 1.0}},
                "gates": {"g1": {"runs": 2, "passes": 2, "rate": 1.0}}}
        d = tab_evals.collect(repo(rows, baseline=base), {})
        self.assertTrue(d["baseline"]["regression"])
        self.assertIn("a", d["baseline"]["regressed"])
        self.assertIn("REGRESSION", tab_evals.line(d))
        ok = tab_evals.collect(repo([row("a", "s2", True), row("a", "s2", True)], baseline=base), {})
        self.assertFalse(ok["baseline"]["regression"])
        self.assertIn("no regression", tab_evals.line(ok))
        junk = tab_evals.collect(repo(rows, baseline={"tasks": "x"}), {})
        self.assertIsNone(junk["baseline"])

    def test_print_row_and_data(self):
        old = sys.argv
        sys.argv = ["dashboard.py", "--print"]
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                dashboard.main()
        finally:
            sys.argv = old
        self.assertIn("| Evals |", out.getvalue())
        self.assertIn("evals", [k for k, _l, _m in dashboard.TABS])


if __name__ == "__main__":
    unittest.main()
