"""adopt.py / adopt_scan.py must treat the target as untrusted: no symlink following, no target git config."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ADOPT = os.path.join(ROOT, "scripts", "adopt.py")
SCAN = os.path.join(ROOT, "scripts", "adopt_scan.py")
# adopt.py itself needs the template's CI file; an already-adopted project (which receives this test) has none.
IS_TEMPLATE = os.path.exists(os.path.join(ROOT, ".github", "workflows", "ci.yml"))


def git_commit(d, *extra):
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-qm", "init", *extra], cwd=d, check=True)


def write(path, body="x\n", mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(body)
    if mode is not None:
        os.chmod(path, mode)


class AdoptSecurity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.target = os.path.join(self.tmp, "target")
        os.makedirs(self.target)

    def adopt(self, *args):
        return subprocess.run([sys.executable, ADOPT, "--target", self.target, *args], capture_output=True, text=True)

    @unittest.skipUnless(IS_TEMPLATE, "adopt.py runs from the template only")
    def test_symlinks_not_followed(self):
        outside = os.path.join(self.tmp, "outside_dir")
        write(os.path.join(outside, "keep.sh"), "echo hi\n", 0o600)
        rcfile = os.path.join(self.tmp, "rcfile")
        write(rcfile, "rc\n", 0o644)
        secret = os.path.join(self.tmp, "secret")
        write(secret, "s3cret\n", 0o600)
        write(os.path.join(self.target, "README.md"), "# t\n")
        os.symlink(outside, os.path.join(self.target, ".githooks"))
        os.symlink(rcfile, os.path.join(self.target, "CLAUDE.md"))
        os.makedirs(os.path.join(self.target, "scripts"))
        os.symlink(secret, os.path.join(self.target, "scripts", "evil.sh"))
        git_commit(self.target)
        before = {p: (os.stat(p).st_mode, open(p).read()) for p in (rcfile, secret, os.path.join(outside, "keep.sh"))}

        for args in ((), ("--apply",)):
            r = self.adopt(*args)
            self.assertEqual(r.returncode, 0, r.stderr)
            for needle in (".githooks", "CLAUDE.md", "scripts/evil.sh"):
                self.assertTrue(any("skip" in l and "symlink" in l and needle in l for l in r.stdout.splitlines()),
                                "%s not reported as skipped symlink in %s run:\n%s" % (needle, args, r.stdout))
        for p, (mode, body) in before.items():
            self.assertEqual(os.stat(p).st_mode, mode, p)
            self.assertEqual(open(p).read(), body, p)
        self.assertEqual(os.listdir(outside), ["keep.sh"])
        self.assertTrue(os.path.islink(os.path.join(self.target, ".githooks")))

    def test_scan_report_symlink_refused(self):
        write(os.path.join(self.target, "package.json"), "{}")
        victim = os.path.join(self.tmp, "victim.md")
        write(victim, "orig\n")
        os.makedirs(os.path.join(self.target, "docs"))
        os.symlink(victim, os.path.join(self.target, "docs", "ADOPTION-REPORT.md"))
        r = subprocess.run([sys.executable, SCAN, "--target", self.target], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(open(victim).read(), "orig\n")

    def test_scan_ignores_target_git_config(self):
        write(os.path.join(self.target, "package.json"), "{}")
        git_commit(self.target)
        marker = os.path.join(self.tmp, "marker")
        hook = os.path.join(self.tmp, "fsm.sh")
        write(hook, "#!/bin/sh\ntouch %s\n" % marker, 0o755)
        subprocess.run(["git", "config", "core.fsmonitor", hook], cwd=self.target, check=True)
        r = subprocess.run([sys.executable, SCAN, "--target", self.target, "--print"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(marker), "target's core.fsmonitor ran")

    @unittest.skipUnless(IS_TEMPLATE, "adopt.py runs from the template only")
    def test_foreign_hooks_and_scripts_listed(self):
        write(os.path.join(self.target, ".githooks", "post-commit"), "#!/bin/sh\n", 0o755)
        write(os.path.join(self.target, "scripts", "foo.sh"), "#!/bin/sh\n", 0o755)
        r = self.adopt()
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertTrue(any("note" in l and ".githooks/post-commit" in l and "foreign hook" in l for l in lines), r.stdout)
        self.assertTrue(any("note" in l and "scripts/foo.sh" in l and "foreign script" in l for l in lines), r.stdout)

    def test_dev_vars_flagged(self):
        write(os.path.join(self.target, "package.json"), "{}")
        write(os.path.join(self.target, ".dev.vars.staging"), "KEY=1\n")
        write(os.path.join(self.target, ".dev.vars.example"), "KEY=\n")
        git_commit(self.target)
        r = subprocess.run([sys.executable, SCAN, "--target", self.target], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        scan = json.load(open(os.path.join(self.target, "docs", "adoption-scan.json")))
        hit = [f for f in scan["findings"] if "committed" in f["title"]]
        self.assertEqual(len(hit), 1)
        self.assertIn(".dev.vars.staging", hit[0]["detail"])
        self.assertNotIn("example", hit[0]["detail"])


if __name__ == "__main__":
    unittest.main()
