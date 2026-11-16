"""SCOUT-1/SCOUT-2: open-source scout agent, routing, template and checker (docs/specs/open-source-scout.md)."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import scout_check  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def note(rec="adopt", lic="MIT", extra="", scouted="yes", cands=3, needs="no"):
    cs = "".join("### %d. lib%d\n- Licence: MIT\n" % (i, i) for i in range(1, cands + 1))
    lic_line = "Licence: %s\n" % lic if lic else ""
    return ("# Scout: x\n\nScouted: %s\n\n## Candidates\n%s\n## Recommendation\nRecommendation: %s\nPick: lib1\n%sNeeds user: %s\n%s"
            % (scouted, cs, rec, lic_line, needs, extra))


class Structure(unittest.TestCase):
    def test_criterion_1_agent_file_and_rosters(self):
        t = read(".claude/agents/oss-scout.md")
        self.assertIn("name: oss-scout", t)
        self.assertIn("model: sonnet", t)
        self.assertTrue(any(x.startswith("**Finding things:**") for x in t.splitlines()))
        r = read("docs/operating-model/AGENT-ROUTING.md")
        self.assertIn("`oss-scout`", r)
        for path in ("software-product", "library-cli", "automation-script"):
            row = next(x for x in r.splitlines() if x.startswith("| %s |" % path))
            self.assertIn("oss-scout", row)

    def test_criterion_2_routing_row_between_prd_and_design(self):
        rows = [x for x in read("docs/operating-model/AGENT-ROUTING.md").splitlines() if x.startswith("| ")]
        i = next(n for n, x in enumerate(rows) if x.startswith("| Scout open source"))
        self.assertTrue(rows[i - 1].startswith("| Acceptance tests"))  # after PRD, before Design
        self.assertTrue(rows[i + 1].startswith("| Design (software)"))
        for word in ("unfamiliar", "oss-scout", "grep/codegraph", "bug fixes"):
            self.assertIn(word, rows[i])

    def test_criterion_3_developer_and_architect_carry_the_rule(self):
        for f in ("developer", "software-architect"):
            t = read(".claude/agents/%s.md" % f)
            self.assertIn("docs/research/<slug>-scout.md", t, f)
            self.assertIn("ask the coordinator for a scout", t, f)

    def test_criterion_4_template_sections_and_cap(self):
        t = read("docs/research/_TEMPLATE-scout.md")
        self.assertLessEqual(len(t.splitlines()), 60)
        for s in ("## Candidates", "## Trade-offs", "## Recommendation", "Recommendation: adopt | borrow | build",
                  "Licence:", "Needs user:", "Scouted:"):
            self.assertIn(s, t)
        self.assertNotEqual(subprocess.call([sys.executable, os.path.join(ROOT, "scripts", "scout_check.py"),
                                             os.path.join(ROOT, "docs/research/_TEMPLATE-scout.md")],
                                            stderr=subprocess.DEVNULL), 0)  # unfilled template is not a note

    def test_criterion_6_and_7_agent_and_mission_rules(self):
        a = read(".claude/agents/oss-scout.md")
        self.assertIn("build from scratch (not scouted)", a)
        self.assertIn("Never block the build", a)
        self.assertIn("never ask the user", a)
        self.assertIn("Decision log as an assumption", a)
        m = read("docs/policies/mission.md")
        self.assertIn("oss-scout", m)
        self.assertIn("assumption", m)

    def test_bootstrap_keeps_only_the_template(self):
        self.assertIn("_TEMPLATE-scout.md", read("scripts/bootstrap.sh"))


class Checker(unittest.TestCase):
    def test_criterion_5_adopt_needs_a_licence_line(self):
        self.assertTrue(any("licence" in p for p in scout_check.problems(note(lic=None))))
        self.assertEqual(scout_check.problems(note()), [])

    def test_borrow_needs_a_licence_line_too(self):
        self.assertTrue(scout_check.problems(note("borrow", lic=None)))
        self.assertEqual(scout_check.problems(note("borrow", lic="Apache-2.0")), [])

    def test_build_needs_no_licence(self):
        self.assertEqual(scout_check.problems(note("build", lic=None)), [])

    def test_copyleft_unknown_or_none_needs_user(self):
        for lic in ("GPL-3.0", "AGPL-3.0", "LGPL-2.1", "SSPL-1.0", "unknown", "none"):
            self.assertTrue(scout_check.problems(note(lic=lic)), lic)
            self.assertEqual(scout_check.problems(note(lic=lic, needs="yes")), [], lic)

    def test_single_valid_recommendation(self):
        self.assertTrue(scout_check.problems("# x\nno recommendation\n"))
        self.assertTrue(scout_check.problems(note() + "Recommendation: build\n"))
        self.assertTrue(scout_check.problems(note("adopt | borrow")))

    def test_caps(self):
        self.assertEqual(scout_check.problems(note(cands=5)), [])
        self.assertTrue(any("candidates" in p for p in scout_check.problems(note(cands=6))))
        self.assertTrue(any("lines" in p for p in scout_check.problems(note(extra="x\n" * 60))))

    def test_unscouted_cannot_adopt_or_borrow(self):
        self.assertTrue(scout_check.problems(note(scouted="no (network blocked)")))
        self.assertEqual(scout_check.problems(note("build", lic=None, scouted="no (network blocked)")), [])

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            for name, text, code in (("bad.md", note(lic=None), 1), ("ok.md", note(), 0)):
                p = os.path.join(d, name)
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(text)
                r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "scout_check.py"), p],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, code, r.stderr)
                if code:
                    self.assertIn("licence", r.stderr)


if __name__ == "__main__":
    unittest.main()
