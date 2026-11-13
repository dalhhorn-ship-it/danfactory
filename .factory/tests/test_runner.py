"""Fixer runner (AUTO-4, ADR 0009): scripts/runner.py, scripts/sandbox.py, issues.py blocked state, acceptance.py
second-reading, dashboard Runner block. No test calls a model: a fake `claude` executable placed first on PATH edits files and
prints stream-json (with a cost) according to a plan file. Temp git projects; no network."""
import contextlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import acceptance  # noqa: E402
import evals  # noqa: E402
import issues  # noqa: E402
import runner  # noqa: E402
import sandbox  # noqa: E402
from obs import tab_autonomy  # noqa: E402

FAKE = r'''#!/usr/bin/env python3
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
plan = json.load(open(os.path.join(here, "plan.json")))
prompt = sys.stdin.read()
argv = sys.argv[1:]
tools = argv[argv.index("--allowedTools") + 1] if "--allowedTools" in argv else ""
role = "review" if tools == "Read,Glob,Grep" else "second" if "THROWAWAY reference" in prompt else "fixer"
sp = os.path.join(here, "state.json")
state = json.load(open(sp)) if os.path.exists(sp) else {}
n = state.get(role, 0)
state[role] = n + 1
json.dump(state, open(sp, "w"))
steps = plan.get(role) or [{}]
step = steps[min(n, len(steps) - 1)]
with open(os.path.join(here, "calls.jsonl"), "a") as fh:
    fh.write(json.dumps({"role": role, "cwd": os.getcwd(), "env": dict(os.environ), "prompt": prompt, "argv": argv}) + "\n")
for rel, text in (step.get("write") or {}).items():
    p = os.path.join(os.getcwd(), rel)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    open(p, "w").write(text)
if step.get("commit"):
    import subprocess
    subprocess.run(["git", "-c", "user.name=x", "-c", "user.email=x@x", "add", "-A"], check=True)
    subprocess.run(["git", "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-q", "-m", "fixer own commit\n\n" + step["commit"]], check=True)
if step.get("no_result"):
    sys.exit(1)
print(json.dumps({"type": "result", "subtype": "success", "result": step.get("text", "done"), "total_cost_usd": step.get("cost", 0.1),
                  "num_turns": 2, "usage": {"input_tokens": 10, "cache_creation_input_tokens": 5, "cache_read_input_tokens": 5, "output_tokens": 7}}))
'''

PRD = "# PRD: Demo\n\n> Status: %s · Approved: 2026-11-12 · Backlog: X-1\n\n## Acceptance criteria\n1. shout upper-cases and adds a bang\n"
TEST = '''import unittest


class T(unittest.TestCase):
    def test_c1_shout(self):
        from textkit import shout
        self.assertEqual(shout("a"), "A!")
'''
GOOD = 'def shout(s):\n    return s.upper() + "!"\n'
BAD = 'def shout(s):\n    return s\n'
SHIP = "Reads well.\nVERDICT: ship"
FIXFIRST = "It special-cases the test input.\nVERDICT: fix-first"
OFFSIDE = {"CLOUDFLARE_API_TOKEN": "cf-canary", "GITHUB_TOKEN": "gh-canary", "AWS_SECRET_ACCESS_KEY": "aws-canary",
           "EVALS_SANDBOX": "off"}


def rd(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def wr(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def sh(cwd, *a):
    p = subprocess.run(["git", "-c", "user.name=t0", "-c", "user.email=t0@t0", "-c", "commit.gpgsign=false"] + list(a), cwd=cwd,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


class Env:
    """A temp project with an admitted failing acceptance test and one open issue, plus a fake claude."""

    def __init__(self, plan, autonomy=None, admit=True, issue=True, approved=True):
        self.root = tempfile.mkdtemp()
        self.bin = tempfile.mkdtemp()
        self.write("factory.json", json.dumps({"autonomy": dict({"enabled": True, "max_attempts": 3, "daily_budget_usd": 5, "run_budget_usd": 2},
                                                                 **(autonomy or {}))}))
        os.makedirs(os.path.join(self.root, "scripts"))
        shutil.copy(os.path.join(ROOT, "scripts", "acceptance.py"), os.path.join(self.root, "scripts", "acceptance.py"))
        self.write("docs/specs/demo.md", PRD % ("approved" if approved else "draft"))
        self.write("textkit/__init__.py", '"""textkit."""\n')
        self.write("tests/acceptance/demo/test_demo.py", TEST)
        self.write(".gitignore", "__pycache__/\n.claude/worktrees/\n")
        sh(self.root, "init", "-q", "-b", "main")
        if admit:
            with contextlib.redirect_stdout(io.StringIO()):
                acceptance.main(["map", "demo"], self.root)
                acceptance.main(["admit", "demo"], self.root)
        if issue:
            with contextlib.redirect_stdout(io.StringIO()):
                issues.main(["--root", self.root, "find"])
        sh(self.root, "add", "-A")
        sh(self.root, "commit", "-q", "-m", "base")
        self.main_sha = sh(self.root, "rev-parse", "HEAD")
        self.set_plan(plan)
        p = os.path.join(self.bin, "claude")
        with open(p, "w") as fh:
            fh.write(FAKE)
        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def set_plan(self, plan):
        with open(os.path.join(self.bin, "plan.json"), "w") as fh:
            json.dump(plan, fh)

    def run(self, *args):
        env = dict(OFFSIDE, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""))
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = runner.main(["--root", self.root] + list(args))
        return rc, out.getvalue() + err.getvalue()

    def calls(self, role=None):
        p = os.path.join(self.bin, "calls.jsonl")
        if not os.path.exists(p):
            return []
        rows = [json.loads(x) for x in rd(p).splitlines()]
        return [r for r in rows if role is None or r["role"] == role]

    def staged(self, path):
        p = subprocess.run(["git", "show", "staging:" + path], cwd=self.root, capture_output=True, text=True)
        return p.stdout if p.returncode == 0 else None

    def staging_files(self, prefix):
        return sh(self.root, "ls-tree", "-r", "--name-only", "staging", "--", prefix).splitlines()

    def rows(self):
        return [json.loads(x) for x in (self.staged("metrics/runner.jsonl") or "").splitlines()]

    def cleanup(self):
        sh(self.root, "worktree", "prune")
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.bin, ignore_errors=True)


FIX = {"fixer": [{"write": {"textkit/__init__.py": GOOD, ".env": "", "package.json": "", "keep/__init__.py": ""}, "cost": 0.3}], "review": [{"text": SHIP, "cost": 0.1}]}


class Pass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Env(FIX)
        cls.home = os.environ.get("HOME", "")
        cls.rc, cls.out = cls.e.run("run", "--next")

    @classmethod
    def tearDownClass(cls):
        cls.e.cleanup()

    def test_merged_to_staging_and_issue_fixed(self):
        e = self.e
        self.assertEqual(self.rc, 0, self.out)
        self.assertEqual(e.staged("textkit/__init__.py"), GOOD)
        self.assertEqual(len(e.staging_files("issues/fixed")), 1)
        self.assertEqual(e.staging_files("issues/open"), [])
        merge = sh(e.root, "log", "staging", "--merges", "-1", "--format=%P")
        self.assertEqual(len(merge.split()), 2, "merge --no-ff")
        rows = e.rows()
        self.assertEqual([(r["kind"], r["attempt"], r["outcome"], r["gate"], r["review"]) for r in rows], [("attempt", 1, "merged", "pass", "ship")])
        self.assertAlmostEqual(rows[0]["cost_usd"], 0.4)
        self.assertEqual(rows[0]["tokens_cache"], 10)
        self.assertEqual(sh(e.root, "worktree", "list").count("\n"), 0, "worktrees removed")

    def test_empty_sandbox_mount_files_are_not_committed(self):  # found in the smoke run: bwrap leaves them in the cwd
        self.assertIsNone(self.e.staged(".env"))
        self.assertIsNone(self.e.staged("package.json"))
        self.assertEqual(self.e.staged("keep/__init__.py"), "", "an empty file the fixer meant to add stays")

    def test_trailers_are_the_runners(self):
        msg = sh(self.e.root, "log", "staging", "--no-merges", "--grep=Fixer-Attempt", "-1", "--format=%B")
        for t in ("Refs: ISS-0001", "Fixer-Attempt: 1", "Runner: ", "Review: ship"):
            self.assertIn(t, msg)
        self.assertNotIn("Acceptance-Change", msg)

    def test_production_branch_and_project_tree_untouched(self):  # AC10: the project tree is written only by a merge
        e = self.e
        self.assertEqual(sh(e.root, "rev-parse", "main"), e.main_sha)
        self.assertEqual(sh(e.root, "status", "--porcelain"), "")
        with open(os.path.join(e.root, "textkit", "__init__.py")) as fh:
            self.assertNotIn("shout", fh.read())

    def test_fixer_environment_is_scrubbed(self):  # AC10
        call = self.e.calls("fixer")[0]
        env = call["env"]
        for k in ("CLOUDFLARE_API_TOKEN", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY"):
            self.assertNotIn(k, env)
        self.assertNotEqual(env["HOME"], self.home)
        self.assertFalse(os.path.abspath(env["HOME"]).startswith(os.path.abspath(self.e.root)))
        self.assertFalse(os.path.exists(env["HOME"]), "throwaway home is removed")
        self.assertTrue(call["cwd"].endswith(os.path.join(".claude", "worktrees", "runner-ISS-0001")) or "runner-ISS-0001" in call["cwd"])
        self.assertNotEqual(os.path.realpath(call["cwd"]), os.path.realpath(self.e.root))
        self.assertIn("--no-session-persistence", call["argv"])

    def test_reviewer_is_read_only_and_separate(self):
        rv = self.e.calls("review")[0]
        self.assertEqual(rv["argv"][rv["argv"].index("--allowedTools") + 1], "Read,Glob,Grep")
        self.assertIn("shout", rv["prompt"])

    def test_status_and_dashboard(self):
        st = runner.summary(self.e.root)
        self.assertEqual((st["runs"], st["attempts"], st["fixed"]), (1, 1, 1))
        self.assertEqual(st["first_try_rate"], 1.0)
        self.assertEqual(st["rework_per_fixed"], 0.0)
        self.assertAlmostEqual(st["cost_per_fixed"], 0.4)
        self.assertAlmostEqual(st["spend_today"], 0.4)
        self.assertEqual(st["staging_lead"], 3)  # fix, merge and ledger commit are not on main yet
        data = tab_autonomy.collect(self.e.root, {})
        html = tab_autonomy.render(data)
        self.assertIn("<h2>Runner</h2>", html)
        self.assertIn("$0.40 / $5.00", html)
        self.assertIn("runner: 1 fixed", tab_autonomy.line(data))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(runner.main(["--root", self.e.root, "status"]), 0)
        self.assertIn("1 issue(s) fixed", out.getvalue())


class Fail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Env({"fixer": [{"write": {"textkit/__init__.py": BAD}, "cost": 0.2}], "review": [{"text": SHIP}]})
        cls.rc, cls.out = cls.e.run("run", "--issue", "ISS-0001")

    @classmethod
    def tearDownClass(cls):
        cls.e.cleanup()

    def test_ac8_parked_after_cap_and_nothing_merged(self):
        e = self.e
        self.assertEqual(self.rc, 1, self.out)
        self.assertEqual(len(e.calls("fixer")), 3)
        self.assertEqual(e.calls("review"), [], "no review money spent while the issue's own tests fail")
        self.assertEqual(len(e.staging_files("issues/blocked")), 1)
        self.assertEqual(e.staging_files("issues/open"), [])
        self.assertEqual(sh(e.root, "diff", "--stat", "main", "staging", "--", "textkit", "tests", "docs", "factory.json"), "", "no code merged")
        self.assertEqual(sh(e.root, "log", "staging", "--merges", "--format=%s"), "")
        self.assertEqual(sh(e.root, "rev-parse", "main"), e.main_sha)
        log = e.staged(e.staging_files("issues/blocked")[0])
        self.assertIn("## Attempt log", log)
        self.assertIn("attempt 3", log)
        self.assertIn("issue-not-fixed", log)

    def test_rows_and_rework_prompt(self):
        e = self.e
        rows = e.rows()
        self.assertEqual([r["kind"] for r in rows], ["attempt", "attempt", "attempt", "park"])
        self.assertTrue(all(r["codes"] == ["issue-not-fixed"] for r in rows[:3]))
        self.assertNotIn("Previous attempt", e.calls("fixer")[0]["prompt"])
        self.assertIn("issue tests still failing", e.calls("fixer")[1]["prompt"])

    def test_dashboard_lists_parked(self):
        st = runner.summary(self.e.root)
        self.assertEqual([p["id"] for p in st["parked"]], ["ISS-0001"])
        self.assertEqual(st["parked"][0]["codes"], ["issue-not-fixed"])
        self.assertEqual(st["fixed"], 0)
        self.assertIn("ISS-0001", tab_autonomy.render(tab_autonomy.collect(self.e.root, {})))

    def test_z_unpark_requeues(self):
        rc, out = self.e.run("run", "--issue", "ISS-0001")
        self.assertEqual(rc, 2)
        self.assertIn("parked", out)
        rc, out = self.e.run("unpark", "ISS-0001")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(self.e.staging_files("issues/open")), 1)
        self.assertEqual(self.e.staging_files("issues/blocked"), [])
        self.assertEqual(sh(self.e.root, "status", "--porcelain"), "")


class Rework(unittest.TestCase):
    def test_review_fix_first_then_ship_and_protected_revert(self):
        evil = "# tampered\n"
        e = Env({"fixer": [{"write": {"textkit/__init__.py": GOOD, "tests/acceptance/demo/test_demo.py": evil}},
                           {"write": {"textkit/__init__.py": GOOD}, "commit": "Acceptance-Change: demo\nReview: ship"},
                           {"write": {"textkit/__init__.py": GOOD + "\n"}}, {"write": {"textkit/__init__.py": GOOD + "\n\n"}}],
                 "review": [{"text": "Hard-coded.\nVERDICT: fix-first"}, {"text": "no verdict line at all"}, {"text": SHIP}]},
                {"max_attempts": 4})
        try:
            rc, out = e.run("run", "--next")
            self.assertEqual(rc, 0, out)
            rows = e.rows()
            self.assertEqual([r["attempt"] for r in rows], [1, 2, 3, 4])
            self.assertEqual(rows[0]["codes"], ["fixer-touched-protected"])
            self.assertEqual(rows[0]["review"], "-")
            self.assertEqual(rows[1]["review"], "fix-first")
            self.assertIn("review-fix-first", rows[1]["codes"])
            self.assertIn("review-unparsed", rows[2]["codes"])
            self.assertEqual(rows[2]["review"], "fix-first")
            self.assertEqual((rows[3]["gate"], rows[3]["review"], rows[3]["outcome"]), ("pass", "ship", "merged"))
            self.assertEqual(e.staged("tests/acceptance/demo/test_demo.py"), TEST, "protected change reverted")
            msgs = sh(e.root, "log", "staging", "--no-merges", "--format=%B")
            self.assertNotIn("Acceptance-Change", msgs)
            self.assertNotIn("fixer own commit", msgs, "a commit the fixer made itself is squashed into the runner's commit")
            self.assertEqual(msgs.count("Review: ship"), 1)
            self.assertIn("protected paths", e.calls("fixer")[1]["prompt"])
            self.assertIn("reviewer said fix-first", e.calls("fixer")[2]["prompt"])
            self.assertIn("Hard-coded", e.calls("fixer")[2]["prompt"])
        finally:
            e.cleanup()

    def test_fixer_without_result_and_without_change_fail_the_attempt(self):
        e = Env({"fixer": [{"no_result": True}, {}]}, {"max_attempts": 2})
        try:
            rc, out = e.run("run", "--next")
            self.assertEqual(rc, 1, out)
            self.assertEqual([r["codes"] for r in e.rows() if r["kind"] == "attempt"], [["fixer-error"], ["no-change"]])
        finally:
            e.cleanup()


class Budget(unittest.TestCase):
    def test_ac9_run_cap_stops_before_the_next_attempt(self):
        e = Env({"fixer": [{"write": {"textkit/__init__.py": BAD}, "cost": 1.5}]})
        try:
            rc, out = e.run("run", "--next")
            self.assertEqual(rc, 3, out)
            self.assertIn("run budget", out)
            self.assertEqual(len(e.calls("fixer")), 1)
            rows = e.rows()
            self.assertEqual([r["kind"] for r in rows], ["attempt", "stop"], "results so far are kept")
            self.assertEqual(e.staging_files("issues/blocked"), [])
            self.assertEqual(len(e.staging_files("issues/open")), 1, "stopped, not parked")
            self.assertEqual(sh(e.root, "rev-parse", "main"), e.main_sha)
        finally:
            e.cleanup()

    def test_ac9_daily_cap_stops_before_any_work(self):
        e = Env(FIX)
        try:
            ts = runner.now()
            e.write("metrics/runner.jsonl", json.dumps({"ts": ts, "kind": "attempt", "run": "old", "issue": "ISS-0009", "attempt": 1,
                                                        "cost_usd": 4.9, "outcome": "fail", "codes": []}) + "\n")
            sh(e.root, "add", "-A")
            sh(e.root, "commit", "-q", "-m", "earlier spend")
            rc, out = e.run("run", "--next")
            self.assertEqual(rc, 3, out)
            self.assertIn("daily budget", out)
            self.assertEqual(e.calls(), [])
            self.assertEqual(e.staged("textkit/__init__.py"), '"""textkit."""\n')
        finally:
            e.cleanup()

    def test_budget_function(self):
        cfg = dict(runner.DEFAULTS)
        old = [{"ts": "2020-01-01T00:00:00Z", "kind": "attempt", "cost_usd": 0.5, "run": "o"}]
        self.assertIsNone(runner.budget_stop(old, "r", cfg))
        now = [{"ts": runner.now(), "kind": "attempt", "cost_usd": 1.0, "run": "r"}]
        self.assertIsNone(runner.budget_stop(now, "r", cfg))
        self.assertIn("run budget", runner.budget_stop(now + [{"ts": runner.now(), "kind": "attempt", "cost_usd": 1.2, "run": "r"}], "r", cfg))
        self.assertIn("daily budget", runner.budget_stop([{"ts": runner.now(), "kind": "attempt", "cost_usd": 5.0, "run": "z"}], "r", cfg))


class Refusals(unittest.TestCase):
    def refused(self, e, fragment, *args):
        rc, out = e.run(*(args or ("run", "--next")))
        self.assertEqual(rc, 2, out)
        self.assertIn(fragment, out)
        self.assertEqual(e.calls(), [])
        self.assertEqual(sh(e.root, "branch", "--list", "staging"), "", "nothing created")

    def test_autonomy_disabled(self):
        e = Env(FIX, {"enabled": False})
        try:
            self.refused(e, "not enabled")
        finally:
            e.cleanup()

    def test_dirty_tree(self):
        e = Env(FIX)
        try:
            e.write("scratch.txt", "x")
            self.refused(e, "not clean")
        finally:
            e.cleanup()

    def test_prd_not_approved(self):
        e = Env(FIX, approved=False)
        try:
            self.refused(e, "not approved", "run", "--issue", "ISS-0001")
        finally:
            e.cleanup()

    def test_needs_a_target_and_dry_run_spends_nothing(self):
        e = Env(FIX)
        try:
            self.refused(e, "--issue ISS-n or --next", "run")
            rc, out = e.run("run", "--next", "--dry-run")
            self.assertEqual(rc, 0, out)
            self.assertIn("would fix ISS-0001", out)
            self.assertEqual(e.calls(), [])
            self.assertEqual(sh(e.root, "branch", "--list", "staging"), "")
        finally:
            e.cleanup()

    def test_nothing_to_do_without_approved_prd(self):
        e = Env(FIX, approved=False)
        try:
            rc, out = e.run("run", "--next")
            self.assertEqual(rc, 0, out)
            self.assertIn("nothing to do", out)
            self.assertEqual(e.calls(), [])
        finally:
            e.cleanup()


class Ledger(unittest.TestCase):
    def test_block_unpark_status_and_find_keeps_parked_issue(self):
        e = Env(FIX)
        try:
            def cli(*a):
                out = io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                    rc = issues.main(["--root", e.root] + list(a))
                return rc, out.getvalue()
            rc, _ = cli("block", "ISS-0001", "--log", "gave up")
            self.assertEqual(rc, 0)
            self.assertEqual(os.listdir(os.path.join(e.root, "issues", "blocked"))[0][:8], "ISS-0001")
            self.assertEqual(os.listdir(os.path.join(e.root, "issues", "open")), [])
            st = issues.status(e.root)
            self.assertEqual((st["open"], st["blocked"]), (0, 1))
            self.assertEqual(st["blocked_issues"][0]["id"], "ISS-0001")
            self.assertIn("1 blocked", cli("status")[1])
            self.assertEqual(cli("block", "ISS-0001")[0], 2, "only open issues can be blocked")
            before = os.listdir(os.path.join(e.root, "issues", "blocked"))
            self.assertEqual(cli("find")[0], 0)  # the finder must not file a duplicate for a parked issue
            self.assertEqual(os.listdir(os.path.join(e.root, "issues", "blocked")), before)
            self.assertEqual(os.listdir(os.path.join(e.root, "issues", "open")), [])
            self.assertEqual(cli("unpark", "ISS-0001")[0], 0)
            self.assertEqual(issues.status(e.root)["open"], 1)
            self.assertEqual(cli("unpark", "ISS-0001")[0], 2)
        finally:
            e.cleanup()


class Sandbox(unittest.TestCase):
    def test_scrubbed_env_and_command_are_shared_with_evals(self):
        self.assertIs(evals.scrubbed_env, sandbox.scrubbed_env)
        self.assertIs(evals.claude_cmd, sandbox.claude_cmd)
        self.assertIs(evals.ENV_ALLOW, sandbox.ENV_ALLOW)
        src = {"PATH": "/bin", "HOME": "/home/me", "GITHUB_TOKEN": "x", "CLOUDFLARE_API_TOKEN": "y", "ANTHROPIC_API_KEY": "k"}
        env = sandbox.scrubbed_env(src, "/tmp/h", "/tmp/t")
        self.assertEqual((env["HOME"], env["TMPDIR"], env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"]), ("/tmp/h", "/tmp/t", "1"))
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("CLOUDFLARE_API_TOKEN", env)
        self.assertEqual(env["ANTHROPIC_API_KEY"], "k")
        off = sandbox.scrubbed_env(dict(src, EVALS_SANDBOX="off"), "/tmp/h", "/tmp/t")
        self.assertNotIn("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", off)

    def test_problem_and_command(self):
        self.assertIn("bubblewrap", sandbox.sandbox_problem({}, which=lambda t: None, platform="linux"))
        self.assertIsNone(sandbox.sandbox_problem({"EVALS_SANDBOX": "off"}, which=lambda t: None, platform="linux"))
        cmd = sandbox.claude_cmd("haiku", 7, True, sandbox.READ_TOOLS)
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "Read,Glob,Grep")
        self.assertIn("--settings", cmd)
        self.assertNotIn("--settings", sandbox.claude_cmd("haiku", 7, False))

    def test_usage_cost(self):
        ev = sandbox.parse_events('not json\n{"type":"result","total_cost_usd":0.5,"num_turns":2,"usage":{"input_tokens":3,"output_tokens":4}}\n'
                                  '{"type":"result","total_cost_usd":0.9,"num_turns":1,"usage":{"cache_read_input_tokens":6}}\n')
        tok, cost, turns, has = sandbox.usage_cost(ev)
        self.assertEqual((tok, cost, turns, has), ({"tokens_in": 3, "tokens_cache": 6, "tokens_out": 4}, 0.9, 3, True))
        self.assertEqual(sandbox.usage_cost([])[3], False)


class SecondReading(unittest.TestCase):
    def test_agent_reference_admits_the_test_and_cost_is_recorded(self):
        e = Env({"second": [{"write": {"textkit/__init__.py": GOOD}, "cost": 0.25}]}, admit=False, issue=False)
        try:
            env = dict(OFFSIDE, PATH=e.bin + os.pathsep + os.environ.get("PATH", ""))
            out = io.StringIO()
            with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out):
                acceptance.main(["map", "demo"], e.root)
                rc = acceptance.main(["second-reading", "demo", "--model", "haiku"], e.root)
            self.assertEqual(rc, 0, out.getvalue())
            self.assertIn("admitted 1", out.getvalue())
            man = json.loads(rd(os.path.join(e.root, "tests", "acceptance", "manifest.json")))
            self.assertEqual([v["reference"] for v in man["admitted"].values()], ["second-reading"])
            row = json.loads(rd(os.path.join(e.root, "metrics", "runner.jsonl")).splitlines()[-1])
            self.assertEqual((row["kind"], row["slug"], row["cost_usd"], row["model"]), ("second-reading", "demo", 0.25, "haiku"))
            call = e.calls("second")[0]
            self.assertIn("--model", call["argv"])
            self.assertNotIn("GITHUB_TOKEN", call["env"])
            self.assertNotIn("shout", call["prompt"].split("LAYOUT.txt (public layout")[1], "the layout shows names that exist, not the missing function")
            self.assertEqual(rd(os.path.join(e.root, "textkit", "__init__.py")), '"""textkit."""\n', "the project is not written")
            self.assertNotEqual(os.path.dirname(call["cwd"]), e.root)
            self.assertFalse(os.path.exists(call["cwd"]), "the throwaway directory is deleted")
        finally:
            e.cleanup()

    def test_public_layout_hides_bodies_tests_and_docs(self):
        d = tempfile.mkdtemp()
        try:
            for rel, text in (("pkg/core.py", "def pub(a, b):\n    secret_body = 1\n\ndef _priv():\n    pass\n\nclass K:\n    pass\n"),
                              ("tests/test_x.py", "def test_x(): pass\n"), ("docs/a.md", "x"), ("README.md", "x")):
                p = os.path.join(d, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                wr(p, text)
            lay = acceptance.public_layout(d)
            self.assertIn("pkg/core.py", lay)
            self.assertIn("def pub(a, b)", lay)
            self.assertIn("class K", lay)
            for bad in ("secret_body", "_priv", "test_x", "docs", "README"):
                self.assertNotIn(bad, lay)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class Empty(unittest.TestCase):
    def test_empty_state(self):
        d = tempfile.mkdtemp()
        try:
            sh(d, "init", "-q")
            sh(d, "commit", "-q", "--allow-empty", "-m", "i")
            data = tab_autonomy.collect(d, {})
            self.assertFalse(data["runner"]["exists"])
            self.assertIn("No runner activity yet", tab_autonomy.render(data))
            self.assertEqual(tab_autonomy.line(data), "no issue ledger yet")
            self.assertIn("No runner activity yet", runner.human(runner.summary(d)))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
