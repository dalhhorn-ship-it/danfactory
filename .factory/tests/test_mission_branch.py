"""Mission branch safety (MISSION-3, docs/specs/mission-autopilot.md criterion 9 and 12; ADR 0012).
While a mission is active, git/gh commands that push or merge into main/master/production are blocked by
guard_bash_policy. Temp git repos, the real hook as a subprocess. No network, no model.

Honest limits (same as _gitmission.py): git run by scripts or generated programs, aliases, `gh api` and the web
UI are not seen; GitHub branch protection plus credential scoping (ADR 0003) is the real protection."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOOK = os.path.join(ROOT, ".claude", "hooks", "guard_bash_policy.py")
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
caps: usd=15 hours=10 continuations=40
scope_in: demo-*
scope_out: everything else
<!-- mission:end -->

## Brief
Build the demo. Reply go to start.

## Decision log
"""


class Proj:
    def __init__(self, status="active", mission=True, head="mission/demo", production="main"):
        self.root = tempfile.mkdtemp()
        started = (NOW - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.write("factory.json", json.dumps({"phase": "build", "gate": {"base_branch": "main"},
                                               "integrations": {"deploy": {"production_branch": production}}}))
        self.write("docs/BACKLOG.md", "# Backlog\n\n## Milestone: M5 — Demo (mission: demo)\n- [~] DEMO-1 x\n")
        if mission:
            self.write("docs/missions/demo.md", MISSION.format(status=status, date=started[:10], started=started))
        self.g("init", "-q", "-b", "main")
        self.g("add", "-A")
        self.g("commit", "-q", "-m", "start")
        self.g("branch", "mission/demo")
        if head != "main":
            self.g("checkout", "-q", head)

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

    def bash(self, cmd, cwd=None):
        ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd or self.root}
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.root)
        return subprocess.run([sys.executable, "-B", HOOK], input=json.dumps(ev), capture_output=True, text=True,
                              env=env)


class Base(unittest.TestCase):
    def proj(self, **kw):
        p = Proj(**kw)
        self.addCleanup(shutil.rmtree, p.root, True)
        return p

    def assertBlocked(self, p, cmd, **kw):
        r = p.bash(cmd, **kw)
        self.assertEqual(r.returncode, 2, "%r should be blocked: %s" % (cmd, r.stdout))
        self.assertIn("mission", r.stderr.lower())

    def assertAllowed(self, p, cmd, **kw):
        r = p.bash(cmd, **kw)
        self.assertEqual((r.returncode, r.stderr), (0, ""), "%r should pass" % cmd)


class PushAndMerge(Base):
    def test_pushes_to_protected_branches_are_blocked(self):
        p = self.proj()
        for cmd in ("git push origin main", "git push origin master", "git push origin HEAD:main",
                    "git push origin +HEAD:refs/heads/main", "git push origin mission/demo:main",
                    "git push origin refs/heads/main", "git push origin --delete main", "git push origin :main",
                    "git push -u origin main", "git push --force origin main", "git push --all",
                    "git push --mirror origin", "git -C . push origin main", "git -c x.y=z push origin main",
                    "cd /tmp && git push origin main", "echo hi; git push origin main",
                    "bash -c 'git push origin main'"):
            with self.subTest(cmd=cmd):
                self.assertBlocked(p, cmd)

    def test_production_and_base_branches_from_factory_json_are_protected(self):
        p = self.proj(production="release")
        self.assertBlocked(p, "git push origin release")
        self.assertBlocked(p, "git push origin main")

    def test_pushing_the_mission_branch_is_allowed(self):
        p = self.proj()
        for cmd in ("git push origin mission/demo", "git push -u origin mission/demo", "git push",
                    "git push origin HEAD", "git push origin HEAD:mission/demo", "git push origin feature/main",
                    "git push origin mainline"):
            with self.subTest(cmd=cmd):
                self.assertAllowed(p, cmd)

    def test_bare_push_and_head_push_from_a_protected_head_are_blocked(self):
        p = self.proj(head="main")
        self.assertBlocked(p, "git push")
        self.assertBlocked(p, "git push origin HEAD")

    def test_gh_pr_merge_is_blocked(self):
        p = self.proj()
        self.assertBlocked(p, "gh pr merge 12 --squash")
        self.assertBlocked(p, "gh -R a/b pr merge 3")
        self.assertAllowed(p, "gh pr view 12")
        self.assertAllowed(p, "gh pr create --fill")

    def test_checkout_switch_worktree_onto_protected_are_blocked(self):
        p = self.proj()
        for cmd in ("git checkout main", "git switch master", "git switch -C main", "git checkout -B main",
                    "git worktree add ../w main", "git -C . checkout main"):
            with self.subTest(cmd=cmd):
                self.assertBlocked(p, cmd)
        for cmd in ("git checkout -b feature/x", "git checkout -b feature/x main", "git switch mission/demo",
                    "git checkout main -- docs/BACKLOG.md", "git worktree add -b w ../w main",
                    "git worktree add ../w mission/demo"):
            with self.subTest(cmd=cmd):
                self.assertAllowed(p, cmd)

    def test_moving_protected_refs_is_blocked(self):
        p = self.proj()
        for cmd in ("git branch -f main HEAD", "git branch -M main", "git branch -D main",
                    "git update-ref refs/heads/main HEAD", "git update-ref refs/heads/master abc123"):
            with self.subTest(cmd=cmd):
                self.assertBlocked(p, cmd)
        self.assertAllowed(p, "git branch -f feature/x HEAD")
        self.assertAllowed(p, "git branch --list")

    def test_history_changes_while_head_is_protected_are_blocked(self):
        p = self.proj(head="main")
        for sub in ("commit -m x", "merge mission/demo", "pull", "rebase mission/demo", "cherry-pick abc",
                    "revert abc", "am p.patch", "reset --hard HEAD~1"):
            with self.subTest(sub=sub):
                self.assertBlocked(p, "git " + sub)
        self.assertAllowed(p, "git status")
        self.assertAllowed(p, "git log --oneline")
        self.assertAllowed(p, "git diff")

    def test_the_c_directory_decides_which_head_counts(self):
        p = self.proj()  # cwd is on the mission branch; the other worktree is on main
        other = os.path.join(p.root, "..", os.path.basename(p.root) + "-wt")
        other = os.path.abspath(other)
        self.addCleanup(shutil.rmtree, other, True)
        p.g("worktree", "add", "-q", other, "main")
        self.assertBlocked(p, "git -C %s commit -m x" % other)
        self.assertAllowed(p, "git commit -m x")

    def test_history_changes_on_the_mission_branch_are_allowed(self):
        p = self.proj()
        for sub in ("commit -m x", "merge main", "pull", "rebase main", "cherry-pick abc", "reset --hard HEAD~1"):
            with self.subTest(sub=sub):
                self.assertAllowed(p, "git " + sub)


class NoMissionBehaviourIsUnchanged(Base):
    def test_no_mission_nothing_extra_is_blocked(self):
        p = self.proj(mission=False, head="main")
        for cmd in ("git push origin main", "git push", "git checkout main", "git commit -m x", "gh pr merge 1",
                    "git branch -f main HEAD", "git merge x"):
            with self.subTest(cmd=cmd):
                self.assertAllowed(p, cmd)

    def test_stopped_mission_nothing_extra_is_blocked(self):
        p = self.proj(status="stopped")
        self.assertAllowed(p, "git push origin main")
        self.assertAllowed(p, "gh pr merge 1")

    def test_existing_policy_still_applies_with_a_mission(self):
        p = self.proj()
        r = p.bash("git push origin mission/demo --no-verify")
        self.assertEqual(r.returncode, 2)
        r = p.bash("npx wrangler deploy")
        self.assertEqual(r.returncode, 2)

    def test_existing_policy_still_applies_without_a_mission(self):
        p = self.proj(mission=False)
        self.assertEqual(p.bash("git push --no-verify origin x").returncode, 2)
        self.assertAllowed(p, "git push origin x")

    def test_missing_mission_module_fails_open(self):
        p = self.proj()
        hooks = os.path.join(p.root, "hk")
        os.makedirs(hooks)
        for f in os.listdir(os.path.dirname(HOOK)):
            if f.endswith(".py") and f not in ("_mission.py", "_gitmission.py"):
                shutil.copy(os.path.join(os.path.dirname(HOOK), f), hooks)
        ev = {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}, "cwd": p.root}
        r = subprocess.run([sys.executable, "-B", os.path.join(hooks, "guard_bash_policy.py")],
                           input=json.dumps(ev), capture_output=True, text=True,
                           env=dict(os.environ, CLAUDE_PROJECT_DIR=p.root))
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
