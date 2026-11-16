"""Mission hardening, slice P (docs/specs/mission-hardening.md criteria 1, 2, 5, 6, 8): tests admitted before by-mission
product writes at L2+, live-only feature cap with a frozen Decision-log approval list, factory.json caps and ceilings."""
import contextlib
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_mission_approval as TA  # noqa: E402
import gate  # noqa: E402
import mission_report  # noqa: E402

M, cli, _prd = TA.M, TA.cli, TA._prd


def admit(p, spec="night-one"):
    adm = {"tests/acceptance/test_x.py::T::test_c1_a": {"prd": spec, "criterion": 1}}
    p.write("tests/acceptance/manifest.json", json.dumps({"prds": {}, "admitted": adm}))


def to_branch(p, rigor="L2"):
    p.write("factory.json", json.dumps({"phase": "build", "gate": {}, "rigor": rigor}))
    p.commit("rigor")
    p.g("switch", "-q", "-c", "mission/night")


def run(p, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(list(args), root=p.root)
    return rc, out.getvalue(), err.getvalue()


class TestsBeforeCode(TA.Base):  # criteria 1 and 2
    def test_l2_blocks_until_admitted_then_allows(self):
        p = self.proj()
        to_branch(p)
        r = p.edit("src/app.py")
        self.assertEqual(r.returncode, 2)
        self.assertIn("tests not admitted for night-one", r.stderr)
        self.assertIn("acceptance.py admit", r.stderr)
        self.assertIn("park the item `[!]`", r.stderr)
        self.assertEqual(p.edit("tests/acceptance/test_x.py").returncode, 0)  # the test-writer can work
        admit(p)
        self.assertEqual(p.edit("src/app.py").returncode, 0)

    def test_below_l2_and_unknown_rigor_unchanged(self):
        for rigor in ("L1", ""):
            p = self.proj()
            to_branch(p, rigor)
            self.assertEqual(p.edit("src/app.py").returncode, 0, rigor)

    def test_off_branch_and_no_mission_unchanged(self):
        p = self.proj()
        p.write("factory.json", json.dumps({"phase": "build", "gate": {}, "rigor": "L3"}))
        self.assertEqual(p.edit("src/app.py").returncode, 0)  # mission active but HEAD is not its branch
        q = self.proj(mission=False)
        q.write("docs/specs/night-one.md", TA.PRD % "approved · 2026-11-16")
        q.write("factory.json", json.dumps({"phase": "build", "gate": {}, "rigor": "L3"}))
        self.assertEqual(q.edit("src/app.py").returncode, 0)

    def test_rigor_reads_operating_model(self):
        p = self.proj(mission=False)
        self.assertEqual(M.rigor_level(p.root), -1)
        p.write("docs/OPERATING-MODEL.md", "## Path and rigor\n_Primary path, rigor level (L0–L3) and why_\n\n## Agents\nL3\n")
        self.assertEqual(M.rigor_level(p.root), -1)
        p.write("docs/OPERATING-MODEL.md", "## Path and rigor\nsoftware-product, rigor L2 (ADR 1)\n\n## Agents\nL3\n")
        self.assertEqual(M.rigor_level(p.root), 2)

    def test_gate_code_for_by_mission_commit_without_admission(self):
        p = self.proj()
        p.write("factory.json", json.dumps({"phase": "build", "gate": {}, "rigor": "L2"}))
        p.commit("rigor")
        base = p.g("rev-parse", "HEAD").strip()
        p.write("src/app.py", "x = 1\n")
        p.commit("code", trailer="Refs: NIGHT-1")
        admit(p)  # admitted only after the commit: not enough
        p.commit("late admit")
        chk = {x["id"]: x for x in gate.run_gate(p.root, base, {"prd"})["checks"]}["prd"]
        self.assertEqual(chk["status"], "fail")
        self.assertIn("mission-tests-not-admitted", chk["codes"])
        base = p.g("rev-parse", "HEAD").strip()
        p.write("src/app.py", "x = 2\n")
        p.commit("code2", trailer="Refs: NIGHT-1")
        chk = {x["id"]: x for x in gate.run_gate(p.root, base, {"prd"})["checks"]}["prd"]
        self.assertEqual(chk["status"], "pass", chk["detail"])

    def test_parked_items_do_not_block_and_report_lists_reason(self):
        bl = ("# Backlog\n\n## Milestone: M5 — Night (mission: night)\n- [!] NIGHT-1 One, parked: tests not admissible "
              "(docs/specs/night-one.md)\n- [ ] NIGHT-2 Two (docs/specs/night-two.md)\n")
        p = self.proj(backlog=bl)
        m = M.load(p.root, "night")
        self.assertEqual(M.next_item(p.root, m)["id"], "NIGHT-2")
        p.write("docs/BACKLOG.md", bl.replace("- [ ] NIGHT-2", "- [x] NIGHT-2"))
        self.assertIsNone(M.next_item(p.root, m))  # only a parked item left: the mission can end
        self.assertIn("NIGHT-1: tests not admissible", "\n".join("%s: %s" % (x["ref"], x["why"]) for x in M.parked(p.root, m)))
        self.assertIn("NIGHT-1: tests not admissible", mission_report.build(p.root, m, "done")[0])


class FeatureCap(TA.Base):  # criterion 5
    BL = ("# Backlog\n\n## Milestone: M5 — Night (mission: night)\n- [~] NIGHT-1 One (docs/specs/night-one.md)\n"
          "- [ ] NIGHT-2 Two (docs/specs/night-two.md)\n- [ ] OTHER-1 Stray (docs/specs/stray.md)\n"
          "- [ ] NIGHT-4 Four (docs/specs/night-else.md)\n")

    def test_approve_enforces_prefix_link_and_live_cap(self):
        p = self.proj(backlog=self.BL, features="1", approved=())
        self.assertNotEqual(run(p, "approve", "night", "stray")[0], 0)  # prefix
        self.assertNotEqual(run(p, "approve", "night", "night-unlinked")[0], 0)  # not linked
        self.assertNotEqual(run(p, "approve", "night", "night-missing")[0], 0)
        self.assertFalse(M.approval(p.root, "night", "night-one")[0])  # not listed: not approved
        rc, _out, err = run(p, "approve", "night", "night-one")
        self.assertEqual(rc, 0, err)
        self.assertIn("Approved PRD: night-one", M._read(M.load(p.root, "night")["path"]))
        self.assertTrue(M.approval(p.root, "night", "night-one")[0])
        rc, _o, err = run(p, "approve", "night", "night-else")
        self.assertEqual(rc, 1)
        self.assertIn("feature cap", err)
        self.assertEqual(run(p, "approve", "night", "night-one")[0], 0)  # idempotent

    def test_parked_item_frees_a_place_and_later_edits_do_not_unapprove(self):
        p = self.proj(backlog=self.BL, features="1", approved=())
        self.assertEqual(run(p, "approve", "night", "night-one")[0], 0)
        p.write("docs/BACKLOG.md", self.BL.replace("- [~] NIGHT-1 One", "- [!] NIGHT-1 One, parked: vague"))
        self.assertEqual(run(p, "approve", "night", "night-two")[0], 0)  # [!] does not count
        p.write("docs/BACKLOG.md", self.BL.replace("- [~] NIGHT-1", "- [-] NIGHT-1").replace("- [ ] NIGHT-2 Two", "- [!] NIGHT-2 Two"))
        for s in ("night-one", "night-two"):  # verdicts frozen by the log
            self.assertTrue(M.approval(p.root, "night", s)[0], s)
        p.write("docs/BACKLOG.md", "# Backlog\n")
        self.assertTrue(M.approval(p.root, "night", "night-one")[0])


class Settings(TA.Base):  # criterion 6
    def test_settings_fallback_and_override(self):
        p = self.proj(mission=False)
        s = M.settings(p.root)
        self.assertEqual(s["defaults"], M.DEFAULTS)
        self.assertEqual(s["ceilings"], {"usd": 30.0, "hours": 12.0, "continuations": 60, "features": 8})
        self.assertEqual(s["protected_branches"], ["main", "master", "production"])
        p.write("factory.json", json.dumps({"mission": {"ceilings": {"usd": 5, "hours": "x"}, "protected_branches": ["live"],
                                                         "defaults": {"usd": -1, "features": 2}}}))
        s = M.settings(p.root)
        self.assertEqual((s["ceilings"]["usd"], s["ceilings"]["hours"]), (5.0, 12.0))
        self.assertEqual((s["defaults"]["usd"], s["defaults"]["features"]), (15.0, 2))
        self.assertEqual(s["protected_branches"], ["live"])

    def test_template_factory_json_matches_fallbacks(self):
        s = M.settings(TA.ROOT)
        self.assertEqual(s["defaults"], M.DEFAULTS)
        self.assertEqual(s["ceilings"], M.CEILINGS)

    def test_start_uses_defaults_and_refuses_above_ceiling(self):
        p = self.proj(mission=False)
        base = ["start", "run1", "--go", "go build it", "--title", "T", "--scope-in", "a", "--scope-out", "b", "--milestone", "M7"]
        for flag, val, name in (("--usd", "31", "usd"), ("--hours", "13", "hours"), ("--continuations", "61", "continuations"),
                                ("--features", "9", "features")):
            rc, _o, err = run(p, *base, flag, val)
            self.assertEqual(rc, 1, flag)
            self.assertIn("ceiling", err)
            self.assertIn("mission.ceilings." + name, err)
        self.assertIsNone(M.load(p.root, "run1"))
        p.write("factory.json", json.dumps({"phase": "build", "mission": {"defaults": {"usd": 7}, "ceilings": {"usd": 8}}}))
        p.commit("cfg")
        self.assertEqual(run(p, *base)[0], 0)
        self.assertEqual(M.load(p.root, "run1")["caps"]["usd"], 7.0)

    def test_validate_rejects_committed_caps_above_ceilings(self):
        p = self.proj(caps="usd=99 hours=10 continuations=40")
        self.assertIn("ceiling", M.validate(p.root, M.load(p.root, "night")))
        q = self.proj(features="9")
        self.assertIn("features", M.validate(q.root, M.load(q.root, "night")))
        ok = self.proj()
        self.assertEqual(M.validate(ok.root, M.load(ok.root, "night")), "")


if __name__ == "__main__":
    unittest.main()
