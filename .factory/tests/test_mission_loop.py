"""Mission hardening, slice Q (MISSION-8, 9, 12; docs/specs/mission-hardening.md criteria 3, 4, 7, 8).
Real temp git repos, the real hooks and runner as subprocesses. No network, no model."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_mission_branch as TB  # noqa: E402
import test_mission_stop as TS  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RUNNER = os.path.join(ROOT, "scripts", "runner.py")
NOW = datetime.datetime.now(datetime.timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class Held(TS.Base):
    def slice_out(self, p, branch="slice/demo-1"):
        wt = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, wt, True)
        p.g("worktree", "add", "-q", "-b", branch, os.path.join(wt, "w"))

    def test_all_open_held_waits_and_does_not_raise_continuations(self):
        p = self.proj(items="- [~] DEMO-1 First\n- [~] DEMO-2 Second\n- [x] DEMO-3 Done\n")
        self.slice_out(p)
        for n in (1, 2):
            out = self.blocked(p.stop())
            self.assertEqual(out["decision"], "block")
            self.assertIn("Developers are still working on: DEMO-1, DEMO-2", out["reason"])
            self.assertIn("slices.py land", out["reason"])
            self.assertIn("do not start these items again", out["reason"])
            self.assertEqual(p.state()["continuations"], 0)
            self.assertEqual(p.state()["waits"], n)

    def test_waits_are_bounded_then_item_is_offered_and_counted(self):
        p = self.proj(items="- [~] DEMO-1 First\n")
        self.slice_out(p)
        for _ in range(6):
            self.assertIn("Developers are still", self.blocked(p.stop())["reason"])
        out = self.blocked(p.stop())
        self.assertIn("Next: DEMO-1", out["reason"])
        self.assertEqual(p.state()["continuations"], 1)

    def test_caps_are_checked_before_waiting(self):
        p = self.proj(items="- [~] DEMO-1 First\n", usd=1)
        self.slice_out(p)
        r = p.stop(transcript_path=p.transcript(tokens=1_000_000))
        self.assertNotIn("decision", self.blocked(r))
        self.assertEqual(p.state()["ended"]["reason"], "budget")

    def test_open_item_beats_held_in_progress_item(self):
        p = self.proj(items="- [~] DEMO-1 First\n- [ ] DEMO-2 Second\n")
        self.slice_out(p)
        out = self.blocked(p.stop())
        self.assertIn("Next: DEMO-2", out["reason"])
        self.assertEqual(p.state()["continuations"], 1)

    def test_no_slices_is_as_before(self):
        p = self.proj(items="- [~] DEMO-1 First\n- [ ] DEMO-2 Second\n")
        self.assertIn("Next: DEMO-1", self.blocked(p.stop())["reason"])
        p = self.proj(items="- [~] DEMO-1 First\n")
        out = self.blocked(p.stop())
        self.assertIn("Next: DEMO-1", out["reason"])
        self.assertNotIn("waits", p.state())

    def test_mission_branch_worktree_is_not_a_slice(self):
        p = self.proj(items="- [~] DEMO-1 First\n", branch="main")
        self.slice_out(p, branch="mission/demo")  # same branch as the mission: not a slice
        p.g("checkout", "-q", "-b", "other")
        self.assertNotIn("Developers are still", json.dumps(self.blocked(p.stop())))


class SecondReading(TS.Base):
    def rows(self, p, *rows):
        os.makedirs(os.path.join(p.root, "metrics"), exist_ok=True)
        with open(os.path.join(p.root, "metrics", "runner.jsonl"), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    def test_second_reading_cost_counts_toward_the_budget(self):
        p = self.proj(usd=5)
        self.rows(p, {"ts": iso(NOW - datetime.timedelta(minutes=10)), "kind": "second-reading", "cost_usd": 2.5},
                  {"ts": iso(NOW - datetime.timedelta(hours=5)), "kind": "second-reading", "cost_usd": 100},  # before start
                  {"ts": iso(NOW), "kind": "attempt", "cost_usd": 100})  # not a second reading
        out = self.blocked(p.stop())
        self.assertIn("$2.50/5", out["reason"])
        self.assertIn("$2.50 of second readings", out["reason"])
        self.rows(p, {"ts": iso(NOW - datetime.timedelta(minutes=10)), "kind": "second-reading", "cost_usd": 5.5})
        self.assertEqual(p.state()["sessions"]["second-reading"], 2.5)
        out = self.blocked(p.stop())
        self.assertNotIn("decision", out)
        self.assertEqual(p.state()["ended"]["reason"], "budget")

    def test_no_rows_no_change(self):
        p = self.proj()
        self.assertNotIn("second readings", self.blocked(p.stop())["reason"])
        self.assertNotIn("second-reading", p.state()["sessions"])


class Window(TB.Base):
    def test_done_and_stopped_inside_window_still_block(self):
        for status in ("done", "stopped"):
            p = self.proj(status=status, head="main")
            for cmd in ("git push origin main", "git push origin staging", "git push origin HEAD:staging",
                        "gh pr merge 3", "git commit -m x"):
                with self.subTest(status=status, cmd=cmd):
                    r = p.bash(cmd)
                    self.assertEqual(r.returncode, 2, r.stdout)
                    self.assertIn("mission window ends at", r.stderr)
                    self.assertIn("from your own terminal", r.stderr)
            self.assertAllowed(p, "git push origin mission/demo")

    def test_after_the_window_it_is_allowed(self):
        p = self.proj(status="done", head="main", hours_ago=11)  # 10h cap
        for cmd in ("git push origin main", "git push origin staging", "gh pr merge 3", "git commit -m x"):
            self.assertAllowed(p, cmd)

    @staticmethod
    def put(path, text):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_editing_or_deleting_the_mission_file_does_not_shorten_the_window(self):
        for how in ("edit-start", "edit-hours", "delete", "strip-header"):
            p = self.proj(status="done", head="main")  # started 1h ago, 10h cap
            path = os.path.join(p.root, "docs/missions/demo.md")
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if how == "edit-start":
                old = (NOW - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
                text = text.replace(old, (NOW - datetime.timedelta(hours=40)).strftime("%Y-%m-%dT%H:%M:%SZ"))
            elif how == "edit-hours":
                text = text.replace("hours=10", "hours=0.01")
            if how == "delete":
                os.remove(path)
            elif how == "strip-header":
                self.put(path, "# gone\n")
            else:
                self.put(path, text)
            with self.subTest(how=how):
                r = p.bash("git push origin main")
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn("mission window ends at", r.stderr)

    def test_active_mission_blocks_staging(self):
        self.assertBlocked(self.proj(), "git push origin staging")

    def test_configured_staging_branch(self):
        p = self.proj()
        p.write("factory.json", json.dumps({"autonomy": {"staging_branch": "preprod"}}))
        self.assertBlocked(p, "git push origin preprod")

    def test_no_mission_is_unchanged(self):
        p = self.proj(mission=False, head="main")
        for cmd in ("git push origin main", "git push origin staging", "git commit -m x"):
            self.assertAllowed(p, cmd)


@unittest.skipUnless(os.path.exists(RUNNER), "no scripts/runner.py in this (light) copy")
class RunnerRefuses(TS.Base):
    def run_runner(self, p, *args):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=p.root)
        return subprocess.run([sys.executable, "-B", RUNNER, "--root", p.root] + list(args), capture_output=True,
                              text=True, env=env, cwd=p.root)

    def test_run_refuses_during_a_mission(self):
        p = self.proj()
        os.makedirs(os.path.join(p.root, ".claude"), exist_ok=True)
        shutil.copytree(os.path.join(ROOT, ".claude", "hooks"), os.path.join(p.root, ".claude", "hooks"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        for extra in ([], ["--scheduled"]):
            r = self.run_runner(p, "run", "--next", *extra)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("a mission is active", r.stdout + r.stderr)
            self.assertIn("does not run during a mission", r.stdout + r.stderr)

    def test_no_mission_does_not_refuse_for_that_reason(self):
        p = self.proj(mission=False)
        r = self.run_runner(p, "run", "--next")
        self.assertNotIn("mission is active", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
