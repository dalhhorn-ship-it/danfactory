"""Self-tests for danfactory hooks and scripts (stdlib unittest)."""
import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOOKS = os.path.join(ROOT, ".claude", "hooks")
with open(os.path.join(ROOT, "factory.json"), encoding="utf-8") as _fh:
    IS_TEMPLATE = not json.load(_fh).get("project", {}).get("name")
template_only = unittest.skipUnless(IS_TEMPLATE, "only meaningful in the un-bootstrapped template repo")


def hook(name, event, env=None):
    e = {k: v for k, v in os.environ.items() if k != "FACTORY_ALLOW_LARGE_READ"}
    e.update(CLAUDE_PROJECT_DIR=ROOT, **(env or {}))
    return subprocess.run([sys.executable, os.path.join(HOOKS, name)], input=json.dumps(event),
                          capture_output=True, text=True, env=e)


class GuardLargeRead(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.big = os.path.join(cls.tmp, "big.txt")
        cls.small = os.path.join(cls.tmp, "small.txt")
        open(cls.big, "w").write("x\n" * 1000)
        open(cls.small, "w").write("x\n" * 10)

    def read(self, path, **extra):
        return hook("guard_large_read.py", {"tool_name": "Read", "cwd": self.tmp,
                                            "tool_input": {"file_path": path, **extra}})

    def bash(self, cmd, **ev):
        return hook("guard_large_read.py", {"tool_name": "Bash", "cwd": self.tmp,
                                            "tool_input": {"command": cmd}, **ev})

    def test_blocks_big_read(self):
        r = self.read(self.big)
        self.assertEqual(r.returncode, 2)
        self.assertIn("bulk-reader", r.stderr)

    def test_allows_small_targeted_missing(self):
        self.assertEqual(self.read(self.small).returncode, 0)
        self.assertEqual(self.read(self.big, offset=10, limit=50).returncode, 0)
        self.assertEqual(self.read(os.path.join(self.tmp, "nope.txt")).returncode, 0)

    def test_allows_inside_subagent(self):
        r = hook("guard_large_read.py", {"tool_name": "Read", "agent_id": "a1", "agent_type": "bulk-reader",
                                         "tool_input": {"file_path": self.big}})
        self.assertEqual(r.returncode, 0)

    def test_escape_hatch(self):
        r = hook("guard_large_read.py", {"tool_name": "Read", "tool_input": {"file_path": self.big}},
                 env={"FACTORY_ALLOW_LARGE_READ": "1"})
        self.assertEqual(r.returncode, 0)

    def test_bash(self):
        self.assertEqual(self.bash("cat big.txt").returncode, 2)
        self.assertEqual(self.bash("cat -n big.txt").returncode, 2)
        self.assertEqual(self.bash("cat big.txt | grep x").returncode, 0)
        self.assertEqual(self.bash("cat big.txt > out.txt").returncode, 0)
        self.assertEqual(self.bash("head -20 big.txt").returncode, 0)
        self.assertEqual(self.bash("head big.txt").returncode, 0)          # 10 lines
        self.assertEqual(self.bash("tail -n +1 big.txt").returncode, 2)    # whole file
        self.assertEqual(self.bash("head -n 5000 big.txt").returncode, 2)
        self.assertEqual(self.bash("sed -n 1,9999p big.txt").returncode, 2)
        self.assertEqual(self.bash("sed -n 10,40p big.txt").returncode, 0)
        self.assertEqual(self.bash("cat small.txt").returncode, 0)
        self.assertEqual(self.bash("git status").returncode, 0)


class BashPolicy(unittest.TestCase):
    def check(self, cmd):
        return hook("guard_bash_policy.py", {"tool_name": "Bash", "tool_input": {"command": cmd}}).returncode

    def test_blocks_deploy_bypasses(self):
        w = "wrangler " + "deploy"
        for cmd in ("npx " + w, "bunx " + w, "cd app && npx wrangler pages deploy dist",
                    "git push origin main --no-verify", "git commit -n -m x"):
            self.assertEqual(self.check(cmd), 2, cmd)

    def test_blocks_text_piped_to_a_shell(self):  # upstreamed from lpdan (its SEC-003)
        w = "wrangler " + "deploy"
        for cmd in ('echo "npx %s" | sh' % w, "printf 'npx %s' | bash" % w, "cat <<EOF | bash\nnpx %s\nEOF" % w):
            self.assertEqual(self.check(cmd), 2, cmd)
        self.assertEqual(self.check('echo "npx %s" > notes.txt' % w), 0)
        self.assertEqual(self.check("echo 'a | sh' && ls"), 0)

    def test_ignores_text_being_written(self):
        w = "wrangler " + "deploy"
        self.assertEqual(self.check("cat > notes.md <<'EOF'\nnever run npx %s\nEOF" % w), 0)
        self.assertEqual(self.check("git commit -m 'docs: explain why %s is denied'" % w), 0)
        self.assertEqual(self.check("echo ok && npx %s" % w), 2)

    def test_allows_normal_and_rollback(self):
        self.assertEqual(self.check("npx wrangler " + "deploy --dry-run --outdir /tmp/x"), 0)
        for cmd in ("git push -u origin HEAD", "git push -n origin main", "npx wrangler rollback",
                    "npx wrangler whoami", "git commit -m 'fix'"):
            self.assertEqual(self.check(cmd), 0, cmd)


class OneShotEscape(unittest.TestCase):
    @unittest.skipIf(os.environ.get("DANFACTORY_TREE_SANDBOX") == "1", "inside the runner's sandbox the repo is read-only by design (runs in CI and check.sh)")
    def test_marker_allows_one_read_then_is_consumed(self):
        big = os.path.join(tempfile.mkdtemp(), "big.txt")
        with open(big, "w") as fh:
            fh.write("x\n" * 1000)
        marker = os.path.join(ROOT, ".claude", ".allow-large-read")
        open(marker, "w").close()
        ev = {"tool_name": "Read", "tool_input": {"file_path": big}}
        self.assertEqual(hook("guard_large_read.py", ev).returncode, 0)
        self.assertFalse(os.path.exists(marker))
        self.assertEqual(hook("guard_large_read.py", ev).returncode, 2)


class RecordTokens(unittest.TestCase):
    def test_weighted_includes_subagents_and_skips_template(self):
        sys.path.insert(0, HOOKS)
        import record_tokens
        d = tempfile.mkdtemp()
        main_t = os.path.join(d, "s1.jsonl")
        os.makedirs(os.path.join(d, "s1", "subagents"))
        u = {"input_tokens": 100, "output_tokens": 10, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 0}
        for path in (main_t, os.path.join(d, "s1", "subagents", "agent-a.jsonl")):
            with open(path, "w") as fh:
                fh.write(json.dumps({"type": "assistant", "message": {"id": path, "model": "m", "usage": u}}) + "\n")
        self.assertEqual(record_tokens.weighted(u), 100 + 50 + 100)
        self.assertEqual(len(record_tokens.subagent_transcripts(main_t)), 1)
        if not IS_TEMPLATE:
            return
        # the un-bootstrapped template (empty project.name) must not record anything
        before = os.path.exists(os.path.join(ROOT, "metrics", "tokens.jsonl"))
        # template detection reads git remote origin; inject it for this one subprocess so the test does not depend
        # on the checkout's remotes (a sandbox without origin would otherwise write into the real metrics/)
        with open(os.path.join(ROOT, "factory.json"), encoding="utf-8") as fh:
            src = json.load(fh)["template"]["source_repo"]
        hook("record_tokens.py", {"transcript_path": main_t, "session_id": "x"},
             env={"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "remote.origin.url",
                  "GIT_CONFIG_VALUE_0": "https://github.com/%s.git" % src})
        self.assertEqual(os.path.exists(os.path.join(ROOT, "metrics", "tokens.jsonl")), before)

    def test_session_shas_window_and_git_failure(self):
        sys.path.insert(0, HOOKS)
        import datetime
        import record_tokens
        tmp = tempfile.mkdtemp()
        tp = os.path.join(tmp, "t.jsonl")
        with open(tp, "w") as fh:
            fh.write(json.dumps({"timestamp": "2026-11-07T10:00:00Z"}) + "\n")
            fh.write(json.dumps({"timestamp": "2026-11-07T09:00:00Z"}) + "\n")
            fh.write("junk\n")
        self.assertEqual(record_tokens.first_timestamp(tp),
                         datetime.datetime(2026, 11, 7, 9, 0, tzinfo=datetime.timezone.utc))
        end = datetime.datetime.now(datetime.timezone.utc)
        self.assertIsInstance(record_tokens.session_shas(tp, end), list)
        empty = os.path.join(tmp, "e.jsonl")
        open(empty, "w").close()
        self.assertEqual(record_tokens.session_shas(empty, end), [])
        old = record_tokens.ROOT
        record_tokens.ROOT = os.path.join(tmp, "missing")  # git cannot run there
        try:
            self.assertEqual(record_tokens.session_shas(tp, end), [])
        finally:
            record_tokens.ROOT = old

    def test_dedupes_and_sums(self):
        tmp = tempfile.mkdtemp()
        tp = os.path.join(tmp, "t.jsonl")
        u = {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 1}
        with open(tp, "w") as fh:
            for mid in ("m1", "m1", "m2"):
                fh.write(json.dumps({"type": "assistant", "message": {"id": mid, "model": "x", "usage": u}}) + "\n")
            fh.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
        sys.path.insert(0, HOOKS)
        import record_tokens
        totals, by_model, n = record_tokens.summarize(tp)
        self.assertEqual(n, 2)
        self.assertEqual(totals["input_tokens"], 20)
        self.assertEqual(sum(totals.values()), 232)


class Metrics(unittest.TestCase):
    def test_analyse_flags_slow_tests_and_coverage_drop(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import metrics
        f = json.load(open(os.path.join(ROOT, "factory.json")))
        f["commands"]["test"] = "true"
        hist = [{"ts": "2026-11-01T00:00:00+00:00", "kind": "test", "scope": "full", "sha": "a", "ok": True,
                 "seconds": 50, "coverage_pct": 90},
                {"ts": "2026-11-02T00:00:00+00:00", "kind": "test", "scope": "full", "sha": "b", "ok": True,
                 "seconds": 300, "coverage_pct": 70}]
        alerts, ideas, table = metrics.analyse(f, hist, [])
        text = " ".join(alerts)
        self.assertIn("budget", text)
        self.assertIn("Coverage", text)
        self.assertTrue(any("affected" in i for i in ideas))

    def test_lcov_parser(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import metrics
        p = os.path.join(tempfile.mkdtemp(), "lcov.info")
        open(p, "w").write("LF:10\nLH:8\nLF:10\nLH:2\n")
        self.assertEqual(metrics._lcov(p), 50.0)


class Dashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import dashboard
        cls.d = dashboard

    def test_backlog_parser(self):
        ms = self.d.parse_backlog("""# Backlog
```
- [x] example inside code fence is ignored
```
## Milestone: M1 — Skeleton (target: 2026-12-01)
- [x] done item (S) #infra
- [~] doing item
- [!] blocked item
- [-] dropped item
- [ ] todo item
""")
        self.assertEqual(len(ms), 1)
        m = ms[0]
        self.assertEqual((m["name"], m["target"], m["done"], m["total"], m["pct"]), ("M1 — Skeleton", "2026-12-01", 1, 4, 25))
        self.assertEqual(m["items"][0]["size"], "S")
        self.assertEqual(m["items"][0]["tags"], ["infra"])
        self.assertEqual(m["items"][0]["title"], "done item")

    def test_debt_parser(self):
        items = self.d.parse_debt("""## Open
- [ ] TD-001 Buffering uploads — impact: high · effort: M · area: api
## Resolved
- [x] TD-000 No CI cache — impact: low · effort: S · area: ci
""")
        self.assertEqual([(i["id"], i["open"], i["impact"], i["effort"], i["area"]) for i in items],
                         [("TD-001", True, "high", "M", "api"), ("TD-000", False, "low", "S", "ci")])

    def test_roadmap_swimlanes_and_sequence(self):
        ms = self.d.parse_backlog("""## Milestone: M1
> Sequence: riskiest first, then polish
- [x] Login works #value
- [ ] Set up CI (S) #ci
- [-] Dropped idea
- [ ] Share a list AC: can share via link
## Milestone: M2
- [~] Split storage layer #arch
- [ ] Export to CSV #feature
""")
        debt = [{"id": "TD-001", "title": "No retries", "impact": "high", "effort": "S"}]
        rm = self.d.roadmap(ms, debt)
        cols = rm["columns"]
        self.assertEqual([c["name"] for c in cols], ["M1", "M2", "Tech debt to schedule"])
        self.assertEqual((cols[0]["sequence"], cols[1]["sequence"]), ("riskiest first, then polish", ""))  # AC1
        lane = lambda i, k: [(x["title"], x["seq"]) for x in cols[i]["lanes"][k]]
        # AC2/AC8: one global number in file order, open cards first, done ones trail
        self.assertEqual(lane(0, "value"), [("Share a list AC: can share via link", 2), ("Login works", None)])
        self.assertEqual(lane(0, "foundation"), [("Set up CI", 1)])
        self.assertEqual(lane(1, "foundation"), [("Split storage layer", 3)])
        self.assertEqual(lane(1, "value"), [("Export to CSV", 4)])
        self.assertEqual(lane(2, "foundation"), [("TD-001 No retries", 5)])  # AC3: debt continues the sequence
        self.assertEqual(rm["open"], {"value": 2, "foundation": 3})
        # AC6/AC7: next up = three lowest numbers, short title cut before " AC:"
        self.assertEqual([(x["seq"], x["short"], x["lane"]) for x in rm["next"]],
                         [(1, "Set up CI", "foundation"), (2, "Share a list", "value"), (3, "Split storage layer", "foundation")])
        html = self.d.render_roadmap(rm)
        for text in ("Technical foundation", "Value-driven features", "Next up", "riskiest first, then polish"):
            self.assertIn(text, html)
        self.assertNotIn("<script", html)  # AC12

    def test_roadmap_done_collapse_and_empty_states(self):
        ms = self.d.parse_backlog("""## Milestone: M0 — Setup
- [x] a
- [-] dropped does not block done
## Milestone: M1
- [ ] b <i>
""")
        rm = self.d.roadmap(ms, [])
        self.assertEqual(rm["done"], [{"name": "M0 — Setup", "done": 1, "total": 1}])  # AC4
        self.assertEqual([c["name"] for c in rm["columns"]], ["M1"])
        self.assertEqual(len(rm["next"]), 1)  # AC6: fewer than three
        html = self.d.render_roadmap(rm)
        self.assertIn("Done: M0 — Setup (1/1)", html)
        self.assertIn("b &lt;i&gt;", html)  # AC12: escaped
        all_done = self.d.roadmap(self.d.parse_backlog("## Milestone: M0\n- [x] a\n"), [])
        self.assertEqual((all_done["columns"], all_done["next"]), ([], []))  # AC5, AC6 (none)
        html = self.d.render_roadmap(all_done)
        self.assertIn("Everything planned is done", html)
        self.assertNotIn("Next up", html)

    def test_roadmap_prd_badge(self):
        import tempfile
        rel = "docs/specs/_test-badge-%d.md" % os.getpid()
        path = os.path.join(ROOT, rel)
        try:
            with open(path, "w") as fh:
                fh.write("# PRD\n\n> Status: approved · 2026-11-07 · by user in chat\n")
            ms = self.d.parse_backlog("## Milestone: M1\n- [ ] Linked item (%s) (S)\n- [ ] [Linked text](docs/specs/missing.md)\n- [ ] Plain\n" % rel)
            items = ms[0]["items"]
            self.assertEqual([(i["title"], i["spec"]) for i in items],
                             [("Linked item", rel), ("Linked text", "docs/specs/missing.md"), ("Plain", "")])
            cards = self.d.roadmap(ms, [])["columns"][0]["lanes"]["value"]
            self.assertEqual([c["prd"] for c in cards], ["approved", "", ""])  # AC9: missing file -> no badge
            self.assertIn("PRD approved", self.d.render_roadmap(self.d.roadmap(ms, [])))
        finally:
            os.remove(path)

    def test_build_writes_artefacts(self):
        d = self.d.build()
        for name in ("index.html", "data.json", "SUMMARY.md"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "dashboard", name)), name)
        page = open(os.path.join(ROOT, "dashboard", "index.html"), encoding="utf-8").read()
        self.assertIn("<title>", page)
        self.assertIn("prefers-color-scheme: dark", page)
        self.assertIn("progress", d)
        self.assertIn("roadmap", d)
        self.assertIn('id="tab-roadmap"', page)
        for tab in ("architecture", "traceability", "decisions", "gates", "docs", "flow", "cost", "hotspots"):
            self.assertIn('id="tab-%s"' % tab, page)
            self.assertIn(tab, d)
        self.assertIn("layers", d["architecture"])
        self.assertIn("chains", d["traceability"])
        self.assertIn("adrs", d["decisions"])
        self.assertIn("deps", d["gates"])
        self.assertIn("orphans", d["docs"])
        self.assertIn("unattributed", d["cost"])
        self.assertIn("deploys", d["flow"])
        self.assertIn("files", d["hotspots"])


class DeliveryBackflow(unittest.TestCase):
    """docs/specs/dashboard-delivery-backflow.md acceptance criteria 1-9 and 11."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import ci_runs
        import dashboard
        from obs import delivery
        cls.d, cls.ci, cls.dl = dashboard, ci_runs, delivery
        import datetime
        cls.today = datetime.date(2026, 11, 7)  # ISO week 2026-W45

    @staticmethod
    def run_(i, day, conclusion="success", branch="main", mins=2, name="ci"):
        return {"id": i, "name": name, "head_branch": branch, "conclusion": conclusion, "status": "completed",
                "created_at": "%sT10:00:00Z" % day, "run_started_at": "%sT10:00:00Z" % day,
                "updated_at": "%sT10:%02d:00Z" % (day, mins), "html_url": "https://github.com/o/r/actions/runs/%d" % i}

    def runs(self):
        r = self.run_
        return [r(1, "2026-11-05"), r(2, "2026-11-05", "failure", "feat", 6, "ci<b>x</b>"), r(3, "2026-11-04", "failure", "main", 4),
                r(4, "2026-11-04", "cancelled"), r(5, "2026-11-03", "skipped"), r(6, "2026-11-03", "success", "main", 10),
                r(7, "2026-10-28", "cancelled")]  # week 44 has no decided run

    def test_ac1_metrics_and_failures(self):
        m = self.dl.ci_metrics(self.runs(), self.today, "main")
        self.assertEqual((m["decided_30"], m["pass_rate_30"]), (4, 50))  # cancelled and skipped are not decided
        self.assertEqual((m["main_decided"], m["main_pass_rate"]), (3, 67))
        self.assertEqual((m["median_min"], m["p90_min"]), (5.0, 10.0))
        self.assertEqual(len(m["failures"]), 2)
        html_ = self.dl.render({"ci": m, "releases": None})
        self.assertIn('href="https://github.com/o/r/actions/runs/2"', html_)
        self.assertIn("50%", html_)

    def test_ac2_weekly_bars(self):
        m = self.dl.ci_metrics(self.runs(), self.today, "main")
        self.assertEqual(len(m["weeks"]), 8)
        self.assertEqual(m["weeks"][-1], "2026-W45")
        self.assertIsNone(m["pass_per_week"][-2])  # W44: only a cancelled run
        self.assertEqual(m["pass_per_week"][-1], 50)
        html_ = self.dl.render({"ci": m, "releases": None})
        self.assertEqual(html_.count("<svg"), 2)
        self.assertIn("2026-W44: no data", html_)
        self.assertNotIn("2026-W44: 0", html_)

    def test_ac3_missing_or_invalid_cache(self):
        self.assertIsNone(self.dl.parse_runs(""))
        self.assertIsNone(self.dl.parse_runs("{not json"))
        with tempfile.TemporaryDirectory() as root:
            for text in (None, "{broken"):
                if text:
                    os.makedirs(os.path.join(root, "metrics"))
                    with open(os.path.join(root, "metrics", "ci-runs.json"), "w") as fh:
                        fh.write(text)
                dl = self.dl.collect(root, {}, self.today)
                self.assertIsNone(dl["ci"])
                self.assertIn("no CI history yet", self.dl.render(dl).replace("No CI", "no CI"))
                self.assertEqual(self.dl.line(dl), "")

    def test_ac4_release_cadence(self):
        text = "# Changelog\n## [Unreleased]\n## [1.2.0] - 2026-11-01\n## 1.1.0 (2026-10-01)\n## 1.0.0 (2026-09-21)\n"
        found = self.dl.parse_changelog(text)
        self.assertEqual([r["version"] for r in found], ["1.2.0", "1.1.0", "1.0.0"])
        rel = self.dl.release_metrics(found, self.today)
        self.assertEqual((rel["count"], rel["median_gap_days"], rel["days_since_last"]), (3, 20.5, 6))
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "CHANGELOG.md"), "w") as fh:
                fh.write(text)
            dl = self.dl.collect(root, {}, self.today)
            self.assertEqual(dl["releases"]["source"], "CHANGELOG")
            self.assertIn("6 days since 1.2.0", self.dl.render(dl))
        with tempfile.TemporaryDirectory() as root:  # no changelog: release-like tags; non-release tags ignored
            g = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
            subprocess.run(g + ["init", "-q", root], check=True)
            subprocess.run(g + ["-C", root, "commit", "-q", "--allow-empty", "-m", "x"], check=True)
            for tag in ("v1.0.0", "wip"):
                subprocess.run(g + ["-C", root, "tag", tag], check=True)
            dl = self.dl.collect(root, {})
            self.assertEqual((dl["releases"]["source"], dl["releases"]["count"]), ("tags", 1))
        with tempfile.TemporaryDirectory() as root:  # neither: omitted
            dl = self.dl.collect(root, {}, self.today)
            self.assertIsNone(dl["releases"])
            self.assertNotIn("Releases (", self.dl.render(dl))

    def test_ac5_offline_builder_one_ci_line(self):
        for rel in ("scripts/dashboard.py", "scripts/obs/delivery.py"):
            src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            for word in ("urllib", "socket", "http.client", "requests"):
                self.assertNotIn(word, src, rel)
        d = self.d.collect()
        d["delivery"] = {"ci": self.dl.ci_metrics(self.runs(), self.today), "releases": None}
        self.assertEqual(sum(1 for l in self.d.summary(d).splitlines() if l.startswith("| CI |")), 1)
        d["delivery"] = {"ci": None, "releases": None}
        self.assertEqual(sum(1 for l in self.d.summary(d).splitlines() if l.startswith("| CI |")), 0)

    def test_ac6_repo_resolution_and_validation(self):
        ci = self.ci
        self.assertEqual(ci.parse_repo("git@github.com:o/r.git"), "o/r")
        for bad in ("", "owner", "a/b/c", "a/..", "../x", "a b/c", "o/r?x=1", "o/r;rm", "o/r#f"):
            self.assertFalse(ci.valid_repo(bad), bad)
        self.assertTrue(ci.valid_repo("my-org/my_repo.v2"))
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "metrics", "ci-runs.json")
            saved = (ci.OUT, ci.repo_name, ci.fetch)
            ci.OUT = out
            ci.fetch = lambda repo, page: self.fail("request made")
            try:
                for repo in ("", "../etc/passwd", "o/r?x"):
                    ci.repo_name = lambda argv, repo=repo: repo
                    self.assertEqual(ci.main([]), 1)
                    self.assertFalse(os.path.exists(out))
            finally:
                ci.OUT, ci.repo_name, ci.fetch = saved

    def test_ac7_partial_data_kept(self):
        ci = self.ci
        saved = (ci.OUT, ci.repo_name, ci.fetch)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "metrics", "ci-runs.json")
            ci.OUT, ci.repo_name = out, lambda argv: "o/r"
            try:
                def page2_fails(repo, page):
                    if page == 1:
                        return [self.run_(i, "2026-11-05") for i in range(100)]
                    raise OSError("rate limited")
                ci.fetch = page2_fails
                self.assertEqual(ci.main([]), 0)
                with open(out) as fh:
                    self.assertEqual(len(json.load(fh)["runs"]), 100)
                with open(out) as fh:
                    before = fh.read()

                def page1_fails(repo, page):
                    raise OSError("down")
                ci.fetch = page1_fails
                self.assertEqual(ci.main([]), 1)
                with open(out) as fh:
                    self.assertEqual(fh.read(), before)
            finally:
                ci.OUT, ci.repo_name, ci.fetch = saved

    def test_ac8_table_form_tech_debt(self):
        text = """# Debt
## Open
| Id | Severity | Item | Where | Size | Source | Status |
|---|---|---|---|---|---|---|
| TD-1 | major | Slow `a | b` parse | api | M | audit | open |
| TD-2 | Minor | Escaped \\| pipe | ui | S | retro | open |
| TD-3 | medium | Paid one | db | L | retro | done (2026-01-01) |
- [ ] TD-4 Checklist item — impact: high · effort: S · area: ci
"""
        items = {i["id"]: i for i in self.d.parse_debt(text)}
        self.assertEqual(sorted(items), ["TD-1", "TD-2", "TD-3", "TD-4"])
        self.assertEqual((items["TD-1"]["impact"], items["TD-1"]["effort"], items["TD-1"]["area"], items["TD-1"]["open"]),
                         ("high", "M", "api", True))
        self.assertEqual(items["TD-1"]["title"], "Slow `a | b` parse")
        self.assertEqual((items["TD-2"]["title"], items["TD-2"]["impact"], items["TD-2"]["effort"]), ("Escaped | pipe", "low", "S"))
        self.assertFalse(items["TD-3"]["open"])
        self.assertEqual((items["TD-4"]["impact"], items["TD-4"]["area"], items["TD-4"]["open"]), ("high", "ci", True))

    def test_ac9_escaping(self):
        runs = [self.run_(1, "2026-11-05", "failure", "<img src=x>", 1, "<script>alert(1)</script>")]
        html_ = self.dl.render({"ci": self.dl.ci_metrics(runs, self.today), "releases": None})
        self.assertNotIn("<script>", html_)
        self.assertNotIn("<img", html_)
        self.assertIn("&lt;script&gt;", html_)
        self.assertNotIn("<script", self.dl.render({"ci": None, "releases": None}))

    @unittest.skipUnless(os.path.isfile(os.path.join(ROOT, ".github", "workflows", "ci.yml")),
                         "template CI workflow is not part of an adopted project")
    def test_ac11_workflow(self):
        ci = open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8").read()
        top, jobs = ci.split("jobs:", 1)
        self.assertIn("contents: read", top)
        self.assertNotIn("actions: read", top)
        self.assertIn("actions: read", jobs)
        step = jobs[jobs.index("scripts/ci_runs.py") - 300:jobs.index("scripts/ci_runs.py") + 40]
        self.assertIn("continue-on-error: true", step)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", step)
        self.assertNotIn("${{", step.split("run:")[-1])  # token never inlined in the command
        self.assertIn("metrics/ci-runs.json", open(os.path.join(ROOT, ".gitignore")).read().split())


class AsyncDelivery(unittest.TestCase):
    def test_wait_for_url_live_and_timeout(self):
        import http.server
        import socketserver
        import threading
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "version"), "w") as fh:
            fh.write("abc1234")
        handler_cls = type("Quiet", (http.server.SimpleHTTPRequestHandler,), {
            "log_message": lambda *a: None, "__init__": lambda self, *a, **k:
            http.server.SimpleHTTPRequestHandler.__init__(self, *a, directory=d, **k)})
        srv = socketserver.TCPServer(("127.0.0.1", 0), handler_cls)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = "http://127.0.0.1:%d/version" % srv.server_address[1]
        script = os.path.join(ROOT, "scripts", "wait-for-url.sh")
        env = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
        try:
            ok = subprocess.run(["bash", script, "--url", url, "--expect", "abc1234", "--timeout", "10"],
                                capture_output=True, text=True, env=env)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            self.assertIn("LIVE", ok.stdout)
            late = subprocess.run(["bash", script, "--url", url, "--expect", "zzz", "--timeout", "2"],
                                  capture_output=True, text=True, env=env)
            self.assertEqual(late.returncode, 1)
            self.assertIn("TIMEOUT", late.stdout)
            self.assertIn("--status fail", open(script).read())  # timeouts are recorded as failed deploys
        finally:
            srv.shutdown()
            srv.server_close()

    def _pre_push(self, commands, cap=1):
        repo = tempfile.mkdtemp()
        os.makedirs(os.path.join(repo, ".githooks"))
        subprocess.run(["cp", os.path.join(ROOT, ".githooks", "pre-push"), os.path.join(repo, ".githooks")])
        f = json.load(open(os.path.join(ROOT, "factory.json")))
        f["commands"].update(commands)
        f["budgets"]["affected_test_seconds"] = cap
        with open(os.path.join(repo, "factory.json"), "w") as fh:
            json.dump(f, fh)
        env = {k: v for k, v in os.environ.items() if k != "CI"}
        return subprocess.run(["bash", os.path.join(repo, ".githooks", "pre-push")], capture_output=True,
                              text=True, env=env)

    def test_pre_push_skips_when_unconfigured(self):
        self.assertEqual(self._pre_push({"lint": "", "test_affected": ""}).returncode, 0)

    def test_pre_push_runs_and_caps(self):
        self.assertEqual(self._pre_push({"lint": "true", "test_affected": "echo 2 passed"}).returncode, 0)
        failed = self._pre_push({"lint": "false"})
        self.assertEqual(failed.returncode, 1)
        slow = self._pre_push({"lint": "", "test_affected": "sleep 5"}, cap=1)
        self.assertEqual(slow.returncode, 1)
        self.assertIn("exceeded", slow.stderr)


@template_only
class Bootstrap(unittest.TestCase):
    def test_flag_anywhere_and_readme_swap(self):
        d = os.path.join(tempfile.mkdtemp(), "proj")
        subprocess.run(["cp", "-r", ROOT, d], check=True)
        for extra in (".claude/skills/security-audit", ".claude/skills/cloudflare-deploy"):
            subprocess.run(["rm", "-rf", os.path.join(d, extra)])
        # --codegraph would install software; stub the installer so only parsing is tested
        with open(os.path.join(d, "scripts", "install-codegraph.sh"), "w") as fh:
            fh.write("echo stub-codegraph\n")
        r = subprocess.run(["bash", "scripts/bootstrap.sh", "demo", "A demo app"], cwd=d, capture_output=True, text=True)
        if subprocess.run(["git", "-C", d, "config", "--get", "remote.origin.url"], capture_output=True).returncode == 0:
            self.assertEqual(r.returncode, 2, "refuses in the template repo itself")  # the copy still has the template origin
            subprocess.run(["git", "-C", d, "remote", "remove", "origin"], check=True)
        r = subprocess.run(["bash", "scripts/bootstrap.sh", "demo", "--codegraph", "A demo app"], cwd=d,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        # TD-017: clean records for the new project
        bl = open(os.path.join(d, "docs", "BACKLOG.md")).read()
        self.assertIn("M0", bl)
        self.assertNotIn("## Milestone: M1", bl)
        self.assertEqual(os.listdir(os.path.join(d, "docs", "specs")), ["_TEMPLATE.md"])
        self.assertEqual(sorted(os.listdir(os.path.join(d, "docs", "decisions"))), ["0000-template.md", "0001-use-danfactory-template.md"])
        self.assertNotIn("TD-0", open(os.path.join(d, "docs", "TECH-DEBT.md")).read())
        self.assertNotIn("\n### 20", open(os.path.join(d, "docs", "operating-model", "LEARNINGS.md")).read())
        self.assertEqual(subprocess.run(["python3", "scripts/docs_index.py", "--check"], cwd=d, capture_output=True).returncode, 0)
        self.assertIn("stub-codegraph", r.stdout)
        f = json.load(open(os.path.join(d, "factory.json")))
        self.assertEqual((f["project"]["name"], f["project"]["one_liner"]), ("demo", "A demo app"))
        self.assertTrue(os.path.isfile(os.path.join(d, "docs", "TEMPLATE-GUIDE.md")))
        self.assertIn("# demo", open(os.path.join(d, "README.md")).read())


@template_only
class Adopt(unittest.TestCase):
    """Scan + install into a tiny Lovable-style repo; nothing of the project may be overwritten."""

    def make_repo(self):
        d = tempfile.mkdtemp()
        files = {
            "package.json": json.dumps({"name": "lovable-demo", "scripts": {"dev": "vite", "build": "vite build"},
                                        "dependencies": {"react": "18", "@supabase/supabase-js": "2"},
                                        "devDependencies": {"vite": "5", "lovable-tagger": "1"}}),
            "README.md": "# My Lovable app\n",
            "CLAUDE.md": "# Project rules\n- keep it simple\n",
            ".gitignore": "node_modules\n",
            "src/App.tsx": "export const App = () => null;\n",
            "supabase/migrations/1.sql": "create table a (id int);\n",
        }
        for rel, body in files.items():
            os.makedirs(os.path.dirname(os.path.join(d, rel)) or d, exist_ok=True)
            with open(os.path.join(d, rel), "w") as fh:
                fh.write(body)
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        subprocess.run(["git", "add", "-A"], cwd=d, check=True)
        subprocess.run(["git", "-c", "user.name=gpt-engineer-app[bot]", "-c", "user.email=b@x", "commit", "-qm", "init"],
                       cwd=d, check=True)
        return d

    def test_scan_then_apply(self):
        d = self.make_repo()
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "adopt_scan.py"), "--target", d],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        scan = json.load(open(os.path.join(d, "docs", "adoption-scan.json")))
        self.assertEqual(scan["origin"], "lovable")
        titles = " ".join(f["title"] for f in scan["findings"])
        self.assertIn("Row Level Security", titles)
        self.assertIn("No automated tests", titles)
        dry = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "adopt.py"), "--target", d],
                             capture_output=True, text=True)
        self.assertIn("DRY RUN", dry.stdout)
        self.assertFalse(os.path.exists(os.path.join(d, "factory.json")))  # dry run writes nothing
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "adopt.py"), "--target", d, "--apply"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(open(os.path.join(d, "README.md")).read(), "# My Lovable app\n")
        claude_md = open(os.path.join(d, "CLAUDE.md")).read()
        self.assertTrue(claude_md.startswith("# Project rules"))
        self.assertIn("danfactory:start", claude_md)
        f = json.load(open(os.path.join(d, "factory.json")))
        self.assertEqual((f["project"]["name"], f["adopted"]["from"], f["commands"]["build"]),
                         ("lovable-demo", "lovable", "npm run build"))
        self.assertIn("Row Level Security", open(os.path.join(d, "docs", "TECH-DEBT.md")).read())
        self.assertIn("node_modules", open(os.path.join(d, ".gitignore")).read())
        subprocess.run([sys.executable, "scripts/docs_index.py", "--quiet"], cwd=d, check=True)
        chk = subprocess.run(["bash", "scripts/check.sh"], cwd=d, capture_output=True, text=True)
        self.assertEqual(chk.returncode, 0, chk.stdout[-800:] + chk.stderr[-800:])


class ShortContexts(unittest.TestCase):
    def transcript(self, ctx_tokens):
        path = os.path.join(tempfile.mkdtemp(), "t.jsonl")
        with open(path, "w") as fh:
            fh.write(json.dumps({"type": "assistant", "message": {"id": "1", "usage": {
                "input_tokens": 10, "cache_read_input_tokens": ctx_tokens - 10, "cache_creation_input_tokens": 0,
                "output_tokens": 5}}}) + "\n")
        return path

    def test_context_watch_nudges_once_per_band(self):
        sid = "test-%d" % os.getpid()
        big = {"transcript_path": self.transcript(200000), "session_id": sid}
        first = hook("context_watch.py", big)
        self.assertIn("handoff", first.stdout)
        self.assertEqual(hook("context_watch.py", big).stdout, "")  # same band: no nagging
        small = {"transcript_path": self.transcript(30000), "session_id": sid + "x"}
        self.assertEqual(hook("context_watch.py", small).stdout, "")
        sdir = os.path.join(tempfile.gettempdir(), "danfactory-%d" % (os.getuid() if hasattr(os, "getuid") else 0))
        for s in (sid, sid + "x"):
            p = os.path.join(sdir, "ctx-%s" % s)
            if os.path.exists(p):
                os.remove(p)

    def state_file(self, sid):
        uid = os.getuid() if hasattr(os, "getuid") else 0
        return os.path.join(tempfile.gettempdir(), "danfactory-%d" % uid, "ctx-%s" % sid)

    def test_context_watch_says_keep_working_not_clear(self):
        sid = "test-keep-%d" % os.getpid()
        out = hook("context_watch.py", {"transcript_path": self.transcript(200000), "session_id": sid}).stdout
        self.assertIn(".factory/HANDOFF.md", out)
        self.assertIn("keep working", out)
        self.assertIn("never mid-debug", out)
        self.assertIn("Do not ask the user to /clear", out)
        self.assertNotIn("ask the user to /clear.", out)
        os.remove(self.state_file(sid))

    def test_context_watch_rearms_after_compaction(self):
        sid = "test-rearm-%d" % os.getpid()
        big = {"transcript_path": self.transcript(200000), "session_id": sid}
        self.assertIn("handoff", hook("context_watch.py", big).stdout)
        self.assertTrue(os.path.exists(self.state_file(sid)))
        # compaction: context drops under the budget, so the band state resets
        self.assertEqual(hook("context_watch.py", {"transcript_path": self.transcript(30000),
                                                   "session_id": sid}).stdout, "")
        self.assertFalse(os.path.exists(self.state_file(sid)))
        self.assertIn("handoff", hook("context_watch.py", big).stdout)  # grows again: nudged again
        os.remove(self.state_file(sid))

    def project_copy(self):
        d = os.path.join(tempfile.mkdtemp(), "proj")
        subprocess.run(["cp", "-r", ROOT, d], check=True)
        if os.path.isfile(os.path.join(d, ".git")):  # a git worktree's .git is a pointer: the copy would commit into the original branch
            os.remove(os.path.join(d, ".git"))
            git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
            subprocess.run(["git", "init", "-q"], cwd=d, check=True)
            subprocess.run(["git", "add", "-A"], cwd=d, check=True, capture_output=True)
            subprocess.run(git + ["commit", "-q", "--no-verify", "-m", "snapshot"], cwd=d, check=True, capture_output=True)
        env = dict(os.environ, CLAUDE_PROJECT_DIR=d)
        return d, os.path.join(d, ".claude", "hooks"), env, os.path.join(d, ".factory", "HANDOFF.md")

    def run_hook(self, hooks, name, stdin, env):
        return subprocess.run([sys.executable, os.path.join(hooks, name)], input=stdin,
                              text=True, capture_output=True, env=env)

    def test_pre_compact_snapshot_and_session_reload(self):
        d, hooks, env, note = self.project_copy()
        with open(note, "w") as fh:
            fh.write("# Handoff — test\n\n## Task\nShip the login page\n")
        for _ in range(2):  # second run must replace, not append, the snapshot
            r = self.run_hook(hooks, "pre_compact.py", '{"trigger":"auto"}', env)
            self.assertEqual(r.returncode, 0, r.stderr)
        text = open(note).read()
        self.assertEqual(text.count("auto-snapshot:start"), 1)
        self.assertIn("Ship the login page", text)
        out = self.run_hook(hooks, "session_start.py", '{"source":"clear"}', env).stdout
        self.assertIn("loaded on clear", out)
        self.assertIn("Ship the login page", out)
        self.assertNotIn("compacted automatically", out)

    def test_pre_compact_prints_summary_instructions(self):
        d, hooks, env, note = self.project_copy()
        with open(note, "w") as fh:
            fh.write("# Handoff — test\n\n## Task\nShip the login page\n")
        r = self.run_hook(hooks, "pre_compact.py", '{"trigger":"manual"}', env)
        self.assertEqual(r.returncode, 0, r.stderr)
        for keep in ("goal and open questions", "decisions and their reasons", "commit shas",
                     "current step and the next steps", "failed approaches", "Drop: file contents, tool output, logs",
                     "Source of truth: .factory/HANDOFF.md"):
            self.assertIn(keep, r.stdout)
        self.assertLessEqual(len(r.stdout), 10000)
        self.assertNotIn("missing", r.stdout)  # fresh, uncommitted note newer than HEAD
        self.assertNotIn("older than the last commit", r.stdout)

    def test_pre_compact_flags_missing_note(self):
        d, hooks, env, note = self.project_copy()
        if os.path.exists(note):
            os.remove(note)
        r = self.run_hook(hooks, "pre_compact.py", '{"trigger":"auto"}', env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("missing or empty", r.stdout)
        # the snapshot-only note it created is still "missing" next time
        self.assertIn("missing or empty", self.run_hook(hooks, "pre_compact.py", '{"trigger":"auto"}', env).stdout)

    def test_pre_compact_flags_stale_note_and_accepts_committed_note(self):
        d, hooks, env, note = self.project_copy()
        with open(note, "w") as fh:
            fh.write("# Handoff — test\n\n## Task\nShip the login page\n")
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run(git + ["commit", "-q", "--no-verify", "--allow-empty", "-m", "chore: unrelated"], cwd=d,
                       check=True, capture_output=True)  # HEAD must not be a commit that touched the note
        head_time = int(subprocess.run(["git", "log", "-1", "--format=%ct"], cwd=d, capture_output=True,
                                       text=True, check=True).stdout.strip())
        os.utime(note, (head_time - 3600, head_time - 3600))
        r = self.run_hook(hooks, "pre_compact.py", '{"trigger":"auto"}', env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("older than the last commit", r.stdout)
        self.assertLess(os.path.getmtime(note), head_time)  # the snapshot keeps the note's mtime
        subprocess.run(git + ["add", "-f", note], cwd=d, check=True, capture_output=True)
        subprocess.run(git + ["commit", "-q", "--no-verify", "-m", "chore: handoff"], cwd=d, check=True,
                       capture_output=True)
        os.utime(note, (head_time - 3600, head_time - 3600))
        r = self.run_hook(hooks, "pre_compact.py", '{"trigger":"auto"}', env)
        self.assertNotIn("older than the last commit", r.stdout)

    def test_pre_compact_never_blocks(self):
        d = tempfile.mkdtemp()  # not a git repo, no factory.json, garbage input
        r = subprocess.run([sys.executable, os.path.join(HOOKS, "pre_compact.py")], input="not json",
                           text=True, capture_output=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=d))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Compaction instructions", r.stdout)

    @unittest.skipUnless(hasattr(os, "symlink"), "needs symlinks")
    def test_pre_compact_does_not_write_through_symlink(self):
        d, hooks, env, note = self.project_copy()
        target = os.path.join(tempfile.mkdtemp(), "victim.txt")
        with open(target, "w") as fh:
            fh.write("keep me")
        if os.path.exists(note):
            os.remove(note)
        os.symlink(target, note)
        r = self.run_hook(hooks, "pre_compact.py", '{"trigger":"auto"}', env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(open(target).read(), "keep me")

    def test_session_start_after_compaction_continues_from_note(self):
        d, hooks, env, note = self.project_copy()
        with open(note, "w") as fh:
            fh.write("# Handoff — test\n\n## Task\nShip the login page\n")
        out = self.run_hook(hooks, "session_start.py", '{"source":"compact"}', env).stdout
        self.assertIn("Context was compacted automatically; continue the task from this note; "
                      "user gates still apply.", out)
        self.assertIn("Ship the login page", out)
        self.assertNotIn("compacted automatically", self.run_hook(hooks, "session_start.py",
                                                                 '{"source":"startup"}', env).stdout)
        os.remove(note)
        out = self.run_hook(hooks, "session_start.py", '{"source":"compact"}', env).stdout
        self.assertIn("compacted automatically", out)
        self.assertIn("user gates still apply", out)

    def test_session_start_compact_line_in_template_mode(self):
        d, hooks, env, note = self.project_copy()
        src = json.load(open(os.path.join(d, "factory.json")))["template"]["source_repo"]
        url = "https://github.com/%s.git" % src
        if subprocess.run(["git", "remote", "get-url", "origin"], cwd=d, capture_output=True).returncode == 0:
            subprocess.run(["git", "remote", "set-url", "origin", url], cwd=d, check=True)
        else:
            subprocess.run(["git", "remote", "add", "origin", url], cwd=d, check=True)
        with open(note, "w") as fh:
            fh.write("# Handoff — test\n\n## Task\nShip the login page\n")
        out = self.run_hook(hooks, "session_start.py", '{"source":"compact"}', env).stdout
        self.assertIn("TEMPLATE repo", out)
        self.assertIn("Context was compacted automatically; continue the task from this note; "
                      "user gates still apply.", out)
        self.assertIn("Ship the login page", out)
        self.assertNotIn("compacted automatically", self.run_hook(hooks, "session_start.py",
                                                                 '{"source":"startup"}', env).stdout)

    def test_settings_matchers_cover_compaction(self):
        hooks_cfg = json.load(open(os.path.join(ROOT, ".claude", "settings.json")))["hooks"]
        start = set(hooks_cfg["SessionStart"][0]["matcher"].split("|"))
        self.assertTrue({"startup", "resume", "clear", "compact"} <= start)
        self.assertEqual(set(hooks_cfg["PreCompact"][0]["matcher"].split("|")), {"manual", "auto"})


class CloudflareScaffold(unittest.TestCase):
    def scaffold(self, files, *flags):
        d = os.path.join(tempfile.mkdtemp(), "proj")
        os.makedirs(os.path.join(d, "scripts"))
        os.makedirs(os.path.join(d, "templates"))
        subprocess.run(["cp", os.path.join(ROOT, "scripts", "cf_scaffold.py"), os.path.join(d, "scripts")], check=True)
        subprocess.run(["cp", os.path.join(ROOT, "templates", "deploy-cloudflare.yml"), os.path.join(d, "templates")], check=True)
        f = json.load(open(os.path.join(ROOT, "factory.json")))
        f["project"]["name"] = "My Cool App"
        files = dict(files, **{"factory.json": json.dumps(f)})
        for rel, body in files.items():
            with open(os.path.join(d, rel), "w") as fh:
                fh.write(body)
        r = subprocess.run([sys.executable, "scripts/cf_scaffold.py", "--no-lock", *flags], cwd=d, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return d

    def config(self, d):
        text = open(os.path.join(d, "wrangler.jsonc")).read()
        return json.loads(text[text.index("{"):])

    def test_vite_spa(self):
        d = self.scaffold({"package.json": json.dumps({"name": "x", "devDependencies": {"vite": "5"}})})
        c = self.config(d)
        self.assertEqual(c["name"], "my-cool-app")
        self.assertEqual(c["assets"]["directory"], "./dist")
        self.assertEqual(c["assets"]["not_found_handling"], "single-page-application")
        self.assertIn("/version", c["assets"]["run_worker_first"])
        self.assertIn("/version", open(os.path.join(d, "worker", "index.ts")).read())
        dep = json.load(open(os.path.join(d, "factory.json")))["integrations"]["deploy"]
        self.assertEqual(dep["worker_name"], "my-cool-app")
        self.assertEqual(dep["route"], "A-dashboard-git")

    def test_default_is_route_a_without_workflow(self):
        d = self.scaffold({})
        self.assertFalse(os.path.exists(os.path.join(d, ".github", "workflows", "deploy-cloudflare.yml")))

    def test_route_b_is_opt_in(self):
        d = self.scaffold({}, "--route-b")
        self.assertTrue(os.path.isfile(os.path.join(d, ".github", "workflows", "deploy-cloudflare.yml")))
        self.assertEqual(json.load(open(os.path.join(d, "factory.json")))["integrations"]["deploy"]["route"], "B-github-actions")

    def test_bare_project_and_idempotent(self):
        d = self.scaffold({})
        self.assertEqual(self.config(d)["assets"]["directory"], "./public")
        self.assertTrue(os.path.isfile(os.path.join(d, "public", "index.html")))
        self.assertIn("wrangler", open(os.path.join(d, "package.json")).read())
        r = subprocess.run([sys.executable, "scripts/cf_scaffold.py", "--no-lock"], cwd=d, capture_output=True, text=True)
        self.assertIn("keep    wrangler.jsonc", r.stdout)  # second run never overwrites


class Config(unittest.TestCase):
    def test_prd_gate_is_wired(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "docs/specs/_TEMPLATE.md")))
        for path in ("CLAUDE.md", ".claude/agents/developer.md", "docs/operating-model/AGENT-ROUTING.md"):
            self.assertIn("prd-approval.md", open(os.path.join(ROOT, path), encoding="utf-8").read(), path)

    def test_settings_reference_existing_hooks(self):
        s = json.load(open(os.path.join(ROOT, ".claude", "settings.json")))
        for groups in s["hooks"].values():
            for g in groups:
                for h in g["hooks"]:
                    script = h["command"].split('"')[1].replace("$CLAUDE_PROJECT_DIR", ROOT)
                    self.assertTrue(os.path.isfile(script), script)

    def test_every_path_in_tree_has_a_playbook(self):
        tree = open(os.path.join(ROOT, "docs", "operating-model", "DECISION-TREE.md")).read()
        for p in os.listdir(os.path.join(ROOT, "docs", "operating-model", "paths")):
            self.assertIn("paths/" + p, tree)

    def test_agents_are_consistent_with_routing(self):
        import re
        d = os.path.join(ROOT, ".claude", "agents")
        names = set()
        for fn in os.listdir(d):
            if not fn.endswith(".md"):
                continue
            with open(os.path.join(d, fn), encoding="utf-8") as fh:
                head = fh.read().split("---")[1]
            meta = dict(l.split(":", 1) for l in head.strip().splitlines() if ":" in l)
            name = meta["name"].strip()
            self.assertEqual(name + ".md", fn)
            self.assertIn(meta.get("model", " inherit").strip(), {"haiku", "sonnet", "opus", "inherit"}, fn)
            self.assertLess(len(meta["description"]), 400, "keep descriptions short (loaded every session): " + fn)
            names.add(name)
        with open(os.path.join(ROOT, "docs", "operating-model", "AGENT-ROUTING.md"), encoding="utf-8") as fh:
            routing = fh.read()
        present = set(names)
        for pf in glob.glob(os.path.join(ROOT, "packs", "*.json")):  # an agent of a pack that is not installed may still be routed (ADR 0011)
            with open(pf, encoding="utf-8") as fh:
                names |= {os.path.basename(x)[:-3] for x in json.load(fh)["files"] if x.startswith(".claude/agents/") and x.endswith(".md")}
        for n in present:
            self.assertIn(n, routing, "agent missing from AGENT-ROUTING.md: " + n)
        for n in set(re.findall(r"`([a-z][a-z-]+)`", routing)):
            skills = set(os.listdir(os.path.join(ROOT, ".claude", "skills")))
            if os.path.isdir(os.path.join(ROOT, "plugin", "skills")):
                skills |= set(os.listdir(os.path.join(ROOT, "plugin", "skills")))
            if n in skills:
                continue
            self.assertIn(n, names, "routing names unknown agent: " + n)
        rosters = routing.split("## Path rosters")[1].split("##")[0]
        for row in rosters.splitlines():
            if row.startswith("| ") and not row.startswith("| Path") and "," in row:
                for n in row.split("|")[2].split(","):
                    self.assertIn(n.strip(), names, "roster names unknown agent: " + n)

    def test_skills_have_frontmatter(self):
        d = os.path.join(ROOT, ".claude", "skills")
        tracked = subprocess.run(["git", "ls-files", "--", ".claude/skills"], cwd=ROOT,
                                 capture_output=True, text=True).stdout
        for name in os.listdir(d):
            if ".claude/skills/%s/" % name not in tracked and os.path.isfile(os.path.join(ROOT, ".gitignore")) \
                    and subprocess.run(["git", "check-ignore", "-q", ".claude/skills/" + name], cwd=ROOT).returncode == 0:
                continue  # on-demand external skill
            body = open(os.path.join(d, name, "SKILL.md")).read()
            self.assertTrue(body.startswith("---\nname: " + name + "\n"), name)


if __name__ == "__main__":
    unittest.main()
