"""Merge gate (scripts/gate.py, docs/policies/merge-gate.md): verdict shape, every reason code from a temp git repo,
acceptance comparison on fake JSON, dashboard block, CI wiring. No network, no model."""
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
from obs import tab_gates  # noqa: E402

PRD = "# PRD: Demo\n\n> Status: %s · Approved: 2026-11-12 · Backlog: X-1\n\n## Acceptance criteria\n1. a thing\n"
KEY = "-----BEGIN " + "RSA PRIVATE KEY-----"  # built in parts so this file never holds a literal secret
GH = "gh" + "p_" + "a" * 36
AWS = "AK" + "IA" + "A" * 16


class Repo:
    """A throwaway git repo with one base commit; `sha` of that commit is `self.base`."""

    def __init__(self, factory=None):
        self.root = tempfile.mkdtemp()
        self.g("init", "-q")
        self.write("factory.json", json.dumps(factory or {"commands": {}, "budgets": {"test_seconds": 120}}))
        self.write("docs/specs/demo.md", PRD % "approved")
        self.write("docs/specs/draft.md", PRD % "draft")
        self.commit("base")
        self.base = self.g("rev-parse", "HEAD").strip()

    def g(self, *a):
        p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"] + list(a),
                           cwd=self.root, capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        return p.stdout

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, msg, trailer=""):
        self.g("add", "-A")
        self.g("commit", "-q", "--allow-empty", "-m", msg + ("\n\n" + trailer if trailer else ""))

    def run(self, only=None, **kw):
        return gate.run_gate(self.root, kw.get("base", self.base), set(only.split(",")) if only else None)

    def check(self, cid):
        return {c["id"]: c for c in self.run(cid)["checks"]}[cid]

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Base(unittest.TestCase):
    def repo(self, factory=None):
        r = Repo(factory)
        self.addCleanup(r.cleanup)
        return r


class Verdict(Base):
    def test_shape_and_exit_codes(self):
        r = self.repo()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = gate.main(["--json", "--no-record", "--base", r.base], root=r.root)
        v = json.loads(out.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(v), ["base", "checks", "codes", "seconds", "sha", "ts", "verdict"])
        self.assertEqual([c["id"] for c in v["checks"]], [c for c, _ in gate.CHECKS])
        for c in v["checks"]:
            self.assertEqual(sorted(c), ["codes", "detail", "id", "seconds", "status"])
            self.assertIn(c["status"], ("pass", "fail", "warn", "skip"))
        self.assertFalse(os.path.exists(os.path.join(r.root, gate.LOCAL)))  # --no-record

    def test_fail_exit_1_and_usage_exit_2_and_record(self):
        r = self.repo({"commands": {"build": "false"}})
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(gate.main(["--base", r.base], root=r.root), 1)
            self.assertEqual(gate.main(["--only", "nope"], root=r.root), 2)
            self.assertEqual(gate.main(["--bogus"], root=r.root), 2)
        rows = [json.loads(l) for l in open(os.path.join(r.root, gate.LOCAL))]
        self.assertEqual(len(rows), 1)  # the usage errors recorded nothing
        self.assertEqual(rows[0]["verdict"], "fail")
        self.assertIn("build-failed", rows[0]["codes"])

    def test_cli_runs_as_script_and_writes_summary(self):
        r = self.repo()
        os.makedirs(os.path.join(r.root, "scripts"))
        for part in ("gate.py", "gate_checks.py"):
            shutil.copy(os.path.join(ROOT, "scripts", part), os.path.join(r.root, "scripts", part))
        summ = os.path.join(r.root, "summary.md")
        p = subprocess.run([sys.executable, "scripts/gate.py", "--base", "", "--summary", summ, "--no-record"], cwd=r.root,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)  # empty base falls back instead of failing
        md = open(summ).read()
        self.assertIn("**Merge gate: PASS**", md)
        self.assertIn("| check | status | codes | seconds |", md)
        self.assertIn("| security |", md)

    def test_base_fallbacks(self):
        r = self.repo()
        r.commit("two")
        for given in (None, "", "0" * 40, "does-not-exist"):
            v = r.run(base=given)
            self.assertEqual(v["base"], r.base[:7])  # HEAD~1
        self.assertEqual(r.run(only="security", base="HEAD")["base"], r.g("rev-parse", "HEAD").strip()[:7])

    def test_base_note(self):
        r = self.repo()
        r.write("a.txt", "x\n")
        r.commit("a", "PRD-Exempt: fixture")
        v = r.run(base="nope")
        self.assertIn("--base nope does not resolve", v["base_note"])
        self.assertEqual(v["base"], r.base[:7])  # fell back to HEAD~1
        self.assertNotIn("base_note", r.run())  # explicit, resolvable base: no note
        out = io.StringIO()
        summ = os.path.join(r.root, "s.md")
        with contextlib.redirect_stdout(out):
            gate.main(["--base", "nope", "--no-record", "--summary", summ], root=r.root)
        self.assertIn("base-fallback: --base nope", out.getvalue())
        with open(summ, encoding="utf-8") as fh:
            self.assertIn("base-fallback: --base nope", fh.read())
        self.assertIn("all zeros", r.run(base="0" * 40)["base_note"])
        self.assertEqual(r.run(base="nope")["verdict"], "pass")  # a note is not a failure

    def test_no_base_skips_diff_checks(self):
        r = self.repo()  # a single commit: no HEAD~1
        v = gate.run_gate(r.root, None, {"protected", "review", "security"})
        self.assertEqual([c["status"] for c in v["checks"]], ["skip"] * 3)

    def test_crashing_check_fails(self):
        r = self.repo()
        with mock.patch.object(gate, "CHECKS", (("build", lambda ctx: 1 / 0),)):
            v = gate.run_gate(r.root, r.base)
        self.assertEqual(v["verdict"], "fail")
        self.assertIn("build-failed", v["codes"])

    def test_only_rows_are_marked(self):
        r = self.repo()
        self.assertEqual(r.run("build")["only"], ["build"])


class Commands(Base):
    def test_build_lint_failures_and_skips(self):
        r = self.repo({"commands": {"build": "false", "lint": "false"}})
        self.assertEqual((r.check("build")["status"], r.check("build")["codes"]), ("fail", ["build-failed"]))
        self.assertEqual(r.check("lint")["codes"], ["lint-failed"])
        ok = self.repo({"commands": {"build": "true", "lint": "true"}})
        self.assertEqual(ok.check("build")["status"], "pass")
        self.assertEqual(self.repo().check("build")["status"], "skip")

    def test_structure(self):
        r = self.repo()
        self.assertEqual(r.check("structure")["status"], "skip")
        r.write("scripts/check.sh", "exit 3\n")
        c = r.check("structure")
        self.assertEqual((c["status"], c["codes"]), ("fail", ["structure-failed"]))
        r.write("scripts/check.sh", "exit 0\n")
        self.assertEqual(r.check("structure")["status"], "pass")

    def _with_metrics(self, r):
        os.makedirs(os.path.join(r.root, "scripts"), exist_ok=True)
        shutil.copy(os.path.join(ROOT, "scripts", "metrics.py"), os.path.join(r.root, "scripts", "metrics.py"))
        os.makedirs(os.path.join(r.root, ".claude", "hooks"), exist_ok=True)
        shutil.copy(os.path.join(ROOT, ".claude", "hooks", "_common.py"), os.path.join(r.root, ".claude", "hooks", "_common.py"))

    def test_tests_failed_and_over_budget(self):
        r = self.repo({"commands": {"test": "false"}, "budgets": {"test_seconds": 120}})
        self._with_metrics(r)
        c = r.check("tests")
        self.assertEqual((c["status"], c["codes"]), ("fail", ["tests-failed"]))
        slow = self.repo({"commands": {"test": "true"}, "budgets": {"test_seconds": 0.001}})
        self._with_metrics(slow)
        c = slow.check("tests")
        self.assertEqual((c["status"], c["codes"]), ("warn", ["tests-over-budget"]))
        self.assertEqual(slow.run("tests")["verdict"], "pass")  # warn never fails

    def test_tests_include_acceptance_warns(self):  # TD-017: the acceptance check runs those; open issues fail by design
        for cmd, want in (("pytest tests/acceptance && true", True), ("python3 -m unittest discover -s tests/unit", False), ("pytest tests/unit", False),
                          ("pytest --ignore=tests/acceptance", False)):
            self.assertEqual(gate.includes_acceptance(cmd), want, cmd)
        r = self.repo({"commands": {"test": "true tests/acceptance"}, "budgets": {"test_seconds": 120}})
        self._with_metrics(r)
        c = r.check("tests")
        self.assertEqual((c["status"], c["codes"]), ("warn", ["tests-include-acceptance"]))

    def test_tests_skipped_in_template_mode_or_without_command(self):
        r = self.repo({"commands": {"test": "false"}})
        with mock.patch.object(gate, "is_template", return_value=True):
            c = r.check("tests")
        self.assertEqual((c["status"], c["detail"]), ("skip", "covered by structure (check.sh)"))
        self.assertEqual(self.repo().check("tests")["status"], "skip")

    def test_coverage(self):
        f = {"commands": {}, "budgets": {"min_coverage_pct": 80, "max_coverage_drop_pct": 2}}
        r = self.repo(f)
        self.assertEqual(r.check("coverage")["status"], "skip")

        def hist(*vals):
            r.write("metrics/history.jsonl", "\n".join(
                json.dumps({"kind": "test", "scope": "full", "coverage_pct": v}) for v in vals) + "\nnot json\n")
        hist(90, 85)
        self.assertEqual(r.check("coverage")["codes"], ["coverage-dropped"])
        hist(90, 89)
        self.assertEqual(r.check("coverage")["status"], "pass")
        hist(75)
        self.assertEqual(r.check("coverage")["codes"], ["coverage-below-min"])
        hist(95, 70)
        self.assertEqual(sorted(r.check("coverage")["codes"]), ["coverage-below-min", "coverage-dropped"])


class Acceptance(Base):
    FAKE = {"tests": [{"id": "s/m::A.ok", "status": "pass"}, {"id": "s/m::A.bad", "status": "fail"},
                      {"id": "s/m::A.new", "status": "pass"}, {"id": "s/m::A.raw", "status": "pass"}],
            "admitted": ["s/m::A.ok", "s/m::A.bad", "s/m::A.new"]}

    def test_compare_pure(self):
        codes, detail = gate.compare_acceptance(self.FAKE, {"passing": ["s/m::A.ok", "s/m::A.bad"]})
        self.assertEqual(codes, ["acceptance-regression", "test-not-admitted"])
        self.assertIn("s/m::A.bad", detail)
        self.assertIn("s/m::A.raw", detail)
        self.assertIn("newly passing", detail)
        self.assertEqual(gate.compare_acceptance(self.FAKE, {"passing": ["s/m::A.ok"]})[0], ["test-not-admitted"])
        clean = {"tests": [{"id": "x", "status": "pass"}], "admitted": ["x"]}
        self.assertEqual(gate.compare_acceptance(clean, {"passing": ["x"]})[0], [])
        self.assertEqual(gate.compare_acceptance(clean, {})[0], [])  # newly passing is informational
        gone = gate.compare_acceptance({"tests": [], "admitted": []}, {"passing": ["x"]})[0]
        self.assertEqual(gone, ["acceptance-regression"])  # a baseline test that vanished is a regression
        for st in ("error", "skip"):
            self.assertEqual(gate.compare_acceptance({"tests": [{"id": "x", "status": st}], "admitted": ["x"]},
                                                     {"passing": ["x"]})[0], ["acceptance-regression"])
        self.assertEqual(gate.compare_acceptance(None, None)[0], [])

    def _suite(self, r, payload):
        r.write("scripts/acceptance.py", "import sys\nsys.stdout.write(%r)\n" % payload)
        r.write("tests/acceptance/manifest.json", json.dumps({"prds": {}, "admitted": {}}))
        r.write(gate.BASELINE, json.dumps({"passing": ["s/m::A.ok", "s/m::A.bad"]}))

    def test_check_runs_suite_when_present(self):
        r = self.repo()
        c = r.check("acceptance")
        self.assertEqual((c["status"], c["detail"]), ("skip", "no acceptance suite"))
        self._suite(r, json.dumps(self.FAKE))
        self.assertEqual(r.check("acceptance")["codes"], ["acceptance-regression", "test-not-admitted"])
        self._suite(r, json.dumps({"tests": [{"id": "s/m::A.ok", "status": "pass"}], "admitted": ["s/m::A.ok"]}))
        r.write(gate.BASELINE, json.dumps({"passing": ["s/m::A.ok"]}))
        self.assertEqual(r.check("acceptance")["status"], "pass")
        self._suite(r, "garbage")
        self.assertEqual(r.check("acceptance")["codes"], ["acceptance-error"])


class Protected(Base):
    def _acc(self, r, trailer, name="t.py"):
        r.write("tests/acceptance/demo/" + name, "x = 1\n")
        r.commit("add acceptance test", trailer)

    def test_without_trailer_fails_and_with_valid_trailer_passes(self):
        r = self.repo()
        self._acc(r, "")
        c = r.check("protected")
        self.assertEqual((c["status"], c["codes"]), ("fail", ["protected-path"]))
        ok = self.repo()
        self._acc(ok, "Acceptance-Change: demo")
        self.assertEqual(ok.check("protected")["status"], "pass")

    def test_trailer_must_name_an_approved_prd(self):
        for slug in ("draft", "missing"):
            r = self.repo()
            self._acc(r, "Acceptance-Change: " + slug)
            self.assertEqual(r.check("protected")["codes"], ["protected-path"], slug)

    def test_trailer_must_be_in_manifest_once_it_exists(self):
        r = self.repo()
        r.write("tests/acceptance/manifest.json", json.dumps({"prds": {"other": {}}}))
        r.commit("manifest", "Acceptance-Change: other")  # 'other' is not an approved PRD
        self.assertEqual(r.check("protected")["codes"], ["protected-path"])
        r2 = self.repo()
        r2.write("tests/acceptance/manifest.json", json.dumps({"prds": {"demo": {}}}))
        r2.commit("manifest", "Acceptance-Change: demo")
        self.assertEqual(r2.check("protected")["status"], "pass")
        r2.write("tests/acceptance/manifest.json", json.dumps({"prds": {}}))
        r2.commit("edit", "Acceptance-Change: demo")  # approved but not in the manifest
        self.assertEqual(r2.check("protected")["codes"], ["protected-path"])

    def test_every_commit_needs_the_trailer_and_worktree_edits_fail(self):
        r = self.repo()
        self._acc(r, "Acceptance-Change: demo")
        self._acc(r, "", "u.py")
        self.assertEqual(r.check("protected")["codes"], ["protected-path"])
        r2 = self.repo()
        self._acc(r2, "Acceptance-Change: demo")
        r2.write("tests/acceptance/demo/t.py", "x = 2\n")  # uncommitted edit
        self.assertEqual(r2.check("protected")["codes"], ["protected-path"])
        r3 = self.repo()
        r3.write("tests/acceptance/new.py", "x\n")  # untracked
        self.assertEqual(r3.check("protected")["codes"], ["protected-path"])

    def test_subject_only_trailer_text_is_not_a_trailer(self):
        r = self.repo()
        r.write("tests/acceptance/a.py", "x\n")
        r.g("add", "-A")
        r.g("commit", "-q", "-m", "Acceptance-Change: demo")
        self.assertEqual(r.check("protected")["codes"], ["protected-path"])

    def test_other_paths_and_custom_patterns(self):
        r = self.repo({"commands": {}, "gate": {"protected": ["locked/*.txt"]}})
        r.write("src/a.py", "x\n")
        r.write("locked/sub/b.txt", "x\n")  # `*` does not cross folders
        r.commit("work")
        self.assertEqual(r.check("protected")["status"], "pass")
        r.write("locked/c.txt", "x\n")
        r.commit("more")
        self.assertEqual(r.check("protected")["codes"], ["protected-path"])

    def test_baseline_shrunk(self):
        r = self.repo()
        r.write(gate.BASELINE, json.dumps({"passing": ["a", "b"]}))
        r.commit("baseline", "Acceptance-Change: demo")
        base = r.g("rev-parse", "HEAD").strip()
        r.write(gate.BASELINE, json.dumps({"passing": ["a", "b", "c"]}))
        r.commit("grow")
        self.assertEqual(gate.run_gate(r.root, base, {"protected"})["checks"][0]["status"], "pass")  # growing is fine
        r.write(gate.BASELINE, json.dumps({"passing": ["a"]}))
        r.commit("shrink")
        c = gate.run_gate(r.root, base, {"protected"})["checks"][0]
        self.assertEqual(c["codes"], ["baseline-shrunk"])
        r.commit("shrink again", "Acceptance-Change: demo")  # empty commit; the shrinking commit still lacks it
        self.assertEqual(gate.run_gate(r.root, base, {"protected"})["checks"][0]["codes"], ["baseline-shrunk"])
        r2 = self.repo()
        r2.write(gate.BASELINE, json.dumps({"passing": ["a", "b"]}))
        r2.commit("baseline", "Acceptance-Change: demo")
        base2 = r2.g("rev-parse", "HEAD").strip()
        r2.write(gate.BASELINE, json.dumps({"passing": ["a"]}))
        r2.commit("shrink", "Acceptance-Change: demo")
        self.assertEqual(gate.run_gate(r2.root, base2, {"protected"})["checks"][0]["status"], "pass")


class Review(Base):
    def mode(self, mode):
        return self.repo({"commands": {}, "gate": {"review": mode}})

    def test_modes(self):
        for mode, want in (("off", ("skip", [])), ("advisory", ("warn", ["review-missing"])),
                           ("required", ("fail", ["review-missing"]))):
            r = self.mode(mode)
            r.commit("work")
            c = r.check("review")
            self.assertEqual((c["status"], c["codes"]), want, mode)
        self.assertEqual(self.repo().run("review")["verdict"], "pass")

    def test_ship_and_fix_first(self):
        for mode in ("advisory", "required"):
            r = self.mode(mode)
            r.commit("work")
            r.commit("review", "Review: ship")
            self.assertEqual(r.check("review")["status"], "pass")
            r.commit("review", "Review: fix-first")
            c = r.check("review")
            self.assertEqual((c["status"], c["codes"]), ("fail", ["review-fix-first"]))
            r.commit("fixed", "Review: ship")  # the newest review wins
            self.assertEqual(r.check("review")["status"], "pass")

    def test_merge_commits_do_not_count(self):
        r = self.mode("required")
        r.g("checkout", "-q", "-b", "side")
        r.commit("side work")
        r.g("checkout", "-q", "-")
        r.commit("main work")
        r.g("merge", "-q", "--no-ff", "side", "-m", "merge side", "-m", "Review: ship")
        self.assertEqual(r.check("review")["codes"], ["review-missing"])


class Security(Base):
    def added(self, rel, text, **kw):
        r = self.repo(kw.get("factory"))
        r.write(rel, text)
        r.commit("add")
        return r.check("security")

    def test_secret_patterns(self):
        for text in (KEY + "\n", "k = '%s'\n" % GH, "k: %s\n" % AWS, "api_key = \"%s\"\n" % ("a1" * 16),
                     "const token = '%s'\n" % ("Zz9" * 10)):
            c = self.added("app/cfg.py", text)
            self.assertEqual((c["status"], c["codes"]), ("fail", ["secret-in-diff"]), text[:20])
            self.assertIn("app/cfg.py:1", c["detail"])
            self.assertNotIn(GH, c["detail"])  # never echo the secret

    def test_no_false_positives(self):
        for text in ("token = os.environ['TOKEN']\n", "api_key = 'your-api-key-goes-here-please'\n", "token: ''\n",
                     "tokens = 12345678901234567890123456789\n", "# see https://example.com/a/b?x=1\n"):
            self.assertEqual(self.added("app/ok.py", text)["status"], "pass", text)

    def test_ignore_globs(self):
        self.assertEqual(self.added(".factory/tests/x.py", KEY + "\n")["status"], "pass")
        self.assertEqual(self.added("evals/x/y.txt", GH + "\n")["status"], "pass")
        c = self.added("src/x.txt", KEY + "\n", factory={"commands": {}, "gate": {"security_ignore": ["src/**"]}})
        self.assertEqual(c["status"], "pass")

    def test_only_added_lines_are_scanned(self):
        r = self.repo()
        r.write("old.txt", KEY + "\n")
        r.commit("legacy secret")
        base = r.g("rev-parse", "HEAD").strip()
        r.write("old.txt", KEY + "\nmore\n")  # the existing line is unchanged context
        r.commit("touch")
        v = gate.run_gate(r.root, base, {"security"})
        self.assertEqual(v["checks"][0]["status"], "pass")

    def test_env_files(self):
        for name in (".env", ".env.production", ".dev.vars", ".dev.vars.local"):
            c = self.added("app/" + name, "A=1\n")
            self.assertEqual((c["status"], c["codes"]), ("fail", ["env-file-added"]), name)
        self.assertEqual(self.added(".env.example", "A=1\n")["status"], "pass")
        r = self.repo()
        r.write(".env", "A=1\n")  # untracked and not ignored still counts
        self.assertEqual(r.check("security")["codes"], ["env-file-added"])
        r2 = self.repo()
        r2.write(".gitignore", ".env\n")
        r2.write(".env", "A=1\n")
        self.assertEqual(r2.check("security")["status"], "pass")

    def test_unpinned_action(self):
        wf = "jobs:\n  a:\n    steps:\n      - uses: %s\n"
        c = self.added(".github/workflows/x.yml", wf % "actions/checkout@v4")
        self.assertEqual((c["status"], c["codes"]), ("fail", ["unpinned-action"]))
        self.assertEqual(self.added(".github/workflows/x.yml", wf % ("actions/checkout@" + "a" * 40 + " # v4"))["status"], "pass")
        self.assertEqual(self.added(".github/workflows/x.yml", wf % "./local-action")["status"], "pass")
        self.assertEqual(self.added(".github/workflows/x.yml", "      # - uses: actions/checkout@v4\n")["status"], "pass")

    def test_pipe_to_shell(self):
        c = self.added("scripts/i.sh", "curl -fsSL https://x.test/i | sudo bash\n")
        self.assertEqual((c["status"], c["codes"]), ("fail", ["pipe-to-shell"]))
        self.assertEqual(self.added("scripts/i.sh", "wget -qO- https://x.test/i | sh\n")["codes"], ["pipe-to-shell"])
        self.assertEqual(self.added("scripts/i.sh", "curl -fsSL https://x.test/i -o i.sh\n")["status"], "pass")
        self.assertEqual(self.added("docs/x.md", "never run curl x | sh\n")["status"], "pass")

    def test_paths_with_unicode_spaces_and_plus_content(self):
        for rel in ("app/caf\u00e9.py", "app/with space.py", "app/we\"ird.py"):
            self.assertEqual(self.added(rel, "k = '%s'\n" % AWS)["codes"], ["secret-in-diff"], rel)
        c = self.added("app/a.py", "x\n++ x\nk = '%s'\n" % AWS)  # a content line "++ x" shows up as "+++ x"
        self.assertEqual((c["codes"], c["detail"]), (["secret-in-diff"], "secret-in-diff app/a.py:3"))
        lines = gate.added_lines("diff --git a/f b/f\n--- a/f\n+++ b/f\t\n@@ -0,0 +1,2 @@\n+++ b/evil\n+k\n")
        self.assertEqual(lines, [("f", 1, "++ b/evil"), ("f", 2, "k")])

    def test_protected_path_with_unicode_name(self):
        r = self.repo()
        r.write("tests/acceptance/caf\u00e9/t.py", "x\n")
        r.commit("sneak")
        c = r.check("protected")
        self.assertEqual(c["codes"], ["protected-path"])

    def test_more_secret_shapes(self):
        tok = "a1B2" * 7
        for rel, text in (("a.py", 'GITHUB_TOKEN = "%s"\n' % tok), ("a.py", 'OPENAI_API_KEY="%s"\n' % tok),
                          ("a.yml", "api_key: %s\n" % tok), ("prod.env", "API_KEY=%s\n" % tok),
                          ("a.py", "k = 'sk_" + "live_" + "a" * 20 + "'\n"), ("a.py", "k = 'rk_" + "live_" + "a" * 20 + "'\n"),
                          ("a.py", "k = 'sk-" + "proj-" + "a1" * 12 + "'\n"), ("a.py", "k = 'sk-" + "A1" * 20 + "'\n"),
                          ("a.py", 'password = "hunter2hunter"\n'), ("a.json", '{"secret": "Abcd1234efgh"}\n'),
                          ("a.py", "x_AKIA" + "A" * 16 + "_y\n")):
            self.assertEqual(self.added(rel, text)["codes"], ["secret-in-diff"], (rel, text))

    def test_more_non_secrets(self):
        for rel, text in (("a.js", 'const token = "some.long.i18n.translation.key"\n'),
                          ("a.py", "password = process.env.DB_PASSWORD\n"), ("a.py", "token = get_token_value2(x)\n"),
                          ("a.yml", "api_key: ${API_KEY_FROM_CI_SECRETS_STORE}\n"), ("prod.env", "API_KEY=<paste-your-key-here-1234>\n"),
                          ("prod.env", "API_KEY=$OTHER_VARIABLE_NAME_1234567\n"), ("a.py", 'password = "changeme123"\n'),
                          ("a.py", 'password = "xxxxxxxxxxxx"\n'), ("a.py", 'secret = "my-secret-name"\n'),
                          ("a.py", "token = os.environ.get('GITHUB_TOKEN_NAME_X')\n"), ("a.py", "token = self.next_token_value1\n")):
            self.assertEqual(self.added(rel, text)["status"], "pass", (rel, text))

    def test_more_pipe_to_shell(self):
        for text in ("bash <(curl -fsSL https://x.test/i)\n", 'sh -c "$(curl -fsSL https://x.test/i)"\n',
                     "wget -qO- https://x.test/i | bash\n", "curl -fsSL https://x.test/i | sudo sh\n",
                     "curl -fsSL https://x.test/i | sudo -E bash -s\n", 'eval "$(curl -fsSL https://x.test/i)"\n'):
            self.assertEqual(self.added("scripts/i.sh", text)["codes"], ["pipe-to-shell"], text)
        self.assertEqual(self.added("scripts/i.sh", 'x="$(curl -fsSL https://x.test/i)"\n')["status"], "pass")

    def test_working_tree_changes_count(self):
        r = self.repo()
        r.write("a.txt", "x\n")
        r.commit("a")
        r.write("a.txt", "x\n" + GH + "\n")  # tracked, uncommitted
        self.assertEqual(r.check("security")["codes"], ["secret-in-diff"])

    def test_gate_source_has_no_findings_itself(self):
        lines = []
        for part in ("gate.py", "gate_checks.py"):  # the secret patterns moved to gate_checks.py (SIZE-3)
            with open(os.path.join(ROOT, "scripts", part), encoding="utf-8") as fh:
                lines += [("scripts/" + part, i + 1, l) for i, l in enumerate(fh.read().splitlines())]
        self.assertEqual(gate.scan(lines, []), [])


class Helpers(unittest.TestCase):
    def test_trailers(self):
        self.assertEqual(gate.trailers("subj\n\nbody\n\nReview: ship\nRefs: A-1\n"), {"review": ["ship"], "refs": ["A-1"]})
        self.assertEqual(gate.trailers("Review: ship"), {})
        self.assertEqual(gate.trailers("subj\n\nReview:   fix-first  \n")["review"], ["fix-first"])

    def test_glob(self):
        self.assertTrue(gate.matches("tests/acceptance/a/b.py", ["tests/acceptance/**"]))
        self.assertFalse(gate.matches("tests/acceptance", ["tests/acceptance/**"]))
        self.assertFalse(gate.matches("src/x.py", ["tests/**"]))
        self.assertTrue(gate.matches("a/b/c.txt", ["**/c.txt"]))
        self.assertTrue(gate.matches("c.txt", ["**/c.txt"]))
        self.assertFalse(gate.matches("a/b/c.txt", ["*.txt"]))

    def test_summary_markdown(self):
        v = {"verdict": "fail", "sha": "abc", "base": None, "seconds": 1.2, "codes": ["x"],
             "checks": [{"id": "lint", "status": "fail", "codes": ["lint-failed"], "detail": "a|b", "seconds": 0.5}]}
        md = gate.summary_md(v)
        self.assertIn("**Merge gate: FAIL**", md)
        self.assertIn("| lint | fail | lint-failed | 0.5 |", md)
        self.assertNotIn("a|b", md)


def row(verdict, sha, codes=(), secs=10, **kw):
    chk = [{"id": "lint", "status": "fail" if codes else "pass", "codes": list(codes), "detail": "", "seconds": 1.0}]
    return dict({"verdict": verdict, "sha": sha, "base": "b", "ts": "2026-11-12T10:00:00+00:00", "seconds": secs,
                 "checks": chk, "codes": list(codes)}, **kw)


class Dashboard(unittest.TestCase):
    def test_empty_state(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(tab_gates.gate_rows(d), [])
        self.assertIsNone(tab_gates.gate_stats([], 120))
        self.assertIn("No gate runs yet: run `python3 scripts/gate.py`.", tab_gates.render_gate(None).replace("&#x27;", "'").replace("&quot;", '"'))
        self.assertEqual(tab_gates.gate_line(None), "merge gate: no runs yet")

    def test_stats_first_try_and_codes(self):
        rows = [row("fail", "s1", ["lint-failed"]), row("pass", "s1"), row("pass", "s2"), row("fail", "s3", ["build-failed", "lint-failed"]),
                row("pass", "s3", secs=30)]
        g = tab_gates.gate_stats(rows, 120)
        self.assertEqual(g["first_try_rate"], 33)  # only s2 passed first of 3 shas
        self.assertEqual(g["pass_rate"], 60)
        self.assertEqual(g["top_codes"][0], ("lint-failed", 2))
        self.assertEqual(g["last"]["verdict"], "pass")
        self.assertIn("first-try 33%", tab_gates.gate_line(g))
        self.assertIn("(budget 120s)", tab_gates.gate_line(g))

    def test_window_is_last_20(self):
        rows = [row("fail", "s%d" % i, ["lint-failed"]) for i in range(10)] + [row("pass", "p%d" % i) for i in range(20)]
        g = tab_gates.gate_stats(rows, 120)
        self.assertEqual((g["window"], g["pass_rate"], g["top_codes"]), (20, 100, []))

    def test_rows_skip_malformed_and_only_runs(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "metrics"))
        with open(os.path.join(d, "metrics", "gate.local.jsonl"), "w") as fh:
            fh.write("garbage\n[1]\n{\"verdict\": \"maybe\", \"checks\": []}\n{\"verdict\": \"pass\", \"checks\": \"x\"}\n"
                     + json.dumps(row("pass", "a")) + "\n" + json.dumps(row("fail", "b", ["x"], only=["lint"])) + "\n"
                     + json.dumps(row("fail", "c", ["x"], seconds="bad")) + "\n")
        rows = tab_gates.gate_rows(d)
        self.assertEqual([r["sha"] for r in rows], ["a", "c"])
        self.assertEqual(tab_gates.gate_stats(rows, None)["last"]["seconds"], 0.0)

    def test_render_with_rows_escapes(self):
        g = tab_gates.gate_stats([row("fail", "<b>x", ["<script>alert(1)</script>"])], 5)
        html_ = tab_gates.render_gate(g)
        self.assertNotIn("<script>", html_)
        self.assertNotIn("<b>x", html_)
        self.assertIn("&lt;script&gt;", html_)
        self.assertIn("Merge gate", html_)
        self.assertIn("(over)", html_)
        self.assertIn('class="imp high"', html_)
        full = tab_gates.render({"gate": g, "items_total": 0, "components_total": 0})
        self.assertIn("Merge gate", full)
        self.assertIn("No backlog items yet", full)

    def test_collect_has_gate_key(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        out = tab_gates.collect(d, {})
        self.assertIsNone(out["gate"])
        self.assertIn("merge gate: no runs yet", tab_gates.line(out))


@unittest.skipUnless(os.path.isfile(os.path.join(ROOT, ".github", "workflows", "ci.yml")), "template CI is not part of an adopted project")
class CiWiring(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8") as fh:
            self.ci = fh.read()

    def test_gate_job_calls_gate_script(self):
        self.assertRegex(self.ci, r"(?m)^  gate:\s*$")
        self.assertNotRegex(self.ci, r"(?m)^  check:\s*$")
        self.assertIn('python3 scripts/gate.py --base "$BASE" --summary "$GITHUB_STEP_SUMMARY"', self.ci)
        self.assertIn("github.event.pull_request.base.sha || github.event.before", self.ci)
        self.assertIn("fetch-depth: 0", self.ci)
        self.assertNotIn("${{", self.ci.split("scripts/gate.py")[1].split("\n")[0])  # no expression inlined in the command

    def test_gate_replaces_separate_steps_and_runs_before_dashboard(self):
        code = "\n".join(l for l in self.ci.splitlines() if not l.lstrip().startswith("#"))
        self.assertNotIn("bash scripts/check.sh", code)
        self.assertNotIn("metrics.py test", code)
        self.assertLess(code.index("scripts/gate.py"), code.index("scripts/ci_runs.py"))
        self.assertLess(code.index("scripts/ci_runs.py"), code.index("scripts/dashboard.py"))
        self.assertEqual(code.count("if: always()"), 3)

    def test_no_eval_step(self):
        self.assertNotRegex(self.ci, r"evals")
        self.assertNotRegex(self.ci, r"claude\s+-p")


if __name__ == "__main__":
    unittest.main()
