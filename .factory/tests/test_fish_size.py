"""FISH-6 (docs/specs/teach-agents-to-fish.md criteria 5-9): `gate.size`, the runner's `fail`, size issues in the ledger
(ADR 0013). Temp git projects only; temp dirs removed in tearDown."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gate  # noqa: E402
import issues  # noqa: E402
import runner_attempt  # noqa: E402
from obs import tab_autonomy  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


def body(n):
    return "".join("x = %d\n" % i for i in range(n))


class Repo(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fish-size-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.git("init", "-q")

    def git(self, *a):
        return subprocess.run(["git", "-C", self.root, "-c", "commit.gpgsign=false", *a], check=True, capture_output=True, text=True, env=ENV).stdout.strip()

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "c")
        return self.git("rev-parse", "HEAD")

    def cli(self, cmd):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = issues.main(["--root", self.root, cmd, "--from-json", self.results()])
        self.assertEqual(rc, 0)
        return out.getvalue()

    def results(self):
        d = tempfile.mkdtemp(prefix="fish-size-res-")
        self.addCleanup(shutil.rmtree, d, True)
        f = os.path.join(d, "results.json")
        with open(f, "w") as fh:
            json.dump({"tests": [], "admitted": []}, fh)
        return f


class GateSize(Repo):
    def grow(self, setting):
        cfg = {"commands": {}}
        if setting is not None:
            cfg["gate"] = {"size": setting}
        self.write("factory.json", json.dumps(cfg))
        self.write("src/big.py", body(710))
        base = self.commit()
        self.write("src/big.py", body(720))
        self.commit()
        factory, g = gate.config(self.root)
        return gate.c_size({"root": self.root, "factory": factory, "gate": g, "base": base, "template": False})

    def test_c5_fail_setting_fails_with_file_over_size(self):
        st, codes, detail = self.grow("fail")
        self.assertEqual((st, codes), ("fail", ["file-over-size"]))
        self.assertIn("src/big.py", detail)

    def test_c5_whole_gate_verdict_fails(self):
        self.grow("fail")
        base = self.git("rev-parse", "HEAD~1")
        v = gate.run_gate(self.root, base, only={"size"})
        self.assertEqual(v["verdict"], "fail")
        self.assertIn("file-over-size", v["codes"])

    def test_c5_fail_setting_passes_when_nothing_grew_over(self):
        self.write("factory.json", json.dumps({"commands": {}, "gate": {"size": "fail"}}))
        self.write("src/ok.py", body(10))
        base = self.commit()
        self.write("src/ok.py", body(20))
        self.commit()
        factory, g = gate.config(self.root)
        self.assertEqual(gate.c_size({"root": self.root, "factory": factory, "gate": g, "base": base})[0], "pass")

    def test_c6_default_warns_and_never_fails(self):
        self.assertEqual(gate.DEFAULTS["size"], "warn")
        st, codes, _ = self.grow(None)
        self.assertEqual((st, codes), ("warn", ["file-over-size"]))
        self.assertEqual(self.grow("warn")[0], "warn")

    def test_c6_invalid_value_is_warn_with_a_note(self):
        st, codes, detail = self.grow("strict")
        self.assertEqual((st, codes), ("warn", ["file-over-size"]))
        self.assertIn("treated as warn", detail)

    def test_size_growth_stays_a_warning_with_fail(self):
        self.write("factory.json", json.dumps({"commands": {}, "gate": {"size": "fail"}}))
        factory, g = gate.config(self.root)
        with mock.patch("gate_checks._c_size", return_value=("warn", ["size-growth"], "grew")):
            self.assertEqual(gate.c_size({"root": self.root, "factory": factory, "gate": g, "base": "x"})[0], "warn")


class RunnerGate(Repo):
    def test_c7_runner_gate_runs_use_fail_whatever_factory_json_says(self):
        self.write("factory.json", json.dumps({"commands": {}, "gate": {"size": "warn"}}))
        self.commit()
        seen = {}

        def fake(path, base):
            seen.update(gate.config(path)[1])
            return {"verdict": "pass"}
        ts = mock.MagicMock()  # no bwrap needed: the sandbox is not what is under test
        with mock.patch.object(gate, "run_gate", fake), mock.patch.object(runner_attempt.S, "TreeSandbox", return_value=ts):
            runner_attempt.gate_verdict(self.root, "HEAD")
        self.assertEqual((seen["size"], seen["review"]), ("fail", "required"))
        self.assertEqual(gate.config(self.root)[1]["size"], "warn")  # the patch is undone


class SizeIssues(Repo):
    def setUp(self):
        super().setUp()
        self.write("src/big.py", body(710))
        self.write("src/fine.py", body(30))
        self.write("src/mid.py", body(500))
        self.commit()

    def files(self, state):
        d = os.path.join(self.root, "issues", state)
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def test_c8_one_issue_per_over_file_and_no_duplicate_on_rerun(self):
        self.assertIn("created ISS-0001", self.cli("find"))
        self.write("src/big2.py", body(701))
        self.commit()
        self.cli("find")
        self.cli("find")
        names = self.files("open")
        self.assertEqual(len(names), 2)
        iss = {i["meta"]["file"]: i for i in issues.load(self.root)}
        self.assertEqual(set(iss), {"src/big.py", "src/big2.py"})
        self.assertEqual(iss["src/big.py"]["meta"]["source"], "size")
        self.assertEqual(iss["src/big.py"]["tests"], {})
        self.assertIn("src/big.py", iss["src/big.py"]["title"])

    def test_c8_a_parked_size_issue_still_owns_its_file(self):
        self.cli("find")
        issues.cmd_block(self.root, "ISS-0001")
        self.cli("find")
        self.assertEqual((len(self.files("open")), len(self.files("blocked"))), (0, 1))

    def test_c9_closes_when_file_is_at_or_under_max_and_reopens_on_regrowth(self):
        self.cli("find")
        self.cli("sync")
        self.assertEqual((len(self.files("open")), len(self.files("fixed"))), (1, 0))  # still over: stays open
        self.write("src/big.py", body(700))  # exactly the max counts as fixed
        self.commit()
        self.assertIn("fixed ISS-0001", self.cli("sync"))
        self.assertEqual(len(self.files("fixed")), 1)
        self.write("src/big.py", body(705))
        self.commit()
        self.assertIn("reopened ISS-0001", self.cli("sync"))
        self.assertEqual(len(self.files("open")), 1)
        self.write("src/big.py", body(705))
        self.cli("find")  # find alone also never duplicates
        self.assertEqual(len(self.files("open")) + len(self.files("fixed")), 1)

    def test_c9_a_removed_file_closes_its_issue(self):
        self.cli("find")
        self.git("rm", "-q", "src/big.py")
        self.commit()
        self.assertIn("fixed ISS-0001", self.cli("sync"))

    def test_header_roundtrip_and_old_files_read_as_test(self):
        self.cli("find")
        with open(os.path.join(self.root, "issues", "open", self.files("open")[0])) as fh:
            text = fh.read()
        self.assertIn("· Source: size · File: src/big.py", text)
        self.assertEqual(issues.parse(text)["meta"]["file"], "src/big.py")
        old = text.split(" · Source:")[0]
        m = issues.parse(old)["meta"]
        self.assertEqual((m["source"], m["file"], m["fixed"]), ("test", "", "-"))

    def test_size_issue_is_not_picked_by_the_runner_and_cannot_be_merged(self):
        import runner_pick
        self.cli("find")
        self.write("src/big2.py", body(701))
        self.commit()
        self.cli("find")
        with mock.patch.object(gate, "approved_slugs", return_value={"-", "any"}):
            self.assertIsNone(runner_pick.pick_issue(self.root, None, None))
            self.assertEqual(runner_pick.pick_batch(self.root, 3), [])
        with self.assertRaises(issues.Usage):
            issues.cmd_merge(self.root, "ISS-0001", "ISS-0002")

    def test_status_counts_and_dashboard_do_not_break(self):
        self.cli("find")
        st = issues.status(self.root)
        self.assertEqual((st["open"], st["issues"][0]["tests"]), (1, 0))
        self.assertIsInstance(tab_autonomy.collect(self.root, None), dict)


if __name__ == "__main__":
    unittest.main()
