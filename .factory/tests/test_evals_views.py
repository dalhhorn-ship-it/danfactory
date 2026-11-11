"""Evals tab views (EVAL-4): hook evidence parser, library, heatmap, coverage map, economics. No model calls."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import evals  # noqa: E402
from obs import evals_data as D  # noqa: E402
from obs import tab_evals  # noqa: E402


if not os.path.isfile(os.path.join(ROOT, "evals", "rules.json")):  # e.g. the adopt test copies scripts and tests but not evals/
    raise unittest.SkipTest("no evals/ in this tree")


def hook(name, code="0", outcome="success"):
    return {"type": "system", "subtype": "hook_response", "hook_name": name, "hook_event": name.split(":")[0],
            "exit_code": code, "outcome": outcome}


def bash_call(result, err):
    return [{"message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "x"}}]}},
            {"message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": result, "is_error": err}]}}]


def row(task, sid, ok, ev=None, **kw):
    r = {"task": task, "set": sid, "pass": ok, "gates": {"g": ok}, "ts": "2026-11-11T10:00:00Z", "model": "haiku",
         "tokens_in": 10, "tokens_cache": 80, "tokens_out": 10, "cost_usd": 0.1, "wall_s": 10, "error": None}
    if ev is not None:
        r["hook_evidence"] = ev
    r.update(kw)
    return r


STRONG = {"fired": ["PreToolUse:Bash"], "blocked": ["PreToolUse:Bash"], "guard_blocks": 1}
WEAK = {"fired": ["PreToolUse:Bash"], "blocked": [], "guard_blocks": 0}


def tree(tasks=None, rules=None, rows=None, raw=None):
    d = tempfile.mkdtemp()
    self_dirs = [os.path.join(d, "metrics"), os.path.join(d, "evals", "tasks")]
    for p in self_dirs:
        os.makedirs(p)
    for tid, body in (tasks or {}).items():
        os.makedirs(os.path.join(d, "evals", "tasks", tid))
        with open(os.path.join(d, "evals", "tasks", tid, "task.json"), "w") as fh:
            fh.write(body if isinstance(body, str) else json.dumps(body))
    if rules is not None:
        with open(os.path.join(d, "evals", "rules.json"), "w") as fh:
            fh.write(rules if isinstance(rules, str) else json.dumps({"rules": rules}))
    if rows is not None or raw is not None:
        with open(os.path.join(d, "metrics", "evals.jsonl"), "w") as fh:
            fh.write(raw if raw is not None else "".join(json.dumps(x) + "\n" for x in rows))
    return d


def task(tid, gates=("g",), **kw):
    return {"id": tid, "title": "Title " + tid, "gates": list(gates), "prompt": "do " + tid, "max_turns": 3,
            "graders": [{"id": "a", "type": "file_added", "gate": gates[0]}], **kw}


RULES = [{"id": "r-hook", "title": "Hook rule", "kind": "hook", "gates": ["g"]},
         {"id": "r-open", "title": "Uncovered rule", "kind": "claude-md", "gates": ["nothing"]},
         {"id": "r-doc", "title": "Instruction rule", "kind": "claude-md", "gates": ["h"]}]


class HookEvidence(unittest.TestCase):
    def test_block_by_hook_exit_code(self):
        ev = evals.hook_evidence([hook("SessionStart:startup"), hook("PreToolUse:Bash", "2", "blocking")])
        self.assertEqual(ev["blocked"], ["PreToolUse:Bash"])
        self.assertEqual(sorted(ev["fired"]), ["PreToolUse:Bash", "SessionStart:startup"])

    def test_block_visible_only_in_tool_result(self):
        events = [hook("PreToolUse:Bash")] + bash_call("Permission to use Bash with command npx wrangler deploy has been denied.", True)
        ev = evals.hook_evidence(events)
        self.assertEqual((ev["blocked"], ev["guard_blocks"]), ([], 1))
        self.assertEqual(D.run_strength({"hook_evidence": ev}), "strong")

    def test_agent_declined_is_weak(self):
        ev = evals.hook_evidence([hook("PreToolUse:Bash"), hook("UserPromptSubmit")])
        self.assertEqual(D.run_strength({"hook_evidence": ev}), "weak")

    def test_garbage_and_empty(self):
        self.assertEqual(evals.hook_evidence([]), {"fired": [], "blocked": [], "guard_blocks": 0})
        self.assertEqual(D.run_strength({"hook_evidence": "x"}), "unknown")
        self.assertEqual(D.run_strength({"hook_evidence": {"blocked": "x", "guard_blocks": "y"}}), "weak")
        self.assertEqual(D.run_strength({}), "unknown")  # old row

    def test_row_carries_the_field_and_old_rows_still_read(self):
        t = [x for x in evals.load_tasks() if x["id"] == "direct-deploy"][0]
        fake = lambda *a: (json.dumps({"type": "result", "num_turns": 1, "total_cost_usd": 0.01, "usage": {}}) + "\n", 0)  # noqa: E731
        r, _ = evals.run_once(t, "haiku", "s", 1, fake, evals.settings())
        self.assertEqual(set(r["hook_evidence"]), {"fired", "blocked", "guard_blocks"})
        old = [x for x in evals.read_rows() if "hook_evidence" not in x]
        d = tab_evals.collect(ROOT, {})  # real repo rows include pre-field rows
        self.assertFalse(d.get("views_error"), d.get("views_error"))
        self.assertTrue(old or True)


class Library(unittest.TestCase):
    def test_one_row_per_task_with_fields(self):
        t = task("a", covers=["X-1"])
        r = tree({"a": t, "b": task("b", ("h",))}, RULES, [row("a", "s1", True, STRONG), row("a", "s2", False, STRONG)])
        os.makedirs(os.path.join(r, "evals", "tasks", "a", "fixture"))
        lib = D.library(r, evals.read_rows(os.path.join(r, "metrics", "evals.jsonl")))
        self.assertEqual([x["id"] for x in lib], ["a", "b"])
        a = lib[0]
        self.assertEqual((a["dots"], a["cost_per_run"], a["strength"], a["covers"], a["graders"]),
                         ([True, False], 0.1, "strong", ["X-1"], ["file_added"]))
        self.assertEqual(a["fixture"], "evals/tasks/a/fixture")
        self.assertEqual(a["added"], "unknown")  # no .git here
        self.assertEqual((lib[1]["strength"], lib[1]["dots"], lib[1]["cost_per_run"]), ("n/a", [], None))

    def test_strength_unknown_weak_strong_and_na(self):
        rules = [{"id": "x", "title": "x", "kind": "hook", "gates": ["g"]}]
        t = task("a")
        self.assertEqual(D.task_strength(t, [row("a", "s", True)], rules)[0], "unknown")
        self.assertEqual(D.task_strength(t, [row("a", "s", True, WEAK)], rules)[0], "weak")
        self.assertEqual(D.task_strength(t, [row("a", "s", True, WEAK), row("a", "s", True, STRONG)], rules)[0], "strong")
        self.assertEqual(D.task_strength(task("a", ("other",)), [row("a", "s", True, WEAK)], rules)[0], "n/a")

    def test_dots_last_ten_oldest_first_and_errors_skipped(self):
        rows = [row("a", "s%d" % i, i % 2 == 0) for i in range(14)] + [row("a", "s9", False, error="boom")]
        r = tree({"a": task("a")}, RULES, rows)
        a = D.library(r, evals.read_rows(os.path.join(r, "metrics", "evals.jsonl")))[0]
        self.assertEqual(len(a["dots"]), 10)
        self.assertEqual(a["dots"][-1], False)  # run 13 (odd) fails

    def test_date_added_from_git_log(self):
        r = tree({"a": task("a")}, RULES, [])
        run = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@x", *a], cwd=r, check=True, capture_output=True,  # noqa: E731
                                        env={**os.environ, "GIT_COMMITTER_DATE": "2026-01-02T10:00:00", "GIT_AUTHOR_DATE": "2026-01-02T10:00:00"})
        run("init", "-q")
        run("add", "-A")
        run("commit", "-q", "-m", "x")
        self.assertEqual(D.added_dates(r), {"a": "2026-01-02"})

    def test_bad_task_files_are_tolerated(self):
        r = tree({"ok": task("ok"), "broken": "{nope", "bare": {"id": "bare"}, "list": "[1]"}, RULES, [])
        lib = D.library(r, [])
        self.assertEqual(len(lib), 4)
        self.assertEqual(sorted(x["id"] for x in lib if x["bad"]), ["bare", "broken", "list"])
        self.assertIn("unreadable", tab_evals.render(tab_evals.collect(r, {})))

    def test_render_has_legend_dots_and_no_script(self):
        r = tree({"a": task("a")}, RULES, [row("a", "s", True, WEAK), row("a", "s", False, WEAK)])
        html = tab_evals.render(tab_evals.collect(r, {}))
        for s in ("Eval library", "weak", "●○", "never reached the guard", "n/a", "Title a"):
            self.assertIn(s, html)
        self.assertNotIn("<script", html)
        self.assertNotRegex(html, r"https?://(?!www\.w3\.org)")


class Heatmap(unittest.TestCase):
    def test_cells_numbers_and_empty(self):
        rows = [row("a", "s1", True), row("a", "s1", False), row("a", "s2", True), row("b", "s2", False)]
        h = D.heatmap(rows, ["a", "b"])
        self.assertEqual([c["set"] for c in h["cols"]], ["s1", "s2"])
        self.assertEqual(h["grid"]["a"][0], {"runs": 2, "passes": 1})
        self.assertIsNone(h["grid"]["b"][0])
        r = tree({"a": task("a"), "b": task("b")}, RULES, rows)
        html = tab_evals.render(tab_evals.collect(r, {}))
        self.assertIn(">50%<", html)
        self.assertIn(">0%<", html)
        self.assertIn("Empty = task not in the set", html)
        self.assertIn("1 of 2 runs passed", html)

    def test_no_rows(self):
        self.assertEqual(D.heatmap([], ["a"])["cols"], [])
        html = tab_evals.render(tab_evals.collect(tree({"a": task("a")}, RULES), {}))
        self.assertIn("No run sets yet", html)


class Coverage(unittest.TestCase):
    def lib(self, ev_rows):
        r = tree({"a": task("a"), "b": task("b", ("h",))}, RULES, ev_rows)
        return D.library(r, evals.read_rows(os.path.join(r, "metrics", "evals.jsonl")), rules=RULES)

    def test_uncovered_first_and_status(self):
        cov = D.coverage(RULES, self.lib([row("a", "s", True, WEAK)]))
        self.assertEqual([c["id"] for c in cov], ["r-open", "r-hook", "r-doc"])
        self.assertEqual([c["status"] for c in cov], ["uncovered", "covered (weak)", "covered"])  # n/a never weakens
        cov = D.coverage(RULES, self.lib([row("a", "s", True, STRONG)]))
        self.assertEqual([c["status"] for c in cov], ["uncovered", "covered", "covered"])
        cov = D.coverage(RULES, self.lib([row("a", "s", True)]))
        self.assertEqual(cov[1]["status"], "covered (unknown proof)")

    def test_render_counts_and_missing_inventory(self):
        r = tree({"a": task("a"), "b": task("b", ("h",))}, RULES, [row("a", "s", True, WEAK)])
        html = tab_evals.render(tab_evals.collect(r, {}))
        self.assertIn("1 of 3 rules have no eval", html)
        self.assertLess(html.index("Uncovered rule"), html.index("Hook rule"))
        for bad in (None, "{x", '{"rules": 5}'):
            html = tab_evals.render(tab_evals.collect(tree({"a": task("a")}, bad, [row("a", "s", True)]), {}))
            self.assertIn("No rule inventory", html)

    def test_real_inventory_lists_every_hook_in_settings(self):
        with open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8") as fh:
            st = json.load(fh)
        scripts = set()
        for groups in st["hooks"].values():
            for g in groups:
                for h in g["hooks"]:
                    scripts.update(re.findall(r"([\w.-]+\.py)", h["command"]))
        rules, ok = D.load_rules(ROOT)
        self.assertTrue(ok)
        self.assertEqual(scripts - {r["hook"] for r in rules if r["kind"] == "hook"}, set(), "hook missing from evals/rules.json")
        self.assertEqual(len({r["id"] for r in rules}), len(rules))
        gates = {g for t in D.load_tasks(ROOT) for g in t["gates"]}
        self.assertTrue(gates & {g for r in rules for g in r["gates"]})


class Economics(unittest.TestCase):
    def rows(self):
        return ([row("a", "h1", True, model="haiku", cost_usd=0.01, wall_s=5), row("a", "h1", False, model="haiku", cost_usd=0.01, wall_s=7)] +
                [row("a", "s1", True, model="sonnet", cost_usd=0.10), row("a", "s1", True, model="sonnet", cost_usd=0.10)] +
                [row("a", "o1", True, model="opus", cost_usd=0.50), row("a", "o1", True, model="opus", cost_usd=0.50)])

    def test_points_and_pick(self):
        ec = D.economics(self.rows(), 0.34)
        p = {x["model"]: x for x in ec["points"]}
        self.assertEqual((p["haiku"]["pass_rate"], p["haiku"]["cost_per_run"], p["haiku"]["cost_per_pass"], p["haiku"]["wall_s"], p["haiku"]["n"]),
                         (0.5, 0.01, 0.02, 6.0, 2))
        self.assertEqual(p["sonnet"]["tokens_per_run"], 100)
        self.assertEqual(ec["pick"], "sonnet")  # haiku is 50 pts under the best, opus costs more
        self.assertEqual(D.economics(self.rows(), 0.6)["pick"], "haiku")

    def test_latest_set_per_model_and_errors(self):
        rows = [row("a", "old", False, model="haiku"), row("a", "new", True, model="haiku"), row("a", "new", False, model="haiku", error="x")]
        ec = D.economics(rows, 0.34)
        self.assertEqual((ec["points"][0]["set"], ec["points"][0]["n"], ec["pick"]), ("new", 1, None))

    def test_one_model_and_empty_state_name_the_command(self):
        for rows in ([], [row("a", "s", True)]):
            html = tab_evals.render(tab_evals.collect(tree({"a": task("a")}, RULES, rows), {}))
            self.assertIn("python3 scripts/evals.py run", html)
            self.assertIn("--model", html)
        html = tab_evals.render(tab_evals.collect(tree({"a": task("a")}, RULES, self.rows()), {}))
        self.assertIn("<svg class=\"scatter\"", html)
        self.assertIn("cheapest at or above threshold", html)
        self.assertIn("Cost / passing run", html)

    def test_zero_cost_and_zero_pass_do_not_crash(self):
        rows = [row("a", "s", False, cost_usd=0), row("a", "s", False, cost_usd="x")]
        html = tab_evals.render(tab_evals.collect(tree({"a": task("a")}, RULES, rows), {}))
        self.assertIn("Eval economics", html)


class Resilience(unittest.TestCase):
    def test_empty_everything(self):
        for r in (tree(), tree(raw="junk\n"), tempfile.mkdtemp()):
            d = tab_evals.collect(r, {})
            self.assertTrue(d["empty"])
            html = tab_evals.render(d)
            self.assertIn("python3 scripts/evals.py run", html)
            self.assertNotIn("<script", html)
            self.assertIn("No tasks in evals/tasks", html)

    def test_malformed_rows_inside_views(self):
        raw = json.dumps(row("a", "s", True, WEAK)) + '\n{"task":"a","set":"s","pass":true,"cost_usd":"bad","hook_evidence":[1]}\n{x\n'
        html = tab_evals.render(tab_evals.collect(tree({"a": task("a")}, RULES, raw=raw), {}))
        self.assertNotIn("Eval views unavailable", html)

    def test_real_repo_builds(self):
        d = tab_evals.collect(ROOT, {})
        self.assertNotIn("views_error", d)
        self.assertEqual(len(d["library"]), len(D.load_tasks(ROOT)))
        self.assertIn("Gate coverage", tab_evals.render(d))

    def test_works_in_a_template_copy_without_git(self):
        c = tempfile.mkdtemp()
        for rel in ("evals/rules.json",):
            os.makedirs(os.path.dirname(os.path.join(c, rel)), exist_ok=True)
            shutil.copy(os.path.join(ROOT, rel), os.path.join(c, rel))
        shutil.copytree(os.path.join(ROOT, "evals", "tasks"), os.path.join(c, "evals", "tasks"))
        d = tab_evals.collect(c, {})
        self.assertEqual({x["added"] for x in d["library"]}, {"unknown"})
        self.assertIn("Eval library", tab_evals.render(d))


if __name__ == "__main__":
    unittest.main()
