"""Learning from gate rejections (AUTO-7, ADR 0010 C7): scripts/learn.py, the Autonomy Learning block, the fixer eval tasks."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import learn  # noqa: E402
from obs import tab_autonomy  # noqa: E402

PILOT = os.path.join(ROOT, "evals", "spikes", "pilot-semverlite", "runner-2026-11-13.jsonl")
HAVE_EVALS = os.path.isdir(os.path.join(ROOT, "evals", "tasks"))


def att(issue, k, codes, ts, outcome="fail", run="r1", cost=0.1):
    return {"kind": "attempt", "issue": issue, "attempt": k, "codes": codes, "ts": ts, "outcome": outcome, "run": run, "cost_usd": cost}


def project(rows=(), gate=()):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "metrics"))
    with open(os.path.join(d, "metrics", "runner.jsonl"), "w") as fh:
        fh.write("".join(json.dumps(r) + "\n" for r in rows) + "not json\n")
    with open(os.path.join(d, "metrics", "gate.local.jsonl"), "w") as fh:
        fh.write("".join(json.dumps(r) + "\n" for r in gate))
    return d


class Report(unittest.TestCase):
    def test_threshold_and_window(self):
        rows = [att("ISS-1", k, ["protected-path"], "2026-11-%02dT10:00:00Z" % (1 + k)) for k in range(3)]       # 3 in 3 days
        rows += [att("ISS-2", k, ["slow"], "2026-11-%02dT10:00:00Z" % (1 + 10 * k)) for k in range(3)]            # 3 in 21 days
        rows += [att("ISS-3", 1, ["rare"], "2026-11-05T10:00:00Z")]
        a = learn.analyze(project(rows))
        self.assertEqual([c["code"] for c in a["candidates"]], ["protected-path"])
        self.assertEqual(learn.analyze(project(rows), threshold=1)["candidates"][0]["total"], 3)
        self.assertEqual(len(a["candidates"][0]["examples"]), 3)
        self.assertEqual(learn.analyze(project(rows), window=30)["candidates"][1]["code"], "slow")

    def test_gate_rejections_counted_separately(self):
        g = [{"verdict": "fail", "codes": ["lint-failed"], "ts": "2026-11-10T10:00:00+00:00", "sha": "abc", "base": "def"}] * 3
        g += [{"verdict": "pass", "codes": [], "ts": "2026-11-10T10:00:00+00:00"}]
        a = learn.analyze(project(gate=g))
        self.assertEqual([(c["source"], c["code"]) for c in a["candidates"]], [("gate", "lint-failed")])

    def test_first_try_rework_cost(self):
        rows = [att("ISS-1", 1, [], "2026-11-02T10:00:00Z", "merged", "a", 0.2),
                att("ISS-2", 1, ["x"], "2026-11-02T11:00:00Z", "fail", "b", 0.3), att("ISS-2", 2, [], "2026-11-02T12:00:00Z", "merged", "b", 0.3)]
        a = learn.analyze(project(rows))
        self.assertEqual(a["first_try_rate"], 0.5)
        self.assertEqual(a["fixed"], 2)
        self.assertEqual(a["rework_per_fixed"], 0.5)
        self.assertAlmostEqual(a["cost_per_fixed"], 0.4)
        self.assertEqual(a["first_try"][0]["issues"], 2)

    def test_empty_state_and_cli_writes_gitignored_file(self):
        d = tempfile.mkdtemp()
        a = learn.analyze(d)
        self.assertFalse(a["exists"])
        self.assertIn("nothing to learn", learn.markdown(a))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(learn.main(["report", "--root", d]), 0)
        self.assertTrue(os.path.isfile(os.path.join(d, "metrics", "LEARN.md")))
        with open(os.path.join(ROOT, ".gitignore")) as fh:
            self.assertIn("metrics/LEARN.md", fh.read().split())

    def test_threshold_default_in_factory_json(self):
        with open(os.path.join(ROOT, "factory.json")) as fh:
            self.assertEqual(json.load(fh)["autonomy"]["learn_threshold"], 3)
        self.assertEqual(learn.analyze(tempfile.mkdtemp())["threshold"], 3)

    @unittest.skipUnless(os.path.isfile(PILOT), "pilot rows not in this copy")
    def test_pilot_rows_surface_recurring_codes(self):
        d = tempfile.mkdtemp()
        a = learn.analyze(d, rows_files=[PILOT])
        self.assertEqual({c["code"] for c in a["candidates"]},
                         {"fixer-touched-protected", "reviewer-modified-tree", "structure-failed", "open-prd-questions"})
        self.assertEqual(a["attempts"], 13)
        self.assertEqual(a["fixed"], 1)
        shutil.copy(PILOT, os.path.join(d, "r.jsonl"))
        with contextlib.redirect_stdout(io.StringIO()):
            learn.main(["report", "--root", d, "--rows", PILOT])
        with open(os.path.join(d, "metrics", "LEARN.md")) as fh:
            md = fh.read()
        self.assertIn("## Candidate rules", md)
        self.assertIn("reviewer-modified-tree", md)
        self.assertIn("ISS-0001 attempt", md)


class Tab(unittest.TestCase):
    def test_empty_state_does_not_fail(self):
        d = tempfile.mkdtemp()
        data = tab_autonomy.collect(d, {})
        html = tab_autonomy.render(data)
        self.assertIn("No rejection data yet", html)
        self.assertNotIn("learning:", tab_autonomy.line(data))

    def test_block_shows_candidates_trend_and_codes(self):
        rows = [att("ISS-1", k, ["protected-path"], "2026-11-%02dT10:00:00Z" % (2 + k)) for k in range(3)]
        rows += [att("ISS-1", 4, [], "2026-11-09T10:00:00Z", "merged")]
        d = project(rows)
        data = tab_autonomy.collect(d, {})
        html = tab_autonomy.render(data)
        for needle in ("Failure codes over time", "First-try pass trend", "Candidate rules", "protected-path", "Cost per fixed issue", "Rework per fixed issue"):
            self.assertIn(needle, html)
        self.assertIn("learning: 1 candidate rule(s) (protected-path)", tab_autonomy.line(data))

    def test_broken_rows_never_fail_the_build(self):
        d = project([{"kind": "attempt", "ts": "garbage", "codes": ["x"]}, {"kind": "attempt", "codes": "oops"}])
        tab_autonomy.render(tab_autonomy.collect(d, {}))


@unittest.skipUnless(HAVE_EVALS, "evals/ not in this copy")
class FixerEvalTasks(unittest.TestCase):
    IDS = ("fixer-protected", "fixer-scope", "fixer-reuse")

    def setUp(self):
        import evals
        import evals_graders as G
        self.evals, self.G = evals, G

    def task(self, tid):
        return next(t for t in self.evals.load_tasks() if t["id"] == tid)

    def grade(self, tid, edits=None):
        t = self.task(tid)
        self.assertEqual(self.evals.validate_task(t), [])
        d = self.evals.prepare_workdir(t, os.path.join(tempfile.mkdtemp(), "p"))
        for rel, text in (edits or {}).items():
            os.makedirs(os.path.dirname(os.path.join(d, rel)) or d, exist_ok=True)
            with open(os.path.join(d, rel), "w", encoding="utf-8") as fh:
                fh.write(text)
        return {s["id"]: self.G.run_grader(s, d, [])[0] for s in t["graders"]}

    def test_mapped_in_rules_and_listed(self):
        with open(os.path.join(ROOT, "evals", "rules.json")) as fh:
            gates = {g for r in json.load(fh)["rules"] for g in r["gates"]}
        for tid in self.IDS:
            self.assertTrue(set(self.task(tid)["gates"]) <= gates, tid)

    def test_noop_agent_fails(self):
        for tid in self.IDS:
            self.assertFalse(all(self.grade(tid).values()), tid)

    def test_protected_edit_fails_and_proper_fix_passes(self):
        fix = ('import re\nimport unicodedata\n\n\ndef slugify(text):\n    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()\n'
               '    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")\n')
        self.assertTrue(all(self.grade("fixer-protected", {"textkit/core.py": fix}).values()))
        cheat = self.grade("fixer-protected", {"textkit/core.py": fix, "tests/acceptance/test_slugify.py": "import unittest\n"})
        self.assertFalse(cheat["acceptance_untouched"])

    def test_scope_creep_fails_and_small_fix_passes(self):
        core = '"""textkit core helpers."""\nimport re\n\n\ndef slugify(text):\n    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")\n'
        self.assertTrue(all(self.grade("fixer-scope", {"textkit/core.py": core}).values()))
        creep = self.grade("fixer-scope", {"textkit/core.py": core, "textkit/legacy.py": "def old_helper(x, y=2):\n    return x * y\n"})
        self.assertFalse(creep["legacy_untouched"])
        self.assertFalse(creep["only_issue_files"])
        stray = self.grade("fixer-scope", {"textkit/core.py": core, "README.md": "x\n"})
        self.assertFalse(stray["only_issue_files"])

    def test_reuse_passes_with_counter_and_fails_hand_rolled(self):
        init = "from .core import slugify, most_common_word  # noqa: F401\n"
        good = ('"""textkit core helpers."""\nimport re\nfrom collections import Counter\n\n\ndef slugify(text):\n    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")\n\n\n'
                'def most_common_word(text):\n    c = Counter(text.lower().split())\n    return c.most_common(1)[0][0] if c else None\n')
        self.assertTrue(all(self.grade("fixer-reuse", {"textkit/core.py": good, "textkit/__init__.py": init}).values()))
        bad = ('"""textkit core helpers."""\nimport re\n\n\ndef slugify(text):\n    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")\n\n\n'
               'def most_common_word(text):\n    counts = {}\n    for w in text.lower().split():\n        counts[w] = counts.get(w, 0) + 1\n'
               '    return max(counts, key=counts.get) if counts else None\n')
        r = self.grade("fixer-reuse", {"textkit/core.py": bad, "textkit/__init__.py": init})
        self.assertTrue(r["tests_green"])
        self.assertFalse(r["no_hand_rolled_count"])


if __name__ == "__main__":
    unittest.main()
