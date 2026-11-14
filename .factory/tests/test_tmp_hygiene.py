"""The parallel test runner must leave nothing behind in the temp dir (a full run once left ~35,000 directories)."""
import os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TmpHygiene(unittest.TestCase):
    def test_runner_leaves_no_temp_dirs(self):
        base = tempfile.mkdtemp(prefix="hyg-")
        self.addCleanup(__import__("shutil").rmtree, base, True)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "run_tests.py"), "test_issues", "test_learn"],
                           cwd=ROOT, capture_output=True, text=True, env={**os.environ, "TMPDIR": base})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.listdir(base), [], "temp dirs leaked by the tests")
