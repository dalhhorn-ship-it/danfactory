"""Optional packs (SIZE-2, ADR 0011): packs/autonomy.json, scripts/pack.py, bootstrap.sh without the pack.
No network: the template is a local git repo built from this working tree, standing in for source_repo at a pinned sha."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MANIFEST = os.path.join(ROOT, "packs", "autonomy.json")
HAVE_PACK = os.path.isfile(MANIFEST) and all(os.path.isfile(os.path.join(ROOT, p)) for p in json.load(open(MANIFEST))["files"])
if not HAVE_PACK:
    raise unittest.SkipTest("the autonomy pack is not installed in this copy")
FILES = json.load(open(MANIFEST))["files"]
GIT = ["git", "-c", "user.name=pack-test", "-c", "user.email=pack-test@example.invalid"]


def run(cmd, cwd, **kw):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, **kw)


def tree_files(d):
    out = set()
    for r, ds, fs in os.walk(d):
        ds[:] = [x for x in ds if x not in (".git", "__pycache__", "metrics", "dashboard")]
        out |= {os.path.relpath(os.path.join(r, f), d) for f in fs if not f.endswith(".pyc")}
    return out


def snapshot(dst, quick_pack_tests=False):
    """Copy this working tree (tracked and new, not ignored files) into dst and commit it. Returns the commit sha.
    quick_pack_tests: the copy's pack manifest lists one small test module, so `pack.py add` (which runs the manifest's tests) does not
    rerun the whole autonomy suite a second time; the real manifest's modules all run in the normal suite (criterion 8 checks that)."""
    names = subprocess.run(["git", "-C", ROOT, "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True, text=True,
                           check=True).stdout.split("\0")
    for rel in filter(None, names):
        if os.path.isfile(os.path.join(ROOT, rel)):
            os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, rel), os.path.join(dst, rel))
    if quick_pack_tests:
        mp = os.path.join(dst, "packs", "autonomy.json")
        with open(mp, encoding="utf-8") as fh:
            m = json.load(fh)
        m["tests"] = [t for t in m["tests"] if t.endswith("test_issues.py")]
        with open(mp, "w", encoding="utf-8") as fh:
            json.dump(m, fh, indent=1)
            fh.write("\n")
    subprocess.run(["git", "-C", dst, "init", "-q"], check=True)
    subprocess.run(["git", "-C", dst, "config", "uploadpack.allowAnySHA1InWant", "true"], check=True)
    subprocess.run(["git", "-C", dst, "add", "-A"], check=True)
    subprocess.run(GIT[:1] + ["-C", dst] + GIT[1:] + ["commit", "-q", "-m", "snapshot"], check=True)
    return subprocess.run(["git", "-C", dst, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


class Project:
    """Mixin: a template snapshot plus a bootstrapped light project (one per test class, so the slow classes run in parallel)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="pack-test-")
        cls.tpl = os.path.join(cls.tmp, "template")
        os.makedirs(cls.tpl)
        cls.sha = snapshot(cls.tpl, quick_pack_tests=True)
        cls.proj = os.path.join(cls.tmp, "proj")  # a new project: a copy of the template commit, no origin
        subprocess.run(["git", "clone", "-q", cls.tpl, cls.proj], check=True)
        subprocess.run(["git", "-C", cls.proj, "remote", "remove", "origin"], check=True)
        src = json.load(open(os.path.join(cls.proj, "factory.json")))["template"]["source_repo"]
        # the template's GitHub URL is redirected to the local snapshot (env config; no network, no config file touched)
        cls.env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="url.%s.insteadOf" % cls.tpl,
                       GIT_CONFIG_VALUE_0="https://github.com/" + src, GIT_CEILING_DIRECTORIES=cls.tmp)
        cls.boot = run(["bash", "scripts/bootstrap.sh", "demo", "A demo"], cls.proj, env=cls.env)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def factory(self):
        return json.load(open(os.path.join(self.proj, "factory.json")))


class Bootstrap(Project, unittest.TestCase):
    def test_bootstrap_without_pack_is_light_and_healthy(self):  # criterion 6
        self.assertEqual(self.boot.returncode, 0, self.boot.stderr)
        for rel in FILES:
            self.assertFalse(os.path.exists(os.path.join(self.proj, rel)), rel)
        for keep in ("scripts/acceptance.py", "scripts/sandbox.py", "scripts/gate.py", "scripts/pack.py", "packs/autonomy.json"):
            self.assertTrue(os.path.isfile(os.path.join(self.proj, keep)), keep)
        f = self.factory()
        self.assertEqual(f["template"]["ref"], self.sha)
        self.assertIs(f["packs"]["autonomy"], False)
        c = run(["bash", "scripts/check.sh"], self.proj)
        self.assertEqual(c.returncode, 0, (c.stdout + c.stderr)[-1500:])
        d = run([sys.executable, "scripts/dashboard.py", "--print"], self.proj)
        self.assertEqual(d.returncode, 0, d.stderr[-800:])
        self.assertIn("Autonomy pack not installed: python3 scripts/pack.py add autonomy", d.stdout)
        g = run([sys.executable, "scripts/gate.py", "--base", "HEAD"], self.proj)
        self.assertEqual(g.returncode, 0, g.stdout[-800:] + g.stderr[-300:])
        s = run([sys.executable, "scripts/pack.py", "status"], self.proj)
        self.assertIn("not installed", s.stdout)


class AddRemove(Project, unittest.TestCase):
    def test_add_brings_exactly_the_manifest_then_remove_restores(self):  # criterion 7
        before = tree_files(self.proj)
        f = self.factory()
        f["template"]["source_repo"] = self.tpl  # a local path stands in for the GitHub repo
        f["template"]["ref"] = ""  # as after an offline bootstrap: pack.py finds the template commit itself (NEW-1)
        json.dump(f, open(os.path.join(self.proj, "factory.json"), "w"), indent=2)
        before_with_conf = tree_files(self.proj)
        r = run([sys.executable, "scripts/pack.py", "add", "autonomy"], self.proj)
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
        arrived = tree_files(self.proj) - before_with_conf
        gone_from_index = {"docs/INDEX.md"}
        self.assertEqual({a for a in arrived if a not in gone_from_index}, set(FILES))
        for rel in FILES:  # content equals the pinned commit's
            self.assertEqual(open(os.path.join(self.proj, rel), "rb").read(), open(os.path.join(self.tpl, rel), "rb").read(), rel)
        self.assertIs(self.factory()["packs"]["autonomy"], True)
        self.assertEqual(self.factory()["template"]["ref"], self.sha)
        self.assertIn("installed", run([sys.executable, "scripts/pack.py", "status"], self.proj).stdout)
        r = run([sys.executable, "scripts/pack.py", "remove", "autonomy"], self.proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(tree_files(self.proj), before_with_conf)
        self.assertEqual(before_with_conf - before, set())
        self.assertIs(self.factory()["packs"]["autonomy"], False)

    def test_zz_add_refuses_unpinned_or_unknown_refs_and_changes_nothing(self):
        for ref in ("main", "abc123", "0" * 40):
            f = self.factory()
            f["template"]["source_repo"], f["template"]["ref"] = self.tpl, ref
            json.dump(f, open(os.path.join(self.proj, "factory.json"), "w"), indent=2)
            before = tree_files(self.proj)
            r = run([sys.executable, "scripts/pack.py", "add", "autonomy"], self.proj)
            self.assertEqual(r.returncode, 1, ref)
            self.assertIn("pack:", r.stderr)
            self.assertIn("add --ref <sha>", r.stderr, ref)
            self.assertEqual(tree_files(self.proj), before, ref)
            self.assertIs(self.factory()["packs"]["autonomy"], False)


class TemplateKeepsEverything(unittest.TestCase):
    def test_pack_commands_refuse_in_the_template_repo(self):
        tmp = tempfile.mkdtemp(prefix="pack-test-")
        self.addCleanup(shutil.rmtree, tmp, True)
        d = os.path.join(tmp, "t")
        os.makedirs(d)
        snapshot(d)
        src = json.load(open(os.path.join(d, "factory.json")))["template"]["source_repo"]
        subprocess.run(["git", "-C", d, "remote", "add", "origin", "https://github.com/%s" % src], check=True)
        before = tree_files(d)
        for cmd in ("add", "remove"):
            r = run([sys.executable, "scripts/pack.py", cmd, "autonomy"], d)
            self.assertEqual(r.returncode, 1)
            self.assertIn("template repo itself", r.stderr)
        self.assertEqual(tree_files(d), before)
        self.assertIn("template keeps the full tree", run([sys.executable, "scripts/pack.py", "status"], d).stdout)

    def test_template_tree_is_full_and_check_runs_the_pack_tests(self):  # criterion 8
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import run_tests
        found = {t.split(".")[0] for t in run_tests.ids(unittest.defaultTestLoader.discover(os.path.join(ROOT, ".factory", "tests")))}
        for t in json.load(open(MANIFEST))["tests"]:
            self.assertIn(os.path.splitext(os.path.basename(t))[0], found, "check.sh would not run " + t)
        self.assertIs(json.load(open(os.path.join(ROOT, "factory.json")))["packs"]["autonomy"], True)

    def test_manifest_is_exact_and_safe(self):
        m = json.load(open(MANIFEST))
        self.assertEqual(len(m["files"]), len(set(m["files"])))
        for rel in m["files"]:
            self.assertFalse(os.path.isabs(rel) or ".." in rel.split("/"), rel)
        for base in ("scripts/acceptance.py", "scripts/sandbox.py", "scripts/gate.py", "scripts/pack.py", "scripts/dashboard.py"):
            self.assertNotIn(base, m["files"])


if __name__ == "__main__":
    unittest.main()
