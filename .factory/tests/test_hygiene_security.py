"""Security hygiene tests (supply chain pins, temp files, escaping, argument validation). No network."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))

import skill_frontmatter  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class SkillInstall(unittest.TestCase):
    def test_frontmatter_forced_lf(self):
        out = skill_frontmatter.force_disable("---\nname: x\n---\nbody\n")
        self.assertIn("disable-model-invocation: true", out)
        self.assertTrue(out.endswith("body\n"))

    def test_frontmatter_crlf(self):
        out = skill_frontmatter.force_disable("---\r\nname: x\r\n---\r\nbody\r\n")
        self.assertIn("disable-model-invocation: true", out)
        self.assertNotIn("\n---\nbody", out)  # still CRLF throughout
        self.assertTrue(out.endswith("body\r\n"))

    def test_existing_false_replaced(self):
        for val in ("false", "False", "'no'", ""):
            out = skill_frontmatter.force_disable("---\nname: x\ndisable-model-invocation: %s\n---\nb\n" % val)
            self.assertEqual(out.count("disable-model-invocation"), 1)
            self.assertIn("disable-model-invocation: true", out)

    def test_missing_frontmatter_fails(self):
        with self.assertRaises(ValueError):
            skill_frontmatter.force_disable("# no frontmatter\n")
        p = os.path.join(tempfile.mkdtemp(), "SKILL.md")
        with open(p, "w") as fh:
            fh.write("# no frontmatter\n")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "skill_frontmatter.py"), p],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no frontmatter", r.stderr)

    def test_name_validation_rejects_traversal(self):
        for bad in ("../x", "-x", "A", "a/b", ".."):
            r = subprocess.run(["bash", os.path.join(ROOT, "scripts", "install-skill.sh"), bad],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, bad)
            self.assertIn("invalid skill name", r.stderr)

    def test_factory_refs_are_full_shas(self):
        skills = json.loads(read("factory.json"))["integrations"]["skills"]
        self.assertTrue(skills)
        for name, s in skills.items():
            self.assertRegex(s["ref"], r"^[0-9a-f]{40}$", name)

    def test_install_script_verifies_sha(self):
        src = read("scripts", "install-skill.sh")
        self.assertIn("rev-parse HEAD", src)
        self.assertIn("checkout --quiet --detach FETCH_HEAD", src)

    def test_codegraph_pinned_and_no_curl_sh(self):
        src = read("scripts", "install-codegraph.sh")
        self.assertIsNone(re.search(r"curl[^\n]*\|\s*(ba)?sh", src))
        self.assertRegex(src, r'CG_VERSION="\d+\.\d+\.\d+"')
        self.assertIn("@colbymchenry/codegraph@$CG_VERSION", src)


class Hygiene(unittest.TestCase):
    def test_pre_push_no_fixed_tmp_logs(self):
        src = read(".githooks", "pre-push")
        self.assertNotIn("/tmp/pre-push-", src)
        self.assertIn("mktemp -d", src)
        self.assertIn("trap", src)

    def test_context_watch_sanitizes_session_id(self):
        import context_watch
        self.assertEqual(context_watch.safe_sid("../../x"), "x")
        self.assertEqual(context_watch.safe_sid("../.."), "unknown")
        self.assertEqual(context_watch.safe_sid("abc-123"), "abc-123")
        d = context_watch.state_dir()
        self.assertIsNotNone(d)
        self.assertEqual(os.stat(d).st_mode & 0o077, 0)

    def test_context_watch_state_stays_in_private_dir(self):
        import context_watch
        d = context_watch.state_dir()
        tr = os.path.join(tempfile.mkdtemp(), "t.jsonl")
        with open(tr, "w") as fh:
            fh.write(json.dumps({"type": "assistant", "message": {"usage": {
                "input_tokens": 500000, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}}) + "\n")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=ROOT)
        r = subprocess.run([sys.executable, os.path.join(ROOT, ".claude", "hooks", "context_watch.py")],
                           input=json.dumps({"transcript_path": tr, "session_id": "../../evil"}),
                           capture_output=True, text=True, env=env)
        self.assertIn("handoff", r.stdout)
        state = os.path.join(d, "ctx-evil")
        self.assertTrue(os.path.isfile(state))
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(d), "evil")))
        os.remove(state)

    def test_dashboard_production_url_and_markdown(self):
        import dashboard
        d = dashboard.collect()
        d["deploy"]["production_url"] = "javascript:alert(1)"
        d["project"]["name"] = "a|b`c*d_e[f]<g>\nh"
        d["metrics"]["alerts"] = ["x|y"]
        html_out = dashboard.render(d)
        self.assertNotIn('href="javascript:', html_out)
        d["deploy"]["production_url"] = "https://ok.example.com"
        self.assertIn('href="https://ok.example.com"', dashboard.render(d))
        md = dashboard.summary(d)
        self.assertIn(r"a\|b\`c\*d\_e\[f\]\<g\> h", md)
        self.assertIn(r"x\|y", md)

    def _wait(self, *args):
        return subprocess.run(["bash", os.path.join(ROOT, "scripts", "wait-for-url.sh"), *args],
                              capture_output=True, text=True, timeout=30)

    def test_wait_for_url_rejects_injection_and_bad_scheme(self):
        marker = os.path.join(tempfile.mkdtemp(), "marker")
        for flag in ("--timeout", "--since"):
            r = self._wait("--url", "http://127.0.0.1:1/", flag, "a[$(touch %s)]" % marker)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertFalse(os.path.exists(marker))
        r = self._wait("--url", "file:///etc/passwd", "--timeout", "1")
        self.assertEqual(r.returncode, 2)
        r = self._wait("--url", "-oevil", "--timeout", "1")
        self.assertEqual(r.returncode, 2)
        self.assertIn("-- \"$URL\"", read("scripts", "wait-for-url.sh"))


if __name__ == "__main__":
    unittest.main()
