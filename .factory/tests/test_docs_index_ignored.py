"""docs_index.py must not link to git-ignored files: they exist locally (generated) but not in a clean checkout."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def git(d, *a):
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=os.path.dirname(d))
    return subprocess.run(["git", "-C", d, *a], check=True, capture_output=True, text=True, env=env)


class IgnoredTargets(unittest.TestCase):
    def test_ignored_generated_file_is_not_a_link_target(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "scripts"))
        os.makedirs(os.path.join(d, "docs"))
        os.makedirs(os.path.join(d, "dashboard"))
        shutil.copy(os.path.join(ROOT, "scripts", "docs_index.py"), os.path.join(d, "scripts"))
        for f in ("factory.json",):
            if os.path.isfile(os.path.join(ROOT, f)):
                shutil.copy(os.path.join(ROOT, f), d)
        with open(os.path.join(d, ".gitignore"), "w") as fh:
            fh.write("/dashboard/\n")
        with open(os.path.join(d, "docs", "a.md"), "w") as fh:
            fh.write("# A\n\n> Doc A.\n\nSee dashboard/SUMMARY.md and docs/b.md.\n")
        with open(os.path.join(d, "docs", "b.md"), "w") as fh:
            fh.write("# B\n\n> Doc B.\n")
        with open(os.path.join(d, "dashboard", "SUMMARY.md"), "w") as fh:
            fh.write("# generated\n")
        git(d, "init", "-q")
        r = subprocess.run([sys.executable, "-B", os.path.join(d, "scripts", "docs_index.py")], cwd=d,
                           capture_output=True, text=True, env=dict(os.environ, GIT_CEILING_DIRECTORIES=os.path.dirname(d)))
        self.assertEqual(r.returncode, 0, r.stderr)
        g = json.load(open(os.path.join(d, "docs", "knowledge-graph.json")))
        edges = {(e["from"], e["to"]) for e in g["edges"]}
        self.assertIn(("docs/a.md", "docs/b.md"), edges)
        self.assertNotIn(("docs/a.md", "dashboard/SUMMARY.md"), edges)


if __name__ == "__main__":
    unittest.main()
