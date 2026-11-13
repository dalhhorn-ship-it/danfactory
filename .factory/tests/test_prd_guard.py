"""PRD write guard (GRD-1, docs/specs/prd-write-guard.md): hook criteria 1-4 and 7, gate check `prd` (criterion 5),
exemptions, template mode, dashboard numbers. Temp dirs only, no network, no model."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOOK = os.path.join(ROOT, ".claude", "hooks", "guard_prd_write.py")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
import gate  # noqa: E402
import _prd  # noqa: E402
from obs import tab_gates  # noqa: E402

TODAY = datetime.date.today().isoformat()
PRD = "# PRD: Demo\n\n> Status: %s · 2026-11-12 · Backlog: X-1\n\n## Acceptance criteria\n1. a thing\n"
SRC = "acme/template"


class Proj:
    """Temp project: factory.json, an approved and a draft PRD, a backlog. Optional git remote makes it template mode."""

    def __init__(self, phase="build", backlog="- [~] X-1 Do it (docs/specs/demo.md)\n", template=False, gate_cfg=None):
        self.root = tempfile.mkdtemp()
        self.write("factory.json", json.dumps({"phase": phase, "template": {"source_repo": SRC}, "gate": gate_cfg or {}}))
        self.write("docs/specs/demo.md", PRD % "approved")
        self.write("docs/specs/draft.md", PRD % "draft")
        self.write("docs/BACKLOG.md", "# Backlog\n\n## M1\n" + backlog)
        self.g("init", "-q")
        if template:
            self.g("remote", "add", "origin", "https://github.com/%s.git" % SRC)

    def g(self, *a):
        p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"] + list(a),
                           cwd=self.root, capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        return p.stdout

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, msg, trailer=""):
        self.g("add", "-A")
        self.g("commit", "-q", "--allow-empty", "-m", msg + ("\n\n" + trailer if trailer else ""))

    def edit(self, rel, tool="Edit", key="file_path", extra=None):
        ev = {"tool_name": tool, "tool_input": {key: os.path.join(self.root, rel)}, "cwd": self.root}
        ev.update(extra or {})
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.root)
        return subprocess.run([sys.executable, HOOK], input=json.dumps(ev), capture_output=True, text=True, env=env)


class Base(unittest.TestCase):
    def proj(self, **kw):
        p = Proj(**kw)
        self.addCleanup(shutil.rmtree, p.root, True)
        return p


class HookCriteria(Base):
    def test_c1_blocked_without_approved_item(self):
        for backlog in ("- [ ] X-1 Do it (docs/specs/demo.md)\n",        # not in progress
                        "- [~] X-1 Do it (docs/specs/draft.md)\n",       # PRD only a draft
                        "- [~] X-1 Do it\n",                              # no PRD link
                        "- [~] X-1 Do it (docs/specs/missing.md)\n"):    # dangling link
            p = self.proj(backlog=backlog)
            r = p.edit("src/app.py")
            self.assertEqual(r.returncode, 2, backlog)
            self.assertIn("no approved PRD", r.stderr)
            self.assertIn("src/app.py", r.stderr)
            self.assertIn("Status: approved", r.stderr)
            self.assertIn(".factory/prd-exemption", r.stderr)   # the three ways forward
            self.assertIn("Ask the user", r.stderr)

    def test_c1_every_write_tool_and_subagents_are_guarded(self):
        p = self.proj(backlog="")
        for tool, key in (("Edit", "file_path"), ("Write", "file_path"), ("MultiEdit", "file_path"), ("NotebookEdit", "notebook_path")):
            self.assertEqual(p.edit("src/a.py", tool, key).returncode, 2, tool)
        self.assertEqual(p.edit("src/a.py", extra={"agent_id": "a1", "agent_type": "developer"}).returncode, 2)

    def test_c2_allowed_with_in_progress_approved_prd(self):
        p = self.proj()
        self.assertEqual(p.edit("src/app.py").returncode, 0)
        self.assertEqual(p.edit("src/app.py", extra={"agent_id": "a1"}).returncode, 0)

    def test_c3_free_paths_always_allowed(self):
        p = self.proj(backlog="")
        for rel in ("docs/specs/new.md", "docs/BACKLOG.md", "issues/open/ISS-0001-x.md", "tests/acceptance/demo/test_x.py",
                    "tests/acceptance/manifest.json", "metrics/history.jsonl", ".factory/HANDOFF.md",
                    ".factory/prd-exemption", ".factory/tests/test_x.py", "README.md", "factory.json"):
            self.assertEqual(p.edit(rel).returncode, 0, rel)
        for rel in ("src/app.py", "tests/test_app.py", ".claude/settings.json", ".claude/hooks/guard_prd_write.py",
                    "CLAUDE.md", "scripts/gate.py", "package.json", "docs.py", "sub/README.md"):
            self.assertEqual(p.edit(rel).returncode, 2, rel)

    def test_paths_outside_the_repo_are_not_guarded(self):
        p = self.proj(backlog="")
        ev = {"tool_name": "Write", "tool_input": {"file_path": "/tmp/elsewhere/x.py"}, "cwd": p.root}
        r = subprocess.run([sys.executable, HOOK], input=json.dumps(ev), capture_output=True, text=True,
                           env=dict(os.environ, CLAUDE_PROJECT_DIR=p.root))
        self.assertEqual(r.returncode, 0)

    def test_c4_same_day_exemption_allows_and_shows_in_gate(self):
        p = self.proj(backlog="")
        self.assertEqual(p.edit("src/app.py").returncode, 2)
        for kind in _prd.KINDS:
            p.write(".factory/prd-exemption", "%s %s: because\n" % (TODAY, kind))
            self.assertEqual(p.edit("src/app.py").returncode, 0, kind)
        p.write(".factory/prd-exemption", "2020-01-01 bugfix: old\n")           # expired
        self.assertEqual(p.edit("src/app.py").returncode, 2)
        for bad in ("%s bugfix:\n" % TODAY, "%s whatever: x\n" % TODAY, "bugfix: x\n", "%s bugfix x\n" % TODAY):
            p.write(".factory/prd-exemption", bad)                               # malformed lines grant nothing
            self.assertEqual(p.edit("src/app.py").returncode, 2, bad)
        p.write(".factory/prd-exemption", "%s bugfix: fix the thing\n2020-01-01 chore: old\n" % TODAY)
        p.commit("base")
        base = p.g("rev-parse", "HEAD").strip()
        c = {x["id"]: x for x in gate.run_gate(p.root, base, {"prd"})["checks"]}["prd"]
        self.assertIn("1 active (bugfix), 1 expired", c["detail"])

    def test_c7_phase_before_build_blocks_even_with_item_in_progress(self):
        for phase in ("brainstorm", "operating-model"):
            p = self.proj(phase=phase)
            r = p.edit("src/app.py")
            self.assertEqual(r.returncode, 2, phase)
            self.assertIn("phase is '%s'" % phase, r.stderr)
            p.write(".factory/prd-exemption", "%s waiver: user said so\n" % TODAY)  # only a spike opens a pre-build phase
            self.assertEqual(p.edit("src/app.py").returncode, 2)
            p.write(".factory/prd-exemption", "%s spike: throwaway prototype\n" % TODAY)
            self.assertEqual(p.edit("src/app.py").returncode, 0)
            self.assertEqual(p.edit("docs/GOAL.md").returncode, 0)

    def test_template_mode_skips_phase_but_keeps_in_progress_rule(self):
        p = self.proj(phase="brainstorm", template=True)        # the template's own factory.json says brainstorm
        self.assertEqual(p.edit("scripts/x.py").returncode, 0)  # item [~] with approved PRD
        p.write("docs/BACKLOG.md", "# Backlog\n- [ ] X-1 Do it (docs/specs/demo.md)\n")
        self.assertEqual(p.edit("scripts/x.py").returncode, 2)  # nothing in progress: blocked

    def test_fails_open_on_internal_error_but_not_on_missing_prd(self):
        p = self.proj(backlog="")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=p.root)
        r = subprocess.run([sys.executable, HOOK], input="{not json", capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0)
        shutil.rmtree(os.path.join(p.root, "docs"))               # missing backlog and PRDs: still blocked
        self.assertEqual(p.edit("src/app.py").returncode, 2)
        # a crash inside the rules is a warning, not a block
        hooks = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, hooks, True)
        for n in ("_common.py", "guard_prd_write.py"):
            shutil.copy(os.path.join(ROOT, ".claude", "hooks", n), hooks)
        with open(os.path.join(hooks, "_prd.py"), "w") as fh:
            fh.write("def rel_path(*a, **k):\n    raise RuntimeError('boom')\n")
        ev = {"tool_name": "Edit", "tool_input": {"file_path": "x.py"}}
        r = subprocess.run([sys.executable, os.path.join(hooks, "guard_prd_write.py")], input=json.dumps(ev),
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0)
        self.assertIn("internal error", r.stderr)

    def test_block_is_recorded_and_fast(self):
        p = self.proj(backlog="")
        t0 = time.monotonic()
        p.edit("src/app.py")
        self.assertLess(time.monotonic() - t0, 1.0)  # budget is 100 ms of work; process start dominates in CI
        with open(os.path.join(p.root, "metrics", "guard.local.jsonl")) as fh:
            rows = [json.loads(x) for x in fh]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["path"], "src/app.py")

    def test_registered_in_settings(self):
        with open(os.path.join(ROOT, ".claude", "settings.json"), encoding="utf-8") as fh:
            pre = json.load(fh)["hooks"]["PreToolUse"]
        hit = [e for e in pre if any("guard_prd_write.py" in h["command"] for h in e["hooks"])]
        self.assertEqual(len(hit), 1)
        self.assertEqual(set(hit[0]["matcher"].split("|")), {"Edit", "Write", "MultiEdit", "NotebookEdit"})


class EvalGrader(unittest.TestCase):
    def events(self, tool, path, result, error=True):
        return [{"message": {"content": [{"type": "tool_use", "id": "1", "name": tool, "input": {"file_path": path}}]}},
                {"message": {"content": [{"type": "tool_result", "tool_use_id": "1", "is_error": error, "content": result}]}}]

    def test_tool_blocked_needs_an_attempt_and_a_guard_stop(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import evals_graders as g
        args = dict(tool="Edit|Write", pattern=r"textkit/core\.py$")
        blocked = self.events("Edit", "/p/textkit/core.py", "PreToolUse:Edit hook error: this edit is not allowed")
        self.assertTrue(g.tool_blocked("", blocked, **args)[0])
        self.assertEqual(g.tool_blocked("", [], **args), (False, "never attempted"))
        self.assertFalse(g.tool_blocked("", self.events("Edit", "/p/textkit/core.py", "ok", error=False), **args)[0])
        self.assertFalse(g.tool_blocked("", self.events("Edit", "/p/docs/x.md", "hook error"), **args)[0])
        self.assertEqual(g.GRADERS["tool_blocked"], g.tool_blocked)
        task = os.path.join(ROOT, "evals", "tasks", "prd-write-forced", "task.json")
        if os.path.exists(task):  # adopted projects do not carry evals/
            with open(task, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["graders"][0]["type"], "tool_blocked")


class GateCheck(Base):
    def prd(self, p, base, only="prd"):
        return {c["id"]: c for c in gate.run_gate(p.root, base, {only})["checks"]}[only]

    def start(self, **kw):
        p = self.proj(**kw)
        p.write("README.md", "x\n")
        p.commit("base")
        return p, p.g("rev-parse", "HEAD").strip()

    def test_c5_required_fails_product_commit_without_refs(self):
        p, base = self.start()
        p.write("src/app.py", "x = 1\n")
        p.commit("feat: thing")
        c = self.prd(p, base)
        self.assertEqual((c["status"], c["codes"]), ("fail", ["no-approved-prd"]))
        p.write("src/b.py", "y = 1\n")
        p.commit("feat: other", "Refs: X-9")          # unknown item
        self.assertEqual(self.prd(p, base)["codes"], ["no-approved-prd"])

    def test_default_mode_is_required(self):
        p, base = self.start(gate_cfg=None)
        p.write("src/app.py", "x = 1\n")
        p.commit("feat: thing")
        self.assertEqual(self.prd(p, base)["status"], "fail")

    def test_advisory_warns_and_off_skips(self):
        p, base = self.start(gate_cfg={"prd": "advisory"})
        p.write("src/app.py", "x = 1\n")
        p.commit("feat: thing")
        c = self.prd(p, base)
        self.assertEqual((c["status"], c["codes"]), ("warn", ["no-approved-prd"]))
        p.write("factory.json", json.dumps({"gate": {"prd": "off"}}))
        self.assertEqual(self.prd(p, base)["status"], "skip")

    def test_passes_with_refs_exempt_or_docs_only(self):
        p, base = self.start(backlog="- [~] X-1 Do it (docs/specs/demo.md)\n- [ ] X-2 Draft (docs/specs/draft.md)\n")
        p.write("docs/notes.md", "n\n")
        p.commit("docs: only")
        self.assertEqual(self.prd(p, base)["status"], "pass")
        p.write("src/a.py", "1\n")
        p.commit("feat: a", "Refs: X-1")
        p.write("src/b.py", "1\n")
        p.commit("feat: b", "Refs: X-0, X-1")
        p.write("src/c.py", "1\n")
        p.commit("fix: c", "PRD-Exempt: typo in a string, no behaviour change")
        p.write("src/d.py", "1\n")
        p.commit("feat: d", "Refs: demo")                # PRD slug
        c = self.prd(p, base)
        self.assertEqual(c["status"], "pass", c["detail"])
        self.assertIn("1 by PRD-Exempt", c["detail"])
        p.write("src/e.py", "1\n")
        p.commit("feat: e", "Refs: X-2")                 # item whose PRD is only a draft
        self.assertEqual(self.prd(p, base)["status"], "fail")

    def test_issue_ref_follows_the_issue_prd(self):
        p, base = self.start()
        p.write("issues/open/ISS-0003-x.md", "# x\n\n> Status: open · PRD: demo · Item: - · Fingerprint: ab · Opened: d · Updated: d · Fixed: -\n")
        p.write("issues/open/ISS-0004-y.md", "# y\n\n> Status: open · PRD: draft · Item: - · Fingerprint: ab · Opened: d · Updated: d · Fixed: -\n")
        p.write("src/a.py", "1\n")
        p.commit("fix: a", "Refs: ISS-0003")
        self.assertEqual(self.prd(p, base)["status"], "pass")
        p.write("src/b.py", "1\n")
        p.commit("fix: b", "Refs: ISS-4")
        self.assertEqual(self.prd(p, base)["status"], "fail")

    def test_no_base_skips(self):
        p = self.proj()
        self.assertEqual({c["id"]: c for c in gate.run_gate(p.root, None, {"prd"})["checks"]}["prd"]["status"], "skip")

    def test_template_factory_json_is_advisory_and_check_is_registered(self):
        self.assertIn("prd", [c for c, _ in gate.CHECKS])
        self.assertEqual(gate.DEFAULTS["prd"], "required")
        sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
        from _common import template_mode
        if not template_mode(root=ROOT):
            self.skipTest("the template's own factory.json setting; a project sets gate.prd itself (pilot 2)")
        with open(os.path.join(ROOT, "factory.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["gate"]["prd"], "advisory")
        self.assertEqual(gate.DEFAULTS["prd"], "required")


class Dashboard(Base):
    def test_guard_stats(self):
        p = self.proj()
        now = time.time()
        old = datetime.datetime.fromtimestamp(now - 40 * 86400, datetime.timezone.utc).isoformat()
        new = datetime.datetime.fromtimestamp(now - 86400, datetime.timezone.utc).isoformat()
        p.write("metrics/guard.local.jsonl", "\n".join([json.dumps({"ts": old}), json.dumps({"ts": new}), "junk", json.dumps({"ts": new})]) + "\n")
        p.write(".factory/prd-exemption", "%s chore: a\n2020-01-01 chore: b\n" % TODAY)
        rows = [{"codes": ["no-approved-prd"]}, {"codes": []}]
        g = tab_gates.guard_stats(p.root, rows, now)
        self.assertEqual((g["blocks_30d"], g["open_exemptions"], g["no_approved_prd_runs"], g["window"]), (2, 1, 1, 2))
        self.assertIn("2 block(s) in 30d, 1 open exemption(s), no-approved-prd in 1 of last 2", tab_gates.guard_line(g))
        self.assertIn("PRD write guard", tab_gates.render_guard(g))


if __name__ == "__main__":
    unittest.main()
