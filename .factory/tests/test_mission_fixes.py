"""Architect-review fixes for mission autopilot (docs/specs/mission-autopilot.md, ADR 0012): by-mission approval everywhere
(gate, runner), the mission cannot edit the factory's own controls, `mission.py start/status/stop/report`, the session
start line, shallow clones. Temp git repos, no network, no model."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_mission_approval as TA  # noqa: E402

ROOT = TA.ROOT
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gate  # noqa: E402
import mission_report  # noqa: E402
try:  # a bootstrapped project without the fixer pack has no runner
    import runner_pick
except ImportError:
    runner_pick = None

M, cli, Base = TA.M, TA.cli, TA.Base
START = ["--go", "go build it", "--title", "Run one", "--scope-in", "a", "--scope-out", "b", "--milestone", "M7"]


def head(p):
    return p.g("rev-parse", "--abbrev-ref", "HEAD").strip()


class ByMissionApproval(Base):  # X2
    def test_ghost_mission_is_unapproved_in_gate_and_runner(self):
        p = self.proj(mission=False)
        self.assertNotIn("night-one", gate.approved_slugs(p.root))
        self.assertFalse(gate.valid_acceptance_change(p.root, {"acceptance-change": ["night-one"]}))
        if runner_pick:
            self.assertNotIn("night-one", runner_pick.approved_for(p.root))

    def test_valid_mission_approves_in_scope_only(self):
        p = self.proj()
        ok = gate.approved_slugs(p.root)
        self.assertIn("night-one", ok)
        self.assertNotIn("stray", ok)
        self.assertTrue(gate.valid_acceptance_change(p.root, {"acceptance-change": ["night-one"]}))
        self.assertFalse(gate.valid_acceptance_change(p.root, {"acceptance-change": ["stray"]}))

    def test_historical_time_outside_window_is_unapproved(self):
        p = self.proj()
        old = TA.NOW - TA.datetime.timedelta(days=3)
        self.assertNotIn("night-one", gate.approved_slugs(p.root, old))

    def test_user_approval_unchanged(self):
        p = self.proj(mission=False)
        p.write("docs/specs/night-one.md", TA.PRD % "approved · 2026-11-16")
        self.assertIn("night-one", gate.approved_slugs(p.root))


class ProtectedControls(Base):  # X3
    PROTECTED = ("factory.json", ".claude/hooks/guard_prd_write.py", ".claude/settings.json", "scripts/gate.py",
                 "scripts/gate_checks.py", "scripts/mission.py", "scripts/mission_report.py", "scripts/slices.py",
                 "scripts/acceptance.py", "scripts/runner.py", "scripts/runner_pick.py", "scripts/sandbox.py",
                 "scripts/check.sh", ".factory/prd-exemption")

    def test_mission_cannot_edit_its_controls(self):
        p = self.proj()
        for rel in self.PROTECTED:
            r = p.edit(rel)
            self.assertEqual(r.returncode, 2, rel)
            self.assertIn("cannot change the factory's own controls", r.stderr)

    def test_mission_work_and_stop_still_allowed(self):
        p = self.proj()
        for rel in ("src/app.py", "docs/missions/night.md", "docs/BACKLOG.md", ".factory/tests/test_x.py", "scripts/other.py"):
            self.assertEqual(p.edit(rel).returncode, 0, rel)

    def test_bash_write_to_controls_blocked(self):
        p = self.proj()
        ev = {"tool_name": "Bash", "tool_input": {"command": "echo {} > factory.json"}, "cwd": p.root}
        r = subprocess.run([sys.executable, TA.HOOK], input=json.dumps(ev), capture_output=True, text=True,
                           env=dict(os.environ, CLAUDE_PROJECT_DIR=p.root))
        self.assertEqual(r.returncode, 2)

    def test_no_mission_no_change(self):  # PRD criterion 12
        p = self.proj(mission=False)
        p.write("docs/specs/night-one.md", TA.PRD % "approved · 2026-11-16")
        for rel in ("factory.json", ".claude/hooks/x.py", "scripts/gate.py", "src/app.py"):
            self.assertEqual(p.edit(rel).returncode, 0, rel)


class StartJourney(Base):  # X4, X5
    def run_cli(self, p, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(list(args), root=p.root)
        return rc, out.getvalue(), err.getvalue()

    def test_start_creates_branch_and_commit_works(self):
        p = self.proj(mission=False)
        rc, _o, e = self.run_cli(p, "start", "run1", *START)
        self.assertEqual((rc, head(p)), (0, "mission/run1"), e)
        self.assertEqual(M.load(p.root, "run1")["branch"], "mission/run1")
        p.commit("mission")
        self.assertEqual(M.validate(p.root, M.load(p.root, "run1")), "")

    def test_start_branch_flag_other_branch(self):
        p = self.proj(mission=False)
        self.assertEqual(self.run_cli(p, "start", "run1", "--branch", "feature/night", *START)[0], 0)
        self.assertEqual((head(p), M.load(p.root, "run1")["branch"]), ("feature/night",) * 2)

    def test_start_refuses_dirty_tree_and_wrong_phase(self):
        p = self.proj(mission=False)
        before = head(p)
        p.write("src/wip.py", "x\n")
        rc, _o, e = self.run_cli(p, "start", "run1", *START)
        self.assertEqual((rc, head(p)), (1, before))
        self.assertIn("uncommitted", e)
        self.assertIsNone(M.load(p.root, "run1"))
        p.commit("wip")
        p.write("factory.json", json.dumps({"phase": "brainstorm"}))
        p.commit("phase")
        rc, _o, e = self.run_cli(p, "start", "run1", *START)
        self.assertEqual((rc, head(p)), (1, before))
        self.assertIn("not 'build'", e)

    def test_status_names_head_off_branch_and_help_documents_flags(self):
        p = self.proj(mission=False)
        self.run_cli(p, "start", "run1", *START)
        p.commit("mission")
        p.g("switch", "-q", "-c", "other")
        out = self.run_cli(p, "status", "run1")[1]
        self.assertIn("HEAD is other, not the mission branch mission/run1", out)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            cli.main(["start", "--help"], root=p.root)
        for word in ("--brief", "--milestone", "--branch"):
            self.assertIn(word, buf.getvalue())

    def test_report_is_read_only_on_status_and_stop_writes_report(self):
        p = self.proj()
        self.assertEqual(self.run_cli(p, "report", "night")[0], 0)
        self.assertEqual(M.load(p.root, "night")["status"], "active")
        self.assertTrue(os.path.isfile(mission_report.report_path(p.root, "night")))
        os.remove(mission_report.report_path(p.root, "night"))
        self.assertEqual(self.run_cli(p, "stop", "night")[0], 0)
        self.assertEqual(M.load(p.root, "night")["status"], "stopped")
        self.assertTrue(os.path.isfile(mission_report.report_path(p.root, "night")))


class SessionStart(Base):  # X6
    def run_hook(self, p, source="startup"):
        r = subprocess.run([sys.executable, os.path.join(ROOT, ".claude", "hooks", "session_start.py")],
                           input=json.dumps({"source": source}), capture_output=True, text=True,
                           env=dict(os.environ, CLAUDE_PROJECT_DIR=p.root))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_active_mission_line(self):
        p = self.proj()
        out = self.run_hook(p, "compact")
        line = next(ln for ln in out.splitlines() if "MISSION night" in ln)
        for word in ("mission/night", "0/40", "NIGHT-1", "Do not stop to ask (docs/policies/mission.md)"):
            self.assertIn(word, line)
        self.assertNotIn("user gates still apply", out)
        self.assertIn("pushes to main still need the user", out)

    def test_no_mission_keeps_old_text_and_broken_mission_fails_open(self):
        p = self.proj(mission=False)
        out = self.run_hook(p, "compact")
        self.assertNotIn("MISSION", out)
        self.assertIn("user gates still apply", out)
        p.write("docs/missions/night.md", "garbage\n")
        self.assertNotIn("MISSION night", self.run_hook(p))


class Shallow(Base):  # X7
    def test_shallow_clone_is_invalid(self):
        p = self.proj()
        p.write("src/a.py", "x\n")
        p.commit("more")
        dst = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, dst, True)
        subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + p.root, dst + "/c"], check=True, capture_output=True)
        why = M.validate(dst + "/c", M.load(dst + "/c", "night"))
        self.assertIn("shallow", why)
        self.assertIn("fetch", why)
        self.assertEqual(M.validate(p.root, M.load(p.root, "night")), "")


if __name__ == "__main__":
    unittest.main()
