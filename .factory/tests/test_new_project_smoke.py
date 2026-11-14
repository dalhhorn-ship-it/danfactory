"""New-project smoke (NEW-3, docs/specs/new-project-readiness.md criterion 5).

Bootstraps a temp copy of this template the way "Use this template" would (same files, its own first commit; a local bare
repo stands in for the upstream, so there is no network) and checks what a user sees. Two layers:
  fast (every run, a few seconds): template ref found, template-files list, no template-owned flags or setup noise in the
      dashboard, PRD guard blocks a product write in brainstorm;
  full (NEW_PROJECT_SMOKE=1, its own CI step; about 45 s): the project's check.sh and the gate pass, and
      `pack.py add autonomy` installs from the stand-in remote at the recorded ref. The two halves run in parallel.
Only meaningful in the template repo; a bootstrapped project skips it (and bootstrap deletes it). Every git call names its
cwd and GIT_CEILING_DIRECTORIES keeps git inside the temp dirs (TD-021)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
from _common import template_mode  # noqa: E402

if not template_mode(root=ROOT):
    raise unittest.SkipTest("only meaningful in the template repo itself")
FULL = os.environ.get("NEW_PROJECT_SMOKE") == "1"
GITC = ["git", "-c", "user.name=smoke", "-c", "user.email=smoke@example.invalid", "-c", "commit.gpgsign=false"]


def sh(cmd, cwd, env, **kw):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, **kw)


class Smoke:
    """upstream (bare, commit U), and two copies of U's files with their own first commit, bootstrapped."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="newproj-")
        src = json.load(open(os.path.join(ROOT, "factory.json")))["template"]["source_repo"]
        # git redirects the template's GitHub URL to the local bare repo (env config: no real config file is touched)
        cls.env = dict(os.environ, GIT_CEILING_DIRECTORIES=cls.tmp, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_COUNT="1",
                       GIT_CONFIG_KEY_0="url.%s.insteadOf" % os.path.join(cls.tmp, "upstream.git"),
                       GIT_CONFIG_VALUE_0="https://github.com/" + src)
        for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            cls.env.pop(k, None)
        names = subprocess.run(["git", "-C", ROOT, "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True,
                               text=True, check=True).stdout.split("\0")
        cls.names = [n for n in names if n and os.path.isfile(os.path.join(ROOT, n)) and not os.path.islink(os.path.join(ROOT, n))]
        work = os.path.join(cls.tmp, "work")
        cls.copy(work)
        sh(["git", "init", "-q"], work, cls.env, check=True)
        sh(["git", "config", "uploadpack.allowAnySHA1InWant", "true"], work, cls.env, check=True)
        sh(["git", "add", "-A"], work, cls.env, check=True)
        sh(GITC + ["commit", "-q", "-m", "upstream template"], work, cls.env, check=True)
        cls.upstream_sha = sh(["git", "rev-parse", "HEAD"], work, cls.env).stdout.strip()
        sh(["git", "clone", "-q", "--bare", work, os.path.join(cls.tmp, "upstream.git")], cls.tmp, cls.env, check=True)
        sh(["git", "-C", os.path.join(cls.tmp, "upstream.git"), "config", "uploadpack.allowAnySHA1InWant", "true"], cls.tmp, cls.env, check=True)
        cls.projects = {}

    @classmethod
    def copy(cls, dst):
        for n in cls.names:
            os.makedirs(os.path.dirname(os.path.join(dst, n)) or dst, exist_ok=True)
            shutil.copy2(os.path.join(ROOT, n), os.path.join(dst, n))

    @classmethod
    def new_project(cls, name):
        """A fresh copy as GitHub makes it (its own first commit, no relation to upstream), then bootstrapped."""
        d = os.path.join(cls.tmp, name)
        work = os.path.join(cls.tmp, "work")
        shutil.copytree(work, d, ignore=shutil.ignore_patterns(".git"))
        sh(["git", "init", "-q"], d, cls.env, check=True)
        sh(["git", "add", "-A"], d, cls.env, check=True)
        sh(GITC + ["commit", "-q", "-m", "Initial commit"], d, cls.env, check=True)
        boot = sh(["bash", "scripts/bootstrap.sh", "demo", "A demo"], d, cls.env)
        return d, boot

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


class Fast(Smoke, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.proj, cls.boot = cls.new_project("fast")

    def factory(self):
        return json.load(open(os.path.join(self.proj, "factory.json")))

    def test_bootstrap_finds_the_upstream_commit_and_lists_template_files(self):
        self.assertEqual(self.boot.returncode, 0, self.boot.stderr[-800:])
        self.assertEqual(self.factory()["template"]["ref"], self.upstream_sha)  # not the copy's own first commit
        listed = open(os.path.join(self.proj, ".factory", "template-files.txt")).read().splitlines()
        self.assertGreater(len(listed), 100)
        self.assertTrue(any(x.endswith(" scripts/gate.py") for x in listed))
        self.assertFalse(any(x.endswith(" README.md") or x.endswith(" docs/BACKLOG.md") for x in listed))  # bootstrap rewrote them

    def test_dashboard_has_no_template_owned_flags_or_setup_noise(self):
        r = sh([sys.executable, "scripts/dashboard.py"], self.proj, self.env)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        d = json.load(open(os.path.join(self.proj, "dashboard", "data.json")))
        self.assertEqual(d["hotspots"]["size"]["flags"], [])
        self.assertGreater(d["hotspots"]["size"]["template_files"], 100)
        self.assertEqual(d["debt"]["signals"]["marker_total"], 0)
        self.assertEqual(d["debt"]["signals"]["large_files"], [])
        self.assertEqual(d["hotspots"]["files"], [])
        self.assertEqual(d["gates"]["items_no_prd"], 0, d["gates"]["items"])

    def test_edited_template_file_counts_as_project_code(self):
        d, boot = self.new_project("edited")
        self.assertEqual(boot.returncode, 0)
        p = os.path.join(d, "scripts", "gate.py")
        with open(p, "a") as fh:
            fh.write("# TODO tidy\n" * 3)
        r = sh([sys.executable, "scripts/dashboard.py"], d, self.env)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        data = json.load(open(os.path.join(d, "dashboard", "data.json")))
        self.assertGreaterEqual(data["debt"]["signals"]["marker_total"], 3)
        self.assertIn("scripts/gate.py", [f["subject"] for f in data["hotspots"]["size"]["flags"]])

    def test_prd_guard_blocks_a_product_write_in_brainstorm(self):
        self.assertEqual(self.factory()["phase"], "brainstorm")
        ev = {"tool_name": "Write", "tool_input": {"file_path": os.path.join(self.proj, "src", "app.py")}, "cwd": self.proj}
        r = subprocess.run([sys.executable, os.path.join(self.proj, ".claude", "hooks", "guard_prd_write.py")], input=json.dumps(ev),
                           capture_output=True, text=True, env=dict(self.env, CLAUDE_PROJECT_DIR=self.proj))
        self.assertEqual(r.returncode, 2, r.stderr)

    def test_pack_add_with_a_missing_ref_says_how_to_fix_it(self):
        f = self.factory()
        f["template"]["ref"] = "0" * 40
        d, _ = self.new_project("badref")
        json.dump(f, open(os.path.join(d, "factory.json"), "w"), indent=2)
        r = sh([sys.executable, "scripts/pack.py", "add", "autonomy"], d, self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("pack.py add --ref <sha>", r.stderr)
        self.assertIn("--template-ref <sha>", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


@unittest.skipUnless(FULL, "full new-project smoke runs in its own CI step (NEW_PROJECT_SMOKE=1)")
class Full(Smoke, unittest.TestCase):
    def test_check_gate_and_pack_add_on_a_new_project(self):
        out = {}

        def verify():
            d, boot = self.new_project("verify")
            out["boot"] = boot
            out["check"] = sh(["bash", "scripts/check.sh"], d, self.env)
            out["gate"] = sh([sys.executable, "scripts/gate.py", "--base", "HEAD"], d, self.env)

        def add():
            d, _ = self.new_project("addpack")
            out["add"] = sh([sys.executable, "scripts/pack.py", "add", "autonomy"], d, self.env)
            out["addf"] = json.load(open(os.path.join(d, "factory.json")))
            out["addfile"] = os.path.isfile(os.path.join(d, "scripts", "runner.py"))

        ts = [threading.Thread(target=verify), threading.Thread(target=add)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(out["boot"].returncode, 0, out["boot"].stderr[-800:])
        self.assertEqual(out["check"].returncode, 0, (out["check"].stdout + out["check"].stderr)[-1500:])
        self.assertEqual(out["gate"].returncode, 0, out["gate"].stdout[-1200:] + out["gate"].stderr[-300:])
        self.assertEqual(out["add"].returncode, 0, out["add"].stdout[-1200:] + out["add"].stderr[-1200:])
        self.assertIs(out["addf"]["packs"]["autonomy"], True)
        self.assertEqual(out["addf"]["template"]["ref"], self.upstream_sha)
        self.assertTrue(out["addfile"])


if __name__ == "__main__":
    unittest.main()
