"""FISH-5 criterion 13 (docs/specs/teach-agents-to-fish.md, ADR 0014): the fixer runner reverts `gate.framework` edits and never
writes `Framework-Change`. Autonomy pack test (the runner is pack code); the gate half is in test_fish_framework.py."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
sys.path.insert(0, HERE)
import test_runner as TR  # noqa: E402

FW = "src/framework/**"


class RunnerReverts(unittest.TestCase):
    def test_c13_fixer_framework_edit_reverted_trailer_not_written(self):
        factory = json.dumps({"autonomy": {"enabled": True, "max_attempts": 1, "daily_budget_usd": 5, "run_budget_usd": 2},
                              "gate": {"framework": [FW]}})
        step = {"write": {"textkit/__init__.py": TR.GOOD, "src/framework/auth.py": "x = 1\n"}, "commit": "Framework-Change: self-approved"}
        e = TR.one({"fixer": [step], "review": [{"text": TR.SHIP}]}, files={"factory.json": factory, "src/framework/auth.py": "x = 0\n"})
        try:
            rc, out = e.run("run", "--next")
            self.assertEqual(rc, 1, out)
            self.assertEqual(TR.codes(e), [["fixer-touched-protected"]])
            self.assertEqual(e.calls("review"), [])
            self.assertEqual(TR.sh(e.root, "log", "--all", "--grep=Framework-Change", "--format=%H"), "")
        finally:
            e.cleanup()


if __name__ == "__main__":
    unittest.main()
