"""SIZE-1: size measures, budgets, flags, the Hotspots Size block, the --print row and the gate `size` check.

Every git call names a temporary repo with `-C`; temp dirs are removed in tearDown (TD-021)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import dashboard  # noqa: E402
import gate  # noqa: E402
from obs import size, tab_hotspots  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="tester", GIT_AUTHOR_EMAIL="x@example.com",
           GIT_COMMITTER_NAME="tester", GIT_COMMITTER_EMAIL="x@example.com")
DAY = 86400


def body(n):
    return "".join("x = %d\n" % i for i in range(n))


class TempRepo(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="size-test-")
        self.addCleanup(shutil.rmtree, self.root, True)

    def git(self, *args, when=None):
        env = dict(ENV)
        if when:
            env.update(GIT_AUTHOR_DATE="%d +0000" % when, GIT_COMMITTER_DATE="%d +0000" % when)
        subprocess.run(["git", "-C", self.root, *args], cwd=self.root, check=True, capture_output=True, env=env)

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, msg="c", when=None):
        self.git("add", "-A")
        self.git("-c", "commit.gpgsign=false", "commit", "-q", "-m", msg, when=when)

    def init(self):
        self.git("init", "-q")


class TestMeasures(TempRepo):
    def test_areas_and_counts(self):
        self.init()
        self.write("src/a.py", body(10))
        self.write(".factory/tests/test_a.py", body(4))
        self.write("docs/x.md", "a\nb\n")
        self.write(".claude/hooks/h.py", body(3))
        self.write(".claude/agents/a.md", "a\n")
        self.write("evals/e.py", body(2))
        self.write("CLAUDE.md", "x" * 400)
        self.commit()
        d = size.collect(self.root, {})
        self.assertEqual(d["areas"]["code"], {"files": 2, "lines": 13})
        self.assertEqual(d["areas"]["tests"]["lines"], 4)
        self.assertEqual(d["areas"]["docs"]["lines"], 3)  # x.md plus CLAUDE.md
        self.assertEqual(d["areas"]["evals"]["lines"], 2)
        self.assertEqual(d["counts"]["agents"], 1)
        self.assertEqual(d["always_loaded"]["claude_md"], 100)
        self.assertEqual(d["test_ratio"], round(4 / 13, 2))

    def test_growth_reads_history_at_the_dates(self):
        self.init()
        now = 1_800_000_000
        self.write("src/a.py", body(100))
        self.commit(when=now - 40 * DAY)
        self.write("src/a.py", body(200))
        self.commit(when=now - 10 * DAY)
        self.write("src/a.py", body(400))
        self.commit(when=now - 1 * DAY)
        cur = size._count(size.current_files(self.root))
        g = size.growth(self.root, cur, now=now)
        self.assertEqual(g["7"]["areas"]["code"]["then"], 200)
        self.assertEqual(g["30"]["areas"]["code"]["then"], 100)
        self.assertEqual(g["30"]["areas"]["code"]["pct"], 300.0)

    def test_no_history_says_so_and_does_not_fail(self):  # criterion 4
        self.write("src/a.py", body(10))  # no git at all
        d = size.collect(self.root, {})
        self.assertEqual(d["growth"], {"7": None, "30": None})
        self.assertIn(size.NO_HISTORY, tab_hotspots.render_size(d))
        self.assertIn(size.NO_HISTORY, size.line(d))
        self.init()
        self.write("README.md", "x\n")
        self.commit()  # one fresh commit: still no history
        self.assertEqual(size.collect(self.root, {})["growth"], {"7": None, "30": None})

    def test_empty_repo_renders(self):
        d = size.collect(self.root, {})
        self.assertEqual(d["flags"], [])
        self.assertIn("No product file is over", tab_hotspots.render_size(d))


class TestFlags(TempRepo):
    def test_file_flags_and_escaping(self):
        self.init()
        self.write("src/<big>.py", body(750))
        self.write("src/mid.py", body(450))
        self.write("src/small.py", body(5))
        self.commit()
        d = size.collect(self.root, {})
        kinds = {f["subject"]: f["kind"] for f in d["flags"]}
        self.assertEqual(kinds, {"src/<big>.py": "file-over-size", "src/mid.py": "file-large"})
        self.assertTrue(all(f["action"] for f in d["flags"]))
        html = tab_hotspots.render_size(d)
        self.assertIn("src/&lt;big&gt;.py", html)
        self.assertNotIn("<big>", html)

    def test_budgets_from_factory_json_move_the_flags(self):  # criterion 3
        self.init()
        self.write("src/a.py", body(300))
        self.commit()
        self.assertEqual(size.collect(self.root, {})["flags"], [])
        f = {"budgets": {"size": {"file_lines_warn": 100, "file_lines_max": 250}}}
        self.assertEqual([x["kind"] for x in size.collect(self.root, f)["flags"]], ["file-over-size"])
        self.write("factory.json", json.dumps(f))
        self.assertEqual([x["kind"] for x in size.collect(self.root)["flags"]], ["file-over-size"])
        self.assertEqual(size.budgets({"budgets": {"size": {"agents_max": "x", "bogus": 1}}}), size.DEFAULTS)

    def test_always_loaded_agents_and_growth_flags(self):
        self.init()
        now = 1_800_000_000
        self.write("CLAUDE.md", "x" * 400)
        self.write("src/a.py", body(100))
        self.write(".claude/agents/a.md", "a\n")
        self.write(".claude/agents/b.md", "a\n")
        self.commit(when=now - 40 * DAY)
        self.write("src/a.py", body(400))
        self.commit(when=now - DAY)
        f = {"budgets": {"size": {"always_loaded_tokens_max": 50, "agents_max": 1, "code_growth_30d_pct_warn": 10}}}
        d = size.collect(self.root, f)
        d["growth"] = size.growth(self.root, d["areas"], now=now)
        got = {x["kind"] for x in size.flags(d, d["budgets"])}
        self.assertEqual(got, {"always-loaded", "agents", "size-growth"})


class TestGate(TempRepo):
    def run_size(self, base):
        factory, gt = gate.config(self.root)
        ctx = {"root": self.root, "factory": factory, "gate": gt, "base": base, "template": False}
        return gate.c_size(ctx)

    def head(self):
        return subprocess.run(["git", "-C", self.root, "rev-parse", "HEAD"], cwd=self.root, capture_output=True, text=True,
                              check=True).stdout.strip()

    def test_warns_when_a_big_file_grows_and_never_fails(self):  # criterion 2
        self.init()
        self.write("src/big.py", body(800))
        self.write("src/other.py", body(10))
        self.commit()
        base = self.head()
        self.write("src/big.py", body(810))
        self.write("src/other.py", body(11))
        self.commit()
        st, codes, detail = self.run_size(base)
        self.assertEqual(st, "warn")
        self.assertIn("file-over-size", codes)
        self.assertIn("src/big.py", detail)
        self.assertNotIn("other.py", detail)
        self.write("src/big.py", body(20))  # shrinking is fine
        self.commit()
        self.assertEqual(self.run_size(base)[0], "pass")

    def test_pushing_a_file_over_the_max_warns(self):
        self.init()
        self.write("src/a.py", body(690))
        self.commit()
        base = self.head()
        self.write("src/a.py", body(720))
        st, codes, _ = self.run_size(base)
        self.assertEqual((st, codes), ("warn", ["file-over-size"]))

    def test_no_base_skips_and_verdict_passes(self):
        self.init()
        self.write("src/a.py", body(800))
        self.commit()
        self.assertEqual(self.run_size(None)[0], "skip")
        self.write("src/b.py", body(800))
        self.commit()
        v = gate.run_gate(self.root, only={"size"})
        self.assertEqual(v["verdict"], "pass")


def in_template_checkout():
    """The repo tests need the template's own git checkout (copies made by other tests have neither)."""
    return os.path.exists(os.path.join(ROOT, ".git")) and os.path.isfile(os.path.join(ROOT, "scripts", "runner.py")) and "scripts/runner.py" in {
        p for p, _ in size.current_files(ROOT)}


@unittest.skipUnless(in_template_checkout(), "needs the template git checkout")
class TestOnThisRepo(unittest.TestCase):
    def test_criterion_1_flags_the_known_big_files(self):
        d = size.collect(ROOT)
        flagged = {f["subject"]: f for f in d["flags"] if f["kind"].startswith("file")}
        self.assertEqual(flagged["scripts/runner.py"]["kind"], "file-over-size")
        self.assertIn("scripts/runner.py", tab_hotspots.render_size(d))
        for p in ("scripts/acceptance.py", "scripts/gate.py", "scripts/dashboard.py", ".claude/hooks/guard_bash_policy.py"):
            self.assertIn(p, flagged)
        if d["growth"]["30"]:
            self.assertTrue(any(f["kind"] == "size-growth" for f in d["flags"]))

    def test_criterion_5_print_has_a_size_row_and_alerts(self):
        d = dashboard.collect()
        self.assertIn("| Size |", dashboard.summary(d))
        self.assertEqual([a for a in d["metrics"]["alerts"] if a.startswith("Size:")], d["hotspots"]["size"]["alerts"])
        self.assertTrue(d["hotspots"]["size"]["alerts"])

    def test_factory_json_ships_the_defaults(self):
        with open(os.path.join(ROOT, "factory.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["budgets"]["size"], size.DEFAULTS)


if __name__ == "__main__":
    unittest.main()
