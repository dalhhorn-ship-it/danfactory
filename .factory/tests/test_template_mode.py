"""Template-mode detection and its call sites (stdlib unittest, temp git repos, no network)."""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
from _common import origin_slug, template_mode  # noqa: E402

SRC = "dalhhorn-ship-it/danfactory"
COPY = [".claude/hooks/_common.py", ".claude/hooks/session_start.py", ".claude/hooks/record_tokens.py",
        "scripts/dashboard.py", "scripts/metrics.py", "scripts/evals.py", "scripts/evals_graders.py", "scripts/issues.py", "scripts/sandbox.py"] + sorted(  # dashboard imports its tab modules
    os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "scripts", "obs", "*.py")))
COPY = [c for c in COPY if os.path.isfile(os.path.join(ROOT, c))]  # issues.py and tab_autonomy.py are pack files (absent in a light project)
BACKLOG = "# Backlog\n\n## Milestone: M0 (target: )\n- [ ] One #process\n\n## Unplanned\n- [ ] Maintain thing #foundation\n"
DEBT = "# Debt\n\n## Open\n- [ ] TD-001 Fix the thing \u2014 impact: low \u00b7 effort: S\n"
BRAINSTORM = "[danfactory] next: No agreed goal yet. Run the `brainstorm` skill"


def make_copy(remote=None, git=True):
    d = tempfile.mkdtemp()
    for rel in COPY:
        os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
        shutil.copy(os.path.join(ROOT, rel), os.path.join(d, rel))
    with open(os.path.join(ROOT, "factory.json"), encoding="utf-8") as fh:  # hermetic: pristine, never adopted
        f = json.load(fh)
    f.pop("adopted", None)
    f.update(phase="brainstorm", project={"name": "", "one_liner": ""})
    f["paths"] = {"primary": "", "secondary": []}  # a project from the template has its own path and commands (pilot 2)
    f["commands"] = {k: "" for k in f.get("commands", {})}
    f["template"]["source_repo"] = SRC
    os.makedirs(os.path.join(d, "docs"))
    for rel, body in (("factory.json", json.dumps(f)), ("docs/BACKLOG.md", BACKLOG), ("docs/TECH-DEBT.md", DEBT)):
        with open(os.path.join(d, rel), "w", encoding="utf-8") as fh:
            fh.write(body)
    if git:
        subprocess.run(["git", "init", "-q", d], check=True)
        if remote:
            subprocess.run(["git", "-C", d, "remote", "add", "origin", remote], check=True)
    return d


def run(d, *argv, stdin=""):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    env["CLAUDE_PROJECT_DIR"] = d
    return subprocess.run([sys.executable, *argv], input=stdin, capture_output=True, text=True, cwd=d, env=env)


class Helper(unittest.TestCase):
    def test_matching_forms(self):
        for url in ["https://github.com/dalhhorn-ship-it/danfactory", "https://github.com/dalhhorn-ship-it/danfactory.git",
                    "https://github.com/dalhhorn-ship-it/danfactory/", "git@github.com:dalhhorn-ship-it/danfactory.git",
                    "git@github.com:dalhhorn-ship-it/danfactory", "ssh://git@github.com/dalhhorn-ship-it/danfactory.git",
                    "https://github.com/Dalhhorn-Ship-It/DanFactory.git",
                    "http://local_proxy@127.0.0.1:41234/git/dalhhorn-ship-it/danfactory",
                    "http://local_proxy@127.0.0.1:41234/git/dalhhorn-ship-it/danfactory.git"]:
            with self.subTest(url=url):
                d = make_copy(url)
                self.addCleanup(shutil.rmtree, d, True)
                self.assertTrue(template_mode(root=d))

    def test_project_mode(self):
        for name, d in [("other repo", make_copy("https://github.com/someone/else.git")),
                        ("lookalike", make_copy("https://github.com/dalhhorn-ship-it/danfactory-fork")),
                        ("other owner", make_copy("https://github.com/someone/danfactory")),
                        ("no remote", make_copy()), ("no git", make_copy(git=False))]:
            self.addCleanup(shutil.rmtree, d, True)
            with self.subTest(name):
                self.assertFalse(template_mode(root=d))

    def test_no_source_repo_or_factory(self):
        d = make_copy("https://github.com/dalhhorn-ship-it/danfactory")
        self.addCleanup(shutil.rmtree, d, True)
        self.assertFalse(template_mode(root=d, factory={"template": {}}))
        os.remove(os.path.join(d, "factory.json"))
        self.assertFalse(template_mode(root=d))

    def test_slug(self):
        self.assertEqual(origin_slug("git@github.com:A/B.git"), "a/b")
        self.assertEqual(origin_slug(""), "")

    def test_factory_declares_source(self):
        with open(os.path.join(ROOT, "factory.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["template"]["source_repo"], SRC)


class CallSites(unittest.TestCase):
    def setUp(self):
        self.tpl = make_copy("https://github.com/dalhhorn-ship-it/danfactory.git")
        self.prj = make_copy("https://github.com/someone/else.git")
        for d in (self.tpl, self.prj):
            self.addCleanup(shutil.rmtree, d, True)

    def test_session_start(self):
        out = run(self.tpl, ".claude/hooks/session_start.py", stdin="{}").stdout
        self.assertIn("TEMPLATE repo", out)
        self.assertNotIn("brainstorm", out.lower())
        prj = run(self.prj, ".claude/hooks/session_start.py", stdin="{}").stdout
        self.assertEqual(prj.splitlines()[0], "[danfactory] phase=brainstorm primary_path=- secondary=-")
        self.assertTrue(prj.splitlines()[1].startswith(BRAINSTORM))
        self.assertNotIn("TEMPLATE", prj)

    def test_dashboard(self):
        t = run(self.tpl, "scripts/dashboard.py", "--print").stdout
        self.assertIn("Template maintenance", t)
        self.assertIn("TD-001", t)
        self.assertIn("Maintain thing", t)
        self.assertNotIn("Phase / path", t)
        self.assertNotRegex(t, r"\d+%\s+—")
        p = run(self.prj, "scripts/dashboard.py", "--print").stdout
        self.assertIn("Phase / path | brainstorm", p)
        self.assertIn("| Progress |", p)
        self.assertNotIn("Template maintenance", p)
        with open(os.path.join(self.prj, "dashboard", "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        self.assertIn("Progress by milestone", html)
        self.assertNotIn("Template maintenance", html)

    def test_metrics_test_command(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import metrics
        self.assertEqual(metrics.TEMPLATE_TEST, "python3 scripts/run_tests.py")
        r = run(self.prj, "scripts/metrics.py", "test")
        self.assertIn("commands.test is empty", r.stdout)  # project mode unchanged

    def test_record_tokens_fresh_copy_not_template(self):
        tp = os.path.join(self.prj, "t.jsonl")
        line = {"type": "assistant", "message": {"model": "m", "usage": {
            "input_tokens": 1, "output_tokens": 1, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}}
        with open(tp, "w") as fh:
            fh.write(json.dumps(line) + "\n")
        ev = json.dumps({"transcript_path": tp, "session_id": "s"})
        run(self.prj, ".claude/hooks/record_tokens.py", stdin=ev)
        self.assertTrue(os.path.isfile(os.path.join(self.prj, "metrics", "tokens.jsonl")))
        run(self.tpl, ".claude/hooks/record_tokens.py", stdin=ev)
        self.assertFalse(os.path.isfile(os.path.join(self.tpl, "metrics", "tokens.jsonl")))


if __name__ == "__main__":
    unittest.main()
