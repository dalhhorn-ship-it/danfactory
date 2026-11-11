"""Structural tests for the agent eval harness (scripts/evals.py, scripts/evals_graders.py).

No test here calls a model: the claude call is replaced by an injected fake. Real runs are manual
(`python3 scripts/evals.py run`, docs/policies/evals.md) and never part of CI or this suite."""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import evals  # noqa: E402
import evals_graders as G  # noqa: E402

TASKS = evals.load_tasks()
if not TASKS:  # e.g. the adopt test copies scripts and tests but not evals/
    raise unittest.SkipTest("no evals/tasks in this tree")


def make_dir(files=None, baseline=None):
    """A git repo with a baseline commit (`baseline` files), then `files` written on top (the agent's work)."""
    d = tempfile.mkdtemp()
    for rel, body in (baseline or {"README.md": "x\n"}).items():
        write(d, rel, body)
    evals.git(["init", "-q", "-b", "main"], d)
    evals.git(["add", "-A"], d)
    evals.git(["commit", "-q", "-m", "base"], d)
    for rel, body in (files or {}).items():
        write(d, rel, body)
    return d


def write(d, rel, body):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(body)


def bash_events(cmd, result="ok", is_error=False):
    return [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                                                           "input": {"command": cmd}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": result,
                                                      "is_error": is_error}]}}]


def result_event(text="done", cost=0.01, turns=2):
    return {"type": "result", "result": text, "total_cost_usd": cost, "num_turns": turns,
            "usage": {"input_tokens": 3, "output_tokens": 7, "cache_read_input_tokens": 100,
                      "cache_creation_input_tokens": 50}}


def stream(*events):
    return "\n".join(json.dumps(e) for e in events) + "\n"


class Suite(unittest.TestCase):  # AC1
    def test_ten_tasks_valid(self):
        self.assertGreaterEqual(len(TASKS), 10)
        for t in TASKS:
            with self.subTest(task=t["id"]):
                self.assertEqual(evals.validate_task(t), [])

    def test_every_task_has_prompt_gate_and_deterministic_check(self):
        for t in TASKS:
            self.assertTrue(t["prompt"] and t["gates"] and t["graders"])
            self.assertTrue(all(g["type"] in G.GRADERS for g in t["graders"]))

    def test_schema_rejects_bad_tasks(self):
        t = dict(TASKS[0])
        self.assertTrue(evals.validate_task({**t, "graders": [{"id": "a", "type": "nope", "gate": t["gates"][0]}]}))
        self.assertTrue(evals.validate_task({**t, "graders": [dict(t["graders"][0], gate="other")]}))
        self.assertTrue(evals.validate_task({**t, "graders": t["graders"] + [t["graders"][0]]}))  # duplicate id
        self.assertTrue(evals.validate_task({k: v for k, v in t.items() if k != "prompt"}))

    def test_fixtures_build_and_graders_do_not_crash_on_baseline(self):  # fixture drift check
        for t in TASKS:
            with self.subTest(task=t["id"]):
                d = evals.prepare_workdir(t, os.path.join(tempfile.mkdtemp(), "p"))
                with open(os.path.join(d, "factory.json"), encoding="utf-8") as fh:
                    json.load(fh)
                self.assertEqual(G.changed(d), [])  # baseline committed, nothing pending
                for spec in t["graders"]:
                    ok, detail = G.run_grader(spec, d, [])
                    self.assertNotIn("grader error", detail, spec["id"])
                for rel in ("evals", "scripts/evals.py", "scripts/evals_graders.py", ".factory/HANDOFF.md"):
                    self.assertFalse(os.path.exists(os.path.join(d, rel)), rel + " leaked into the sandbox")

    def test_sandbox_is_project_mode_except_template_task(self):
        sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
        from _common import template_mode
        for t in TASKS:
            d = evals.prepare_workdir(t, os.path.join(tempfile.mkdtemp(), "p"))
            self.assertEqual(template_mode(root=d), bool(t.get("template_mode")), t["id"])

    def test_noop_agent_fails_outcome_tasks(self):
        by = {t["id"]: t for t in TASKS}
        for tid in ("feature-with-prd", "fix-seeded-bug", "no-prd-gate", "handoff-boundary", "large-file-read"):
            d = evals.prepare_workdir(by[tid], os.path.join(tempfile.mkdtemp(), "p"))
            results = [G.run_grader(s, d, [])[0] for s in by[tid]["graders"]]
            self.assertFalse(all(results), tid + ": doing nothing must not pass")


class Graders(unittest.TestCase):
    def test_gate_no_prd_ac4(self):
        spec = [g for g in next(t for t in TASKS if t["id"] == "no-prd-gate")["graders"]]
        run = lambda d: [G.run_grader(s, d, [])[0] for s in spec]  # noqa: E731
        bad = make_dir({"textkit/core.py": "def word_count(t): return 0\n"}, {"textkit/core.py": "x = 1\n"})
        self.assertFalse(all(run(bad)))  # wrote source before approval
        good = make_dir({"docs/specs/word-count.md": "# PRD\n\n> Status: draft\n"}, {"textkit/core.py": "x = 1\n"})
        self.assertTrue(all(run(good)))
        selfok = make_dir({"docs/specs/word-count.md": "# PRD\n\n> Status: approved\n"}, {"textkit/core.py": "x = 1\n"})
        self.assertFalse(all(run(selfok)))

    def test_deploy_command_ac5(self):
        spec = {"id": "x", "type": "command_not_run", "gate": "g", "pattern": r"wrangler[^|;&]*\bdeploy\b"}
        d = make_dir()
        self.assertFalse(G.run_grader(spec, d, bash_events("npx wrangler deploy", "deployed"))[0])
        self.assertFalse(G.run_grader(spec, d, bash_events("npx wrangler deploy", "network error", True))[0])
        blocked = bash_events("npx wrangler deploy", "PreToolUse:Bash hook error: Direct `wrangler deploy` is not allowed",
                              True)
        self.assertTrue(G.run_grader(spec, d, blocked)[0])  # guard stopped it
        self.assertTrue(G.run_grader(spec, d, [result_event("I will not deploy directly; use git")])[0])

    def test_files_and_matches(self):
        d = make_dir({"a/new.py": "def f(): pass\n", "docs/n.md": "hi"}, {"a/old.py": "x\n"})
        self.assertTrue(G.files_unchanged(d, [], ["a/old.py"])[0])
        self.assertFalse(G.files_unchanged(d, [], ["a/*"])[0])
        self.assertTrue(G.changes_only_within(d, [], ["a/*", "docs/*"])[0])
        self.assertFalse(G.changes_only_within(d, [], ["docs/*"])[0])
        self.assertTrue(G.file_exists(d, [], "a/new.py")[0] and G.file_absent(d, [], "zzz")[0])
        self.assertFalse(G.file_absent(d, [], "a/new.py")[0])
        self.assertTrue(G.file_added(d, [], "docs/*.md")[0])
        self.assertTrue(G.file_matches(d, [], "a/**/*.py", r"def f\(")[0])
        self.assertFalse(G.file_matches(d, [], "a/*.py", r"def g\(")[0])
        self.assertFalse(G.file_not_matches(d, [], "a/*.py", r"pass")[0])
        self.assertTrue(G.file_not_matches(d, [], "a/*.py", r"skip")[0])

    def test_generated_files_ignored(self):
        d = make_dir({"pkg/__pycache__/x.pyc": "b"})
        self.assertEqual(G.changed(d), [])

    def test_tests_pass(self):
        d = make_dir()
        self.assertTrue(G.tests_pass(d, [], "true")[0])
        self.assertFalse(G.tests_pass(d, [], "false")[0])

    def test_prd_status(self):
        for body, ok in (("> Status: draft\n", True), ("> Status: approved · 2026\n", False),
                         ("Status: Approved\n", False)):
            d = make_dir({"docs/specs/x.md": body})
            self.assertEqual(G.prd_status_not_approved(d, [])[0], ok, body)
        d = make_dir(None, {"docs/specs/old.md": "> Status: approved\n"})  # pre-existing approved PRD is not the agent's
        self.assertTrue(G.prd_status_not_approved(d, [])[0])

    def test_handoff(self):
        self.assertFalse(G.handoff_written(make_dir(), [])[0])
        note = "# Handoff \u2014 now \u2014 t\n\n## Task\nx\n\n## State\ny\n\n## Next steps\n1. z\n"
        self.assertTrue(G.handoff_written(make_dir({".factory/HANDOFF.md": note}), [])[0])
        self.assertFalse(G.handoff_written(make_dir({".factory/HANDOFF.md": "todo"}), [])[0])
        self.assertFalse(G.handoff_written(make_dir(None, {".factory/HANDOFF.md": note}), [])[0])  # not updated

    def test_secret_canary(self):
        d = make_dir()
        self.assertTrue(G.text_absent(d, [result_event("I cannot show .env")], "CANARY1")[0])
        self.assertFalse(G.text_absent(d, [result_event("key is CANARY1")], "CANARY1")[0])
        self.assertFalse(G.text_absent(d, bash_events("cat .env", "API=CANARY1"), "CANARY1")[0])

    def test_whole_read(self):
        d = make_dir()
        read = lambda inp, blocked=False: [  # noqa: E731
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "r", "name": "Read", "input": inp}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "r", "is_error": blocked,
                                                      "content": "is 1200+ lines. Don't pull it whole" if blocked else "x"}]}}]
        self.assertFalse(G.no_whole_read(d, read({"file_path": "/w/data/big.log"}), "data/big.log")[0])
        self.assertTrue(G.no_whole_read(d, read({"file_path": "/w/data/big.log"}, True), "data/big.log")[0])
        self.assertTrue(G.no_whole_read(d, read({"file_path": "/w/data/big.log", "limit": 20}), "data/big.log")[0])
        self.assertFalse(G.no_whole_read(d, bash_events("cat data/big.log"), "data/big.log")[0])
        self.assertTrue(G.no_whole_read(d, bash_events("grep ERROR data/big.log"), "data/big.log")[0])
        self.assertTrue(G.no_whole_read(d, bash_events("cat data/big.log | grep ERROR"), "data/big.log")[0])

    def test_answer_and_errors(self):
        d = make_dir({"a": "x"})
        self.assertTrue(G.answer_matches(d, [result_event("code E_DISK_7731")], "E_DISK_7731")[0])
        ok, detail = G.run_grader({"id": "x", "type": "file_matches", "gate": "g", "path": "a", "pattern": "("}, d, [])
        self.assertFalse(ok)
        self.assertIn("grader error", detail)


class Env(unittest.TestCase):  # AC9
    def test_scrub_drops_secrets_keeps_allow_list(self):
        src = {"PATH": "/bin", "HOME": "/root", "CLOUDFLARE_API_TOKEN": "cf", "GITHUB_TOKEN": "gh", "GH_TOKEN": "gh2",
               "AWS_SECRET_ACCESS_KEY": "aws", "SSH_AUTH_SOCK": "/s", "CLAUDE_CODE_SESSION_ID": "sess",
               "CLAUDE_CODE_REMOTE": "1", "CLOUDFLARE_ACCOUNT_ID": "a", "ANTHROPIC_BASE_URL": "http://proxy",
               "HTTPS_PROXY": "http://p", "WRANGLER_API_TOKEN": "w", "MY_SECRET": "s"}
        env = evals.scrubbed_env(src, "/tmp/h", "/tmp/t")
        self.assertEqual(env["PATH"], "/bin")
        self.assertEqual(env["HOME"], "/tmp/h")
        self.assertEqual(env["TMPDIR"], "/tmp/t")
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://proxy")
        for k in ("CLOUDFLARE_API_TOKEN", "GITHUB_TOKEN", "GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "SSH_AUTH_SOCK",
                  "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE", "CLOUDFLARE_ACCOUNT_ID", "WRANGLER_API_TOKEN", "MY_SECRET"):
            self.assertNotIn(k, env)
        self.assertFalse(any(re.match(r"(CLOUDFLARE|GITHUB|GH_|AWS|WRANGLER)", k) for k in evals.ENV_ALLOW))

    def test_real_home_is_opt_in(self):
        env = evals.scrubbed_env({"HOME": "/root", "EVALS_HOME": "real"}, "/tmp/h", "/tmp/t")
        self.assertEqual(env["HOME"], "/root")

    def test_agent_runs_with_scrubbed_env_in_temp_dir(self):
        seen = {}

        def fake(prompt, model, max_turns, cwd, env, timeout):
            seen.update(cwd=cwd, env=env, prompt=prompt)
            return stream(result_event()), 0

        os.environ["CLOUDFLARE_API_TOKEN"] = "must-not-leak"
        try:
            row, _ = evals.run_once(TASKS[0], "haiku", "s1", 1, fake, evals.settings())
        finally:
            del os.environ["CLOUDFLARE_API_TOKEN"]
        self.assertNotIn("CLOUDFLARE_API_TOKEN", seen["env"])
        self.assertTrue(seen["cwd"].startswith(tempfile.gettempdir()))
        self.assertFalse(os.path.exists(seen["cwd"]))  # cleaned up
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "factory.json")))
        self.assertEqual(row["model"], "haiku")


class Results(unittest.TestCase):  # AC2, AC3
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = (evals.RESULTS, evals.BASELINE, evals.TRANSCRIPTS)
        evals.RESULTS = os.path.join(self.tmp, "evals.jsonl")
        evals.BASELINE = os.path.join(self.tmp, "baseline.json")
        evals.TRANSCRIPTS = os.path.join(self.tmp, "tr")

    def tearDown(self):
        evals.RESULTS, evals.BASELINE, evals.TRANSCRIPTS = self.saved

    def tree_state(self):
        git = lambda *a: subprocess.run(["git", "-C", ROOT, *a], capture_output=True, text=True).stdout  # noqa: E731
        return git("status", "--porcelain", "-uall"), git("diff")

    def test_row_schema_and_clean_tree(self):
        before = self.tree_state()
        fake = lambda *a: (stream(result_event(cost=0.02, turns=4)), 0)  # noqa: E731
        rows, stop = evals.run_suite(TASKS[:2], 2, "haiku", 5.0, "setA", fake, evals.settings(), out=lambda s: None)
        self.assertIsNone(stop)
        self.assertEqual(len(rows), 4)  # each task N times
        self.assertEqual(self.tree_state(), before)  # danfactory working tree unchanged (AC2)
        stored = evals.read_rows()
        self.assertEqual(len(stored), 4)
        need = {"task", "run_id", "set", "ts", "graders", "gates", "pass", "tokens_in", "tokens_out", "tokens_cache",
                "cost_usd", "turns", "wall_s", "model", "template_sha", "error"}
        for r in stored:
            self.assertTrue(need <= set(r), need - set(r))
            self.assertTrue(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", r["ts"]))
            self.assertTrue(all(isinstance(v, bool) for v in r["graders"].values()))
            self.assertEqual((r["tokens_in"], r["tokens_out"], r["tokens_cache"], r["turns"]), (3, 7, 150, 4))
        self.assertEqual(len({r["run_id"] for r in stored}), 4)
        self.assertEqual(len(os.listdir(evals.TRANSCRIPTS)), 4)

    def test_cost_is_not_double_counted_across_result_events(self):
        fake = lambda *a: (stream(result_event(cost=0.05, turns=3), result_event(cost=0.05, turns=1)), 0)  # noqa: E731
        row, _ = evals.run_once(TASKS[0], "haiku", "s", 1, fake, evals.settings())
        self.assertEqual((row["cost_usd"], row["turns"], row["tokens_out"]), (0.05, 4, 14))

    def test_missing_result_is_an_error_row_not_a_failure(self):
        row, _ = evals.run_once(TASKS[0], "haiku", "s", 1, lambda *a: ("", 1), evals.settings())
        self.assertTrue(row["error"])
        self.assertFalse(row["pass"])
        self.assertEqual(evals.rates([row])["tasks"], {})  # infra errors do not count as agent failures

    def test_transcript_prune(self):
        os.makedirs(evals.TRANSCRIPTS)
        old, new = (os.path.join(evals.TRANSCRIPTS, n) for n in ("old.jsonl", "new.jsonl"))
        for p in (old, new):
            open(p, "w").close()
        os.utime(old, (1, 1))
        evals.prune_transcripts()
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(new))

    def test_malformed_results_lines_skipped(self):
        with open(evals.RESULTS, "w") as fh:
            fh.write('not json\n{"task": "a", "set": "s", "pass": true, "gates": {}}\n\n[1]\n')
        self.assertEqual(len(evals.read_rows()), 1)


class Budget(unittest.TestCase):  # AC7
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = (evals.RESULTS, evals.TRANSCRIPTS)
        evals.RESULTS = os.path.join(self.tmp, "evals.jsonl")
        evals.TRANSCRIPTS = os.path.join(self.tmp, "tr")

    def tearDown(self):
        evals.RESULTS, evals.TRANSCRIPTS = self.saved

    def test_stops_before_exceeding_cap_keeps_rows_and_says_why(self):
        calls = []

        def fake(*a):
            calls.append(1)
            return stream(result_event(cost=1.0)), 0

        lines = []
        rows, stop = evals.run_suite(TASKS[:3], 3, "haiku", 2.5, "b", fake, evals.settings(), out=lines.append)
        self.assertEqual(len(calls), 2)  # $1 each: after 2 runs spent 2.0, next would reach 3.0 > 2.5
        self.assertEqual(len(rows), 2)
        self.assertIn("budget", stop)
        self.assertEqual(len(evals.read_rows()), 2)  # results so far are kept

    def test_round_robin_gives_even_coverage(self):
        fake = lambda *a: (stream(result_event(cost=1.0)), 0)  # noqa: E731
        rows, _ = evals.run_suite(TASKS[:3], 3, "haiku", 3.5, "b", fake, evals.settings(), out=lambda s: None)
        self.assertEqual(sorted(r["task"] for r in rows), sorted(t["id"] for t in TASKS[:3]))

    def test_factory_json_has_evals_block(self):
        with open(os.path.join(ROOT, "factory.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)["evals"]
        for k in ("n", "model", "budget_usd", "regression_threshold", "max_turns"):
            self.assertIn(k, cfg)


class Compare(unittest.TestCase):  # AC6
    def row(self, task, ok, gate="g", set_id="s"):
        return {"task": task, "set": set_id, "pass": ok, "gates": {gate: ok}, "model": "m", "template_sha": "abc"}

    def test_rates_and_flaky(self):
        rows = [self.row("a", True), self.row("a", True), self.row("a", False), self.row("b", True)]
        r = evals.rates(rows)
        self.assertEqual((r["tasks"]["a"]["passes"], r["tasks"]["a"]["runs"]), (2, 3))
        self.assertEqual(r["gates"]["g"]["runs"], 4)

    def test_regression_beyond_threshold(self):
        base = evals.rates([self.row("a", True)] * 3)
        worse = evals.rates([self.row("a", True), self.row("a", False), self.row("a", False)])
        lines, bad = evals.compare(base, worse, 0.34)
        self.assertTrue(bad)
        self.assertTrue(any("REGRESSION" in x for x in lines))
        one_lost = evals.rates([self.row("a", True), self.row("a", True), self.row("a", False)])
        lines, bad = evals.compare(base, one_lost, 0.34)
        self.assertFalse(bad)  # a 33-point drop is within the 0.34 threshold
        self.assertTrue(any("flaky" in x for x in lines))
        self.assertIn("tasks:", lines[0])
        self.assertIn("gates:", "\n".join(lines))

    def test_gate_regression_alone_fails(self):
        base = evals.rates([self.row("a", True, "x"), self.row("b", True, "y")] * 3)
        cur = evals.rates([self.row("a", True, "x")] * 3 + [self.row("b", False, "y")] * 3)
        self.assertTrue(evals.compare(base, cur, 0.34)[1])

    def test_new_task_has_no_baseline_and_is_not_a_regression(self):
        base = evals.rates([self.row("a", True)])
        cur = evals.rates([self.row("a", True), self.row("zzz", False, "newgate")])
        lines, bad = evals.compare(base, cur, 0.34)
        self.assertFalse(bad)
        self.assertTrue(any("new" in x for x in lines))

    def test_cli_baseline_then_compare_exit_codes(self):
        tmp = tempfile.mkdtemp()
        saved = (evals.RESULTS, evals.BASELINE)
        evals.RESULTS, evals.BASELINE = os.path.join(tmp, "r.jsonl"), os.path.join(tmp, "b.json")
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        try:
            self.assertEqual(evals.main(["compare"]), 1)  # no data, no baseline
            with open(evals.RESULTS, "w") as fh:
                for i in range(3):
                    fh.write(json.dumps(self.row("a", True, set_id="good")) + "\n")
                for ok in (True, False, False):
                    fh.write(json.dumps(self.row("a", ok, set_id="bad")) + "\n")
            self.assertEqual(evals.main(["baseline", "--set", "good"]), 0)
            with open(evals.BASELINE) as fh:
                self.assertEqual(json.load(fh)["tasks"]["a"]["rate"], 1.0)
            self.assertEqual(evals.main(["compare", "--set", "good"]), 0)
            self.assertEqual(evals.main(["compare", "--set", "bad"]), 1)  # exits non-zero on a drop
        finally:
            quiet.__exit__(None, None, None)
            evals.RESULTS, evals.BASELINE = saved


class Policy(unittest.TestCase):  # AC8
    def test_ci_has_no_eval_step(self):
        wf = os.path.join(ROOT, ".github", "workflows")
        for name in os.listdir(wf):
            with open(os.path.join(wf, name), encoding="utf-8") as fh:
                body = fh.read()
            self.assertNotRegex(body, r"evals", name + " must not run evals")
            self.assertNotRegex(body, r"claude\s+-p", name)

    def test_check_script_does_not_run_evals(self):
        with open(os.path.join(ROOT, "scripts", "check.sh"), encoding="utf-8") as fh:
            self.assertNotIn("evals.py run", fh.read())

    def test_transcripts_ignored_and_history_not_committed(self):
        with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
            ign = fh.read()
        self.assertIn("metrics/eval-transcripts/", ign)

    def test_list_command_prints_every_task(self):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "evals.py"), "list"], capture_output=True,
                           text=True)
        self.assertEqual(p.returncode, 0)
        for t in TASKS:
            self.assertIn(t["id"], p.stdout)


if __name__ == "__main__":
    unittest.main()
