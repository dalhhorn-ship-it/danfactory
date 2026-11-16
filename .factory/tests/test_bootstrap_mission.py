"""bootstrap.sh must not leak the template's state into a new project (handoff note, exemption, missions, gate.prd)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
from _common import template_mode  # noqa: E402

if not template_mode(root=ROOT):
    raise unittest.SkipTest("only meaningful in the template repo itself")
GITC = ["git", "-c", "user.name=t", "-c", "user.email=t@t.invalid", "-c", "commit.gpgsign=false"]


class T(unittest.TestCase):
    def test_new_project_starts_clean(self):
        tmp = tempfile.mkdtemp(prefix="bootmis-")
        self.addCleanup(shutil.rmtree, tmp, True)
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=tmp, GIT_TERMINAL_PROMPT="0")
        for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            env.pop(k, None)
        names = subprocess.run(["git", "-C", ROOT, "ls-files", "-co", "--exclude-standard", "-z"], capture_output=True,
                               text=True, check=True).stdout.split("\0")
        for n in names:
            if n and os.path.isfile(os.path.join(ROOT, n)) and not os.path.islink(os.path.join(ROOT, n)):
                os.makedirs(os.path.dirname(os.path.join(tmp, n)) or tmp, exist_ok=True)
                shutil.copy2(os.path.join(ROOT, n), os.path.join(tmp, n))
        for rel, text in (("docs/missions/old.md", "x\n"), (".factory/mission-state.json", "{}\n"),
                          (".factory/HANDOFF.md", "template note\n"), (".factory/prd-exemption", "bugfix\n")):
            with open(os.path.join(tmp, rel), "w") as fh:
                fh.write(text)
        subprocess.run(["git", "init", "-q"], cwd=tmp, env=env, check=True)
        subprocess.run(["git", "add", "-A"], cwd=tmp, env=env, check=True)
        subprocess.run(GITC + ["commit", "-q", "-m", "first"], cwd=tmp, env=env, check=True)
        r = subprocess.run(["bash", "scripts/bootstrap.sh", "--template-ref", "0" * 40, "demo"], cwd=tmp, env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        for rel in (".factory/HANDOFF.md", ".factory/prd-exemption", ".factory/mission-state.json", "docs/missions/old.md"):
            self.assertFalse(os.path.exists(os.path.join(tmp, rel)), rel)
        self.assertTrue(os.path.isfile(os.path.join(tmp, "docs", "missions", "_TEMPLATE.md")))
        self.assertEqual(json.load(open(os.path.join(tmp, "factory.json")))["gate"]["prd"], "required")
        self.assertEqual(json.load(open(os.path.join(ROOT, "factory.json")))["gate"]["prd"], "advisory")


if __name__ == "__main__":
    unittest.main()
