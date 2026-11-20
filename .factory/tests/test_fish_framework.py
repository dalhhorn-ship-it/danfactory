"""FISH-5 (docs/specs/teach-agents-to-fish.md criteria 10-13): framework guidance, `gate.framework` and the
`Framework-Change` trailer (ADR 0014), the runner's revert. Temp git projects only."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, HERE)
import gate  # noqa: E402
import test_gate  # noqa: E402

FW = "src/framework/**"
FACTORY = {"commands": {}, "budgets": {"test_seconds": 120}, "gate": {"framework": [FW]}}


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class Guidance(unittest.TestCase):
    def test_c10_three_files_tell_agents_the_pattern(self):
        for rel in ("docs/operating-model/paths/software-product.md", "docs/operating-model/paths/library-cli.md",
                    ".claude/agents/software-architect.md"):
            t = read(rel)
            for word in ("framework folder", "default", "override hook", "gate.framework"):
                self.assertIn(word, t, "%s lacks %r" % (rel, word))

    def test_c10_defaults_and_docs(self):
        self.assertEqual(gate.DEFAULTS["framework"], [])
        self.assertEqual(json.loads(read("factory.json"))["gate"]["framework"], [])
        doc = read("docs/policies/merge-gate.md")
        for word in ("Framework-Change", "gate.framework", "TD-012"):
            self.assertIn(word, doc)
        self.assertIn("Framework-Change", read(".claude/agents/developer.md"))


class FrameworkGate(test_gate.Base):
    def repo(self, factory=FACTORY):
        return super().repo(json.loads(json.dumps(factory)))

    def change(self, r, trailer="", path="src/framework/auth.py", text="x = 1\n"):
        r.write(path, text)
        r.commit("change", trailer)

    def test_c11_without_trailer_fails_protected_path(self):
        r = self.repo()
        self.change(r)
        c = r.check("protected")
        self.assertEqual((c["status"], c["codes"]), ("fail", ["protected-path"]))
        self.assertIn("Framework-Change", c["detail"])
        self.assertIn("gate.framework", c["detail"])

    def test_c11_wrong_trailer_and_empty_reason_fail(self):
        for trailer in ("Acceptance-Change: demo", "Framework-Change:  ", "Refs: X-1"):
            r = self.repo()
            self.change(r, trailer)
            self.assertEqual(r.check("protected")["codes"], ["protected-path"], trailer)

    def test_c11_uncommitted_framework_change_fails(self):
        r = self.repo()
        r.write("src/framework/auth.py", "x = 1\n")
        self.assertEqual(r.check("protected")["codes"], ["protected-path"])

    def test_c12_trailer_passes(self):
        r = self.repo()
        self.change(r, "Framework-Change: new auth scheme approved by the user")
        c = r.check("protected")
        self.assertEqual((c["status"], c["codes"]), ("pass", []))

    def test_c12_every_commit_in_range_needs_it(self):
        r = self.repo()
        self.change(r, "Framework-Change: ok")
        self.change(r, "", text="x = 2\n")
        self.assertEqual(r.check("protected")["codes"], ["protected-path"])

    def test_c12_trailer_does_not_unlock_protected_paths(self):
        r = self.repo()
        self.change(r, "Framework-Change: sneaky", path="tests/acceptance/demo/test_x.py")
        c = r.check("protected")
        self.assertEqual(c["codes"], ["protected-path"])
        self.assertIn("Acceptance-Change", c["detail"])

    def test_c12_acceptance_change_does_not_unlock_framework(self):
        r = self.repo()
        self.change(r, "Acceptance-Change: demo")
        self.assertEqual(r.check("protected")["codes"], ["protected-path"])

    def test_c12_path_in_both_lists_needs_both(self):
        f = dict(FACTORY, gate={"framework": [FW], "protected": ["tests/acceptance/**", FW]})
        for trailer, ok in (("Framework-Change: a", False), ("Acceptance-Change: demo", False),
                            ("Framework-Change: a\nAcceptance-Change: demo", True)):
            r = self.repo(f)
            self.change(r, trailer)
            self.assertEqual(r.check("protected")["status"], "pass" if ok else "fail", trailer)

    def test_default_empty_list_changes_nothing(self):
        r = self.repo({"commands": {}, "budgets": {"test_seconds": 120}})
        self.change(r)
        self.assertEqual(r.check("protected")["status"], "pass")

    def test_other_paths_unaffected(self):
        r = self.repo()
        self.change(r, path="src/app.py")
        self.assertEqual(r.check("protected")["status"], "pass")


if __name__ == "__main__":
    unittest.main()
