"""Mission Stop hook (MISSION-2, docs/specs/mission-autopilot.md criteria 5-7, 12; ADR 0012).
Real mission files in temp git repos, the real hook as a subprocess. No network, no model."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOOKS = os.path.join(ROOT, ".claude", "hooks")
HOOK = os.path.join(HOOKS, "mission_stop.py")
NOW = datetime.datetime.now(datetime.timezone.utc)

MISSION = """# Mission: demo

<!-- mission:start -->
slug: demo
status: {status}
go: "go, build the demo"
date: {date}
started_at: {started}
branch: mission/demo
milestone: M5
features: 5
caps: usd={usd} hours={hours} continuations={conts}
scope_in: demo-*
scope_out: everything else
<!-- mission:end -->

## Brief
Build the demo. Reply go to start.

## Decision log
"""


def usage_line(mid, model, tokens):
    return json.dumps({"type": "assistant", "uuid": "u-" + mid, "message": {
        "id": mid, "model": model, "usage": {"input_tokens": tokens, "output_tokens": 0,
                                             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}})


class Proj:
    def __init__(self, items="- [~] DEMO-1 First thing (docs/specs/demo-one.md)\n- [ ] DEMO-2 Second\n",
                 status="active", usd=15, hours=10, conts=40, age_hours=1, branch="mission/demo", mission=True):
        self.root = tempfile.mkdtemp()
        started = (NOW - datetime.timedelta(hours=age_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.write("factory.json", json.dumps({"phase": "build"}))
        self.write("docs/BACKLOG.md", "# Backlog\n\n## M1\n- [x] OLD-1 Old\n\n"
                   "## Milestone: M5 — Demo (mission: demo)\n" + items)
        if mission:
            self.write("docs/missions/demo.md", MISSION.format(status=status, usd=usd, hours=hours, conts=conts,
                                                               started=started, date=started[:10]))
        self.g("init", "-q", "-b", "main")
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "start")
        if branch != "main":
            self.g("checkout", "-q", "-b", branch)

    def g(self, *a):
        p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
                           + list(a), cwd=self.root, capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        return p.stdout

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def state(self):
        try:
            with open(os.path.join(self.root, ".factory", "mission-state.json"), encoding="utf-8") as fh:
                return json.load(fh)
        except OSError:
            return None

    def header(self, key):
        with open(os.path.join(self.root, "docs", "missions", "demo.md"), encoding="utf-8") as fh:
            for ln in fh:
                if ln.startswith(key + ":"):
                    return ln.split(":", 1)[1].strip()

    def transcript(self, sid="s1", model="claude-opus-4", tokens=1_000_000, sub_tokens=0):
        d = os.path.join(self.root, "tx")
        os.makedirs(os.path.join(d, sid, "subagents"), exist_ok=True)
        path = os.path.join(d, sid + ".jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(usage_line("m1", model, tokens) + "\n")
        if sub_tokens:
            with open(os.path.join(d, sid, "subagents", "a.jsonl"), "w", encoding="utf-8") as fh:
                fh.write(usage_line("s1", model, sub_tokens) + "\n")
        return path

    def stop(self, hook=HOOK, **ev):
        ev.setdefault("session_id", "s1")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.root)
        return subprocess.run([sys.executable, "-B", hook], input=json.dumps(ev), capture_output=True,
                              text=True, env=env, cwd=self.root)


class Base(unittest.TestCase):
    def proj(self, **kw):
        p = Proj(**kw)
        self.addCleanup(shutil.rmtree, p.root, True)
        return p

    def blocked(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def silent(self, r):
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))


class NoOps(Base):
    def test_no_mission_is_silent_and_writes_nothing(self):
        p = self.proj(mission=False)
        self.silent(p.stop())
        self.assertIsNone(p.state())

    def test_head_not_mission_branch_is_silent(self):
        p = self.proj(branch="main")
        self.silent(p.stop())
        self.assertIsNone(p.state())

    def test_other_branch_is_silent(self):
        p = self.proj(branch="feature/x")
        self.silent(p.stop())
        self.assertIsNone(p.state())

    def test_stopped_by_user_is_silent(self):
        p = self.proj(status="stopped")
        self.silent(p.stop())

    def test_ended_state_is_silent(self):
        p = self.proj()
        p.write(".factory/mission-state.json", json.dumps(
            {"slug": "demo", "continuations": 3, "sessions": {}, "ended": {"reason": "done", "ts": "x"}}))
        self.silent(p.stop())
        self.assertEqual(p.state()["continuations"], 3)

    def test_missing_mission_module_fails_open(self):
        p = self.proj()
        hooks = os.path.join(p.root, "hk")
        os.makedirs(hooks)
        for f in ("mission_stop.py", "_common.py"):  # no _mission.py: slice A absent
            shutil.copy(os.path.join(HOOKS, f), hooks)
        self.silent(p.stop(hook=os.path.join(hooks, "mission_stop.py")))


class Blocking(Base):
    def test_open_work_blocks_with_next_item_and_counts(self):
        p = self.proj()
        out = self.blocked(p.stop())
        self.assertEqual(out["decision"], "block")
        self.assertIn("Mission demo (1/40", out["reason"])
        self.assertIn("DEMO-1", out["reason"])
        self.assertIn("Don't ask the user", out["reason"])
        self.assertEqual(p.state()["continuations"], 1)
        self.assertEqual(p.header("status"), "active")

    def test_in_progress_item_comes_before_open_one(self):
        p = self.proj(items="- [ ] DEMO-1 First\n- [~] DEMO-2 Second\n")
        self.assertIn("DEMO-2", self.blocked(p.stop())["reason"])

    def test_open_item_when_none_in_progress(self):
        p = self.proj(items="- [x] DEMO-1 First\n- [!] DEMO-2 Parked\n- [ ] DEMO-3 Third\n")
        self.assertIn("DEMO-3", self.blocked(p.stop())["reason"])

    def test_empty_milestone_asks_for_a_plan_step(self):
        p = self.proj(items="")
        self.assertIn("PLAN", self.blocked(p.stop())["reason"])

    def test_stop_hook_active_is_ignored(self):
        p = self.proj()
        self.assertEqual(self.blocked(p.stop(stop_hook_active=True))["decision"], "block")
        self.assertEqual(p.state()["continuations"], 1)

    def test_unreadable_transcript_still_blocks(self):
        p = self.proj()
        out = self.blocked(p.stop(transcript_path=os.path.join(p.root, "nope.jsonl")))
        self.assertEqual(out["decision"], "block")

    def test_spend_is_stored_per_session_and_summed(self):
        p = self.proj()
        p.stop(session_id="a", transcript_path=p.transcript("a", "claude-sonnet-4", 1_000_000))  # $3
        p.stop(session_id="b", transcript_path=p.transcript("b", "claude-haiku-4", 1_000_000))   # $1
        s = p.state()
        self.assertAlmostEqual(s["sessions"]["a"], 3.0, places=2)
        self.assertAlmostEqual(s["sessions"]["b"], 1.0, places=2)

    def test_unknown_model_is_priced_at_the_highest(self):
        p = self.proj()
        p.stop(transcript_path=p.transcript("s1", "mystery-model", 1_000_000))
        self.assertAlmostEqual(p.state()["sessions"]["s1"], 5.0, places=2)


class Ending(Base):
    def test_all_closed_ends_done(self):
        p = self.proj(items="- [x] DEMO-1 First\n- [!] DEMO-2 Parked\n- [-] DEMO-3 Dropped\n")
        r = p.stop()
        self.silent_decision(r)
        self.assertEqual(p.state()["ended"]["reason"], "done")
        self.assertEqual(p.header("status"), "done")
        self.assertIn("done", json.loads(r.stdout)["systemMessage"])
        self.silent(p.stop())  # ended: later stops are no-ops

    def silent_decision(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("decision", json.loads(r.stdout))

    def test_budget_cap_from_transcript_and_subagents(self):
        p = self.proj(usd=4)  # main $2.5 + subagent $2.5 = $5 >= 4
        r = p.stop(transcript_path=p.transcript(tokens=500_000, sub_tokens=500_000))
        self.silent_decision(r)
        self.assertEqual(p.state()["ended"]["reason"], "budget")
        self.assertEqual(p.header("status"), "stopped")
        self.assertIn("budget", json.loads(r.stdout)["systemMessage"])

    def test_wall_clock_cap(self):
        p = self.proj(hours=2, age_hours=3)
        self.silent_decision(p.stop())
        self.assertEqual(p.state()["ended"]["reason"], "wall-clock")
        self.assertEqual(p.header("status"), "stopped")

    def test_continuation_cap(self):
        p = self.proj(conts=2)
        self.assertEqual(self.blocked(p.stop())["decision"], "block")
        self.assertEqual(self.blocked(p.stop())["decision"], "block")
        self.silent_decision(p.stop())
        self.assertEqual(p.state()["ended"]["reason"], "continuations")
        self.assertEqual(p.state()["continuations"], 2)

    def test_caps_are_checked_before_remaining_work(self):
        p = self.proj(usd=1)  # work remains, but $5 >= $1: the stop is allowed
        self.silent_decision(p.stop(transcript_path=p.transcript()))
        self.assertEqual(p.state()["ended"]["reason"], "budget")

    def test_wall_clock_comes_before_budget(self):
        p = self.proj(usd=1, hours=2, age_hours=3)
        p.stop(transcript_path=p.transcript())
        self.assertEqual(p.state()["ended"]["reason"], "wall-clock")

    def test_report_script_is_called_when_present(self):
        p = self.proj(items="- [x] DEMO-1 First\n")
        p.write("scripts/mission_report.py",
                "def write(root, slug, reason):\n"
                "    open(root + '/called.txt', 'w').write(slug + ':' + reason)\n"
                "    return 'docs/missions/%s-report.md' % slug\n")
        r = p.stop()
        with open(os.path.join(p.root, "called.txt"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "demo:done")
        self.assertIn("demo-report.md", json.loads(r.stdout)["systemMessage"])

    def test_failing_report_script_still_ends_the_mission(self):
        p = self.proj(items="- [x] DEMO-1 First\n")
        p.write("scripts/mission_report.py", "def write(root, slug, reason):\n    raise RuntimeError('boom')\n")
        r = p.stop()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(p.state()["ended"]["reason"], "done")
        self.assertIn("mission.py report", json.loads(r.stdout)["systemMessage"])


class NeverLoops(Base):
    def test_loop_ends_within_the_continuation_cap_even_with_stop_hook_active(self):
        p = self.proj(conts=5)
        blocks = 0
        for _ in range(20):
            r = p.stop(stop_hook_active=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            if r.stdout and json.loads(r.stdout).get("decision") == "block":
                blocks += 1
                continue
            break
        else:
            self.fail("hook kept blocking after 20 stops")
        self.assertEqual(blocks, 5)
        self.assertEqual(p.state()["ended"]["reason"], "continuations")

    def test_internal_error_allows_the_stop(self):
        p = self.proj()
        p.write(".factory/mission-state.json", "{not json")  # corrupt state must not wedge the session
        r = p.stop()
        self.assertEqual(r.returncode, 0)


class Registration(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8") as fh:
            self.settings = json.load(fh)

    def test_stop_hook_is_registered_behind_a_missing_file_guard(self):
        cmds = [h["command"] for g in self.settings["hooks"]["Stop"] for h in g["hooks"]]
        self.assertEqual(len(cmds), 1)
        self.assertIn("mission_stop.py", cmds[0])
        self.assertIn('[ -f "$f" ]', cmds[0])
        self.assertTrue(cmds[0].rstrip().endswith("|| true"))

    def test_wrapper_exits_zero_when_the_script_is_missing(self):
        cmd = [h["command"] for g in self.settings["hooks"]["Stop"] for h in g["hooks"]][0]
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        r = subprocess.run(["bash", "-c", cmd], env=dict(os.environ, CLAUDE_PROJECT_DIR=d), capture_output=True,
                           text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_permissions_untouched(self):
        self.assertNotIn("Stop", self.settings["permissions"])
        self.assertIn("SessionEnd", self.settings["hooks"])


if __name__ == "__main__":
    unittest.main()
