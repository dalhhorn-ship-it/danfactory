"""Acceptance suite tool (scripts/acceptance.py, docs/policies/merge-gate.md): map, admit (two checks), run --json,
baseline ratchet, JUnit runner, dashboard block, gate wiring. Temp project dirs; no network, no model."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import acceptance  # noqa: E402
import gate  # noqa: E402
from obs import tab_gates  # noqa: E402
from test_gate import Repo  # noqa: E402

PRD = "# PRD: Demo\n\n> Status: approved · 2026-11-12\n\n## Acceptance criteria\n1. adds\n2. subtracts\n3. multiplies\n\n## Other\n1. not a criterion\n"
TESTS = '''import unittest


class T(unittest.TestCase):
    def test_c1_add(self):
        from calc import add
        self.assertEqual(add(1, 2), 3)

    def test_c2_sub(self):
        from calc import sub
        self.assertEqual(sub(3, 1), 2)

    def test_c2_trivial(self):
        self.assertTrue(True)
'''


class Proj:
    def __init__(self, tests=TESTS, name="test_calc.py", slug="demo", prd=PRD):
        self.root = tempfile.mkdtemp()
        self.w("factory.json", json.dumps({"acceptance": {"dir": "tests/acceptance", "command": "", "reference_command": ""}}))
        self.w("docs/specs/%s.md" % slug, prd)
        if tests is not None:
            self.w("tests/acceptance/%s/%s" % (slug, name), tests)

    def w(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def cli(self, *a):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = acceptance.main(list(a), root=self.root)
        return rc, out.getvalue(), err.getvalue()

    def manifest(self):
        return acceptance.load_manifest(self.root)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Base(unittest.TestCase):
    def proj(self, *a, **k):
        p = Proj(*a, **k)
        self.addCleanup(p.cleanup)
        return p


class MapAndAdmit(Base):
    def test_map_reports_unmapped(self):
        p = self.proj()
        rc, out, _ = p.cli("map", "demo")
        self.assertEqual(rc, 0)
        self.assertIn("unmapped criterion 3", out)
        self.assertNotIn("unmapped criterion 1", out)
        self.assertEqual(p.cli("map", "demo", "--strict")[0], 1)
        m = p.manifest()["prds"]["demo"]["criteria"]
        self.assertEqual(sorted(m), ["1", "2"])
        self.assertEqual(m["1"], ["demo/test_calc::T.test_c1_add"])
        self.assertEqual(p.cli("map", "nope")[0], 2)

    def test_admit_rejects_passing_test_accepts_body_error(self):
        p = self.proj()
        rc, out, _ = p.cli("admit", "demo")
        self.assertEqual(rc, 1)
        self.assertIn("REJECT demo/test_calc::T.test_c2_trivial [passes-without-behaviour]", out)
        adm = p.manifest()["admitted"]
        self.assertEqual(sorted(adm), ["demo/test_calc::T.test_c1_add", "demo/test_calc::T.test_c2_sub"])  # ImportError in body = fails
        rec = adm["demo/test_calc::T.test_c1_add"]
        self.assertEqual((rec["before"], rec["reference"], rec["criterion"], rec["prd"]), ("fail", None, "1", "demo"))
        self.assertIn("second reading", out)  # warning when no reference

    def test_admit_rejects_import_error_as_broken_test(self):
        p = self.proj(tests="from calc import add\nimport unittest\n\n\nclass T(unittest.TestCase):\n    def test_c1_add(self):\n        self.assertEqual(add(1, 2), 3)\n")
        rc, out, _ = p.cli("admit", "demo")
        self.assertEqual(rc, 1)
        self.assertIn("[broken-test]", out)
        self.assertEqual(p.manifest()["admitted"], {})

    def test_admit_skipped_and_second_reading(self):
        p = self.proj(tests=TESTS.replace("    def test_c2_trivial(self):\n        self.assertTrue(True)\n",
                                          "    @unittest.skip('x')\n    def test_c3_skip(self):\n        pass\n"))
        ref = os.path.join(p.root, "scratch")
        os.makedirs(ref)
        with open(os.path.join(ref, "calc.py"), "w") as fh:
            fh.write("def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a + b\n")  # wrong sub
        rc, out, _ = p.cli("admit", "demo", "--reference-dir", ref)
        self.assertIn("test_c3_skip [skipped]", out)
        self.assertIn("test_c2_sub [fails-on-reference]", out)
        adm = p.manifest()["admitted"]
        self.assertEqual(list(adm), ["demo/test_calc::T.test_c1_add"])
        self.assertEqual(adm["demo/test_calc::T.test_c1_add"]["reference"], "second-reading")
        self.assertNotIn("warning", out)

    def test_subtest_failure_and_collection_vs_body_error_in_run(self):
        p = self.proj(tests="import unittest\n\n\nclass T(unittest.TestCase):\n    def test_c1_sub(self):\n        for i in (1, 2):\n"
                            "            with self.subTest(i=i):\n                self.assertEqual(i, 1)\n\n    def test_c2_err(self):\n        1 / 0\n"
                            "\n    def test_c3_ok(self):\n        pass\n")
        p.w("tests/acceptance/demo/test_broken.py", "import nothing_here_xyz\n")
        res = acceptance.run_unittest(p.root)
        st = {t["id"]: t["status"] for t in res["tests"]}
        self.assertEqual(st, {"demo/test_calc::T.test_c1_sub": "fail", "demo/test_calc::T.test_c2_err": "error", "demo/test_calc::T.test_c3_ok": "pass"})
        self.assertEqual([e["module"] for e in res["collection_errors"]], ["demo/test_broken"])

    def test_run_reports_message_and_where(self):
        p = self.proj(tests="import unittest\n\n\nclass T(unittest.TestCase):\n    def test_c1_boom(self):\n        from calc import boom\n"
                            "        boom()\n\n    def test_c2_assert(self):\n        self.assertEqual(1, 2, 'one is not two\\nsecond line')\n")
        p.w("calc.py", "def helper():\n    raise ValueError('bad value\\nmore')\n\n\ndef boom():\n    helper()\n")
        st = {t["id"]: t for t in json.loads(p.cli("run", "--json")[1])["tests"]}
        t = st["demo/test_calc::T.test_c1_boom"]
        self.assertEqual((t["status"], t["message"], t["where"]), ("error", "bad value", "calc.py:2:helper"))
        a = st["demo/test_calc::T.test_c2_assert"]
        self.assertEqual((a["status"], a["where"]), ("fail", ""))
        self.assertTrue(a["message"].startswith("1 != 2 : one is not two"))
        self.assertLessEqual(len(a["message"]), 200)

    @unittest.skipUnless(os.path.isdir(os.path.join(ROOT, "evals", "spikes", "acceptance-admission")), "fixture lives in the template repo only")
    def test_spike_fixture(self):
        p = Proj(tests=None, slug="truncate", prd=open(os.path.join(ROOT, "evals/spikes/acceptance-admission/prd-truncate.md"), encoding="utf-8").read())
        self.addCleanup(p.cleanup)
        shutil.copytree(os.path.join(ROOT, "evals/base/textkit"), os.path.join(p.root, "textkit"), ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(os.path.join(ROOT, "evals/spikes/acceptance-admission/test_truncate_agent_written.py"),
                    os.path.join(p.root, "tests/acceptance/truncate/") if os.makedirs(os.path.join(p.root, "tests/acceptance/truncate")) is None else "")
        spec = importlib.util.spec_from_file_location("impls", os.path.join(ROOT, "evals/spikes/acceptance-admission/impls.py"))
        impls = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(impls)
        ref = os.path.join(p.root, "scratch")
        os.makedirs(os.path.join(ref, "textkit"))
        with open(os.path.join(ref, "textkit", "__init__.py"), "w") as fh:
            fh.write(impls.IMPL_A)
        rc, out, _ = p.cli("admit", "truncate", "--reference-dir", ref)
        self.assertEqual(rc, 1)
        self.assertIn("test_c5_trailing_comma_removed [fails-on-reference]", out)
        self.assertGreaterEqual(len(p.manifest()["admitted"]), 18)
        self.assertNotIn("demo", json.dumps(p.manifest()["admitted"]))
        self.assertNotIn("truncate/test_truncate_agent_written::TruncateAcceptance.test_c5_trailing_comma_removed", p.manifest()["admitted"])
        self.assertEqual(p.cli("map", "truncate", "--strict")[0], 0)


class RunBaseline(Base):
    def admitted_proj(self):
        p = self.proj()
        p.w("calc.py", "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n")
        # admit against the tree without calc.py, then add the implementation
        os.rename(os.path.join(p.root, "calc.py"), os.path.join(p.root, "calc.py.later"))
        p.cli("admit", "demo")
        os.rename(os.path.join(p.root, "calc.py.later"), os.path.join(p.root, "calc.py"))
        return p

    def test_run_json_matches_gate_contract_and_baseline_grows(self):
        p = self.admitted_proj()
        rc, out, _ = p.cli("run", "--json")
        self.assertEqual(rc, 0)
        rep = json.loads(out)
        self.assertEqual(sorted(rep["admitted"]), ["demo/test_calc::T.test_c1_add", "demo/test_calc::T.test_c2_sub"])
        self.assertIn({"id": "demo/test_calc::T.test_c1_add", "status": "pass"}, rep["tests"])
        self.assertEqual(gate.compare_acceptance(rep, {"passing": rep["admitted"]})[0], ["test-not-admitted"])  # c2_trivial was never admitted
        self.assertEqual(p.cli("baseline")[0], 0)
        base = json.load(open(os.path.join(p.root, acceptance.BASELINE)))
        self.assertEqual(len(base["passing"]), 2)
        self.assertIn("date", base)
        # break one test's code: baseline keeps the id (only grows); --allow-shrink drops it
        p.w("calc.py", "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return 0\n")
        self.assertEqual(p.cli("run")[0], 1)
        p.cli("baseline")
        self.assertEqual(len(json.load(open(os.path.join(p.root, acceptance.BASELINE)))["passing"]), 2)
        p.cli("baseline", "--allow-shrink")
        self.assertEqual(json.load(open(os.path.join(p.root, acceptance.BASELINE)))["passing"], ["demo/test_calc::T.test_c1_add"])

    def test_status_json(self):
        p = self.admitted_proj()
        s = json.loads(p.cli("status", "--json")[1])["demo"]
        self.assertEqual((s["criteria"], s["mapped"], s["admitted_criteria"], s["admitted"], s["passing"]), (3, 2, 2, 2, 2))

    def test_junit_runner(self):
        p = self.proj()
        junit = ('<testsuites><testsuite><testcase classname="tests.acceptance.demo.test_calc.T" name="test_c1_add"/>'
                 '<testcase classname="tests.acceptance.demo.test_calc.T" name="test_c2_sub"><failure message="x"/></testcase>'
                 '<testcase classname="tests.acceptance.demo.test_calc.T" name="test_c2_trivial"><skipped/></testcase>'
                 '<testcase classname="" name="tests.acceptance.demo.test_bad"><error message="ImportError"/></testcase>'
                 '</testsuite></testsuites>')
        p.w("junit.xml", junit)
        p.w("factory.json", json.dumps({"acceptance": {"command": "cp junit.xml \"$ACCEPTANCE_JUNIT\""}}))
        res = acceptance.run_suite(p.root)
        st = {t["id"]: t["status"] for t in res["tests"]}
        self.assertEqual(next(t for t in res["tests"] if t["status"] == "fail")["message"], "x")
        self.assertEqual(st, {"demo/test_calc::T.test_c1_add": "pass", "demo/test_calc::T.test_c2_sub": "fail", "demo/test_calc::T.test_c2_trivial": "skip"})
        self.assertEqual(res["collection_errors"][0]["module"], "demo/test_bad")
        p.w("factory.json", json.dumps({"acceptance": {"command": "true"}}))
        with self.assertRaises(acceptance.RunnerError):
            acceptance.run_suite(p.root)
        self.assertEqual(json.loads(p.cli("run", "--json")[1])["tests"], [])


FIX = os.path.join(os.path.dirname(__file__), "fixtures", "junit")


def junit(name, root=None):
    return acceptance.parse_junit(os.path.join(FIX, name), {"demo"}, root, os.path.join(root, "tests/acceptance") if root else None)


class JunitProducers(Base):
    def rows(self, res):
        return {t["id"]: t for t in res["tests"]}

    def test_pytest(self):
        r = junit("pytest.xml", "/work/repo")
        t = self.rows(r)
        self.assertEqual({k: v["status"] for k, v in t.items()}, {
            "demo/test_calc::TestCalc.test_c1_add": "pass", "demo/test_calc::TestCalc.test_c2_sub": "fail",
            "demo/test_calc::TestCalc.test_c3_mul": "error", "demo/test_calc::test_c4_fn": "skip"})
        f = t["demo/test_calc::TestCalc.test_c2_sub"]
        self.assertEqual((f["message"], f["where"]), ("assert 1 == 2", "src/calc.py:4"))  # acceptance-dir frame skipped
        e = t["demo/test_calc::TestCalc.test_c3_mul"]
        self.assertEqual(e["where"], "src/calc.py:7")  # site-packages frame skipped
        self.assertEqual([c["module"] for c in r["collection_errors"]], ["demo/test_bad"])

    def test_vitest_paths_and_frames(self):
        t = self.rows(junit("vitest.xml", "/work/repo"))
        self.assertEqual({k: v["status"] for k, v in t.items()}, {
            "demo/calc.test::calc > test_c1_add": "pass", "demo/calc.test::calc > test_c2_sub": "fail", "demo/calc.test::calc > test_c3_mul": "skip"})
        f = t["demo/calc.test::calc > test_c2_sub"]
        self.assertEqual((f["message"], f["where"]), ("expected 1 to be 2", "src/calc.ts:12"))

    def test_jest_file_attr_collection_error_and_absolute_where(self):
        r = junit("jest.xml", "/work/repo")
        t = self.rows(r)
        self.assertEqual({k: v["status"] for k, v in t.items()}, {
            "demo/calc.test::calc test_c1_add": "pass", "demo/calc.test::calc test_c2_sub": "fail"})
        self.assertEqual(t["demo/calc.test::calc test_c2_sub"]["where"], "src/calc.js:3")  # node_modules frame skipped
        self.assertEqual([c["module"] for c in r["collection_errors"]], ["demo/broken.test"])

    def test_go_package_classname_and_subtests(self):
        t = self.rows(junit("go.xml", "/work/repo"))
        self.assertEqual({k: v["status"] for k, v in t.items()}, {
            "demo/demo::TestC1Add": "pass", "demo/demo::TestC2Sub": "fail", "demo/demo::TestC3Mul/neg": "skip"})
        f = t["demo/demo::TestC2Sub"]
        self.assertEqual((f["message"], f["where"]), ("Failed", "calc_test.go:12"))

    def test_nested_suites_and_suite_level_error(self):
        r = junit("nested.xml")
        self.assertEqual(r["tests"], [{"id": "demo/test_ok::T.test_c1_x", "status": "pass"}])
        self.assertEqual([c["module"] for c in r["collection_errors"]], ["demo/test_calc"])
        self.assertIn("ImportError", r["collection_errors"][0]["error"])

    def test_admit_rejects_junit_collection_error_as_broken_test(self):
        p = self.proj()
        shutil.copy(os.path.join(FIX, "nested.xml"), os.path.join(p.root, "junit.xml"))
        p.w("factory.json", json.dumps({"acceptance": {"command": "cp junit.xml \"$ACCEPTANCE_JUNIT\""}}))
        rc, out, _ = p.cli("admit", "demo")
        self.assertEqual(rc, 1)
        self.assertIn("[broken-test]", out)
        self.assertIn("ImportError", out)

    def test_error_beats_failure_and_unreadable_xml(self):
        p = self.proj()
        p.w("a.xml", '<testsuite><testcase classname="demo.test_x.T" name="test_c1"><failure message="f"/><error message="e"/></testcase></testsuite>')
        r = acceptance.parse_junit(os.path.join(p.root, "a.xml"), {"demo"})
        self.assertEqual(r["tests"], [{"id": "demo/test_x::T.test_c1", "status": "error", "message": "e", "where": ""}])
        p.w("b.xml", "<testsuite")
        with self.assertRaises(acceptance.RunnerError):
            acceptance.parse_junit(os.path.join(p.root, "b.xml"), {"demo"})


MAN = {"prds": {"demo": {"prd": "docs/specs/demo.md", "criteria": {"1": ["demo/t::T.test_c1_a"]}}},
       "admitted": {"demo/t::T.test_c1_a": {"prd": "demo", "criterion": "1", "reference": "second-reading"},
                    "demo/t::T.test_c2_b": {"prd": "demo", "criterion": "2", "reference": None}},
       "questions": {"demo": ["Is <b>x</b> allowed?"]}}


class Dashboard(Base):
    def test_empty_state(self):
        p = self.proj()
        self.assertIsNone(tab_gates.acceptance_stats(p.root, []))
        h = tab_gates.render_acceptance(None).replace("&#x27;", "'")
        self.assertIn("No acceptance suite yet: at L2+, the test-writer adds one after a PRD is approved (docs/policies/merge-gate.md).", h)
        self.assertEqual(tab_gates.acceptance_line(None), "no suite yet")

    def test_rendering(self):
        p = self.proj()
        p.w("tests/acceptance/manifest.json", json.dumps(MAN))
        p.w("docs/specs/demo.md", PRD)
        p.w("metrics/acceptance-baseline.json", json.dumps({"passing": ["demo/t::T.test_c1_a"]}))
        a = tab_gates.acceptance_stats(p.root, [])
        d = a["prds"][0]
        self.assertEqual((d["criteria"], d["covered"], d["admitted"], d["passing"], d["second_reading"]), (3, 2, 2, 1, 1))
        self.assertEqual((a["coverage_pct"], a["source"]), (67, "baseline"))
        row = {"verdict": "pass", "checks": [{"id": "acceptance", "status": "pass", "passing": ["demo/t::T.test_c1_a", "demo/t::T.test_c2_b"]}]}
        a2 = tab_gates.acceptance_stats(p.root, [row])
        self.assertEqual((a2["prds"][0]["passing"], a2["source"]), (2, "latest gate run"))
        h = tab_gates.render_acceptance(a)
        self.assertIn("Acceptance coverage", h)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", h)
        self.assertNotIn("<b>x</b>", h)
        self.assertIn("67%", tab_gates.acceptance_line(a))
        self.assertIn("Acceptance coverage", tab_gates.render({"gate": None, "acceptance": a, "items_total": 0, "components_total": 0}))


class GateWiring(unittest.TestCase):
    def repo(self):
        r = Repo()
        self.addCleanup(r.cleanup)
        return r

    def install(self, r, man):
        for part in ("acceptance.py", "acceptance_exec.py"):
            r.write("scripts/" + part, open(os.path.join(ROOT, "scripts", part), encoding="utf-8").read())
        r.write("tests/acceptance/manifest.json", json.dumps(man))

    def test_warns_open_questions_and_unmapped(self):
        r = self.repo()
        self.install(r, {"prds": {"demo": {"criteria": {}}}, "admitted": {}, "questions": {"demo": ["q1"]}})
        c = r.check("acceptance")
        self.assertEqual(c["status"], "warn")
        self.assertEqual(c["codes"], ["open-prd-questions", "acceptance-unmapped"])
        self.assertIn("passing", c)

    def test_clean_suite_passes(self):
        r = self.repo()
        self.install(r, {"prds": {"demo": {"criteria": {"1": ["demo/t::T.test_c1_a"]}}}, "admitted": {}, "questions": {}})
        self.assertEqual(r.check("acceptance")["status"], "pass")

    def test_missing_script_with_baseline_fails(self):
        r = self.repo()
        r.write("metrics/acceptance-baseline.json", json.dumps({"passing": ["demo/t::T.a"]}))
        c = r.check("acceptance")
        self.assertEqual((c["status"], c["codes"]), ("fail", ["acceptance-error"]))
        r.write("metrics/acceptance-baseline.json", json.dumps({"passing": []}))
        self.assertEqual(r.check("acceptance")["status"], "skip")


if __name__ == "__main__":
    unittest.main()
