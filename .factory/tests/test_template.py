"""Self-tests for danfactory hooks and scripts (stdlib unittest)."""
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
        hook("record_tokens.py", {"transcript_path": main_t, "session_id": "x"})
        self.assertEqual(os.path.exists(os.path.join(ROOT, "metrics", "tokens.jsonl")), before)

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
- [x] Login works #value
- [ ] Set up CI (S) #ci
- [-] Dropped idea
- [ ] Share a list
## Milestone: M2
- [~] Split storage layer #arch
- [ ] Export to CSV #feature
""")
        debt = [{"id": "TD-001", "title": "No retries", "impact": "high", "effort": "S"}]
        rm = self.d.roadmap(ms, debt)
        cols = rm["columns"]
        self.assertEqual([c["name"] for c in cols], ["M1", "M2", "Tech debt to schedule"])
        lane = lambda i, k: [(x["title"], x["seq"]) for x in cols[i]["lanes"][k]]
        self.assertEqual(lane(0, "value"), [("Login works", None), ("Share a list", 1)])
        self.assertEqual(lane(0, "foundation"), [("Set up CI", 1)])
        self.assertEqual(lane(1, "foundation"), [("Split storage layer", 2)])
        self.assertEqual(lane(1, "value"), [("Export to CSV", 2)])
        self.assertEqual(lane(2, "foundation"), [("TD-001 No retries", 3)])
        self.assertEqual(rm["open"], {"value": 2, "foundation": 3})
        html = self.d.render_roadmap(rm)
        self.assertIn("Technical foundation", html)
        self.assertIn("Value-driven features", html)

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
        r = subprocess.run(["bash", "scripts/bootstrap.sh", "demo", "--codegraph", "A demo app"], cwd=d,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
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
        os.remove(os.path.join(tempfile.gettempdir(), "danfactory-ctx-%s" % sid))

    def test_pre_compact_snapshot_and_session_reload(self):
        d = os.path.join(tempfile.mkdtemp(), "proj")
        subprocess.run(["cp", "-r", ROOT, d], check=True)
        hooks = os.path.join(d, ".claude", "hooks")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=d)
        note = os.path.join(d, ".factory", "HANDOFF.md")
        with open(note, "w") as fh:
            fh.write("# Handoff — test\n\n## Task\nShip the login page\n")
        for _ in range(2):  # second run must replace, not append, the snapshot
            subprocess.run([sys.executable, os.path.join(hooks, "pre_compact.py")], input='{"trigger":"auto"}',
                           text=True, env=env, check=True)
        text = open(note).read()
        self.assertEqual(text.count("auto-snapshot:start"), 1)
        self.assertIn("Ship the login page", text)
        out = subprocess.run([sys.executable, os.path.join(hooks, "session_start.py")], input='{"source":"clear"}',
                             text=True, capture_output=True, env=env).stdout
        self.assertIn("loaded on clear", out)
        self.assertIn("Ship the login page", out)


class CloudflareScaffold(unittest.TestCase):
    def scaffold(self, files):
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
        r = subprocess.run([sys.executable, "scripts/cf_scaffold.py", "--no-lock"], cwd=d, capture_output=True, text=True)
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
        self.assertTrue(os.path.isfile(os.path.join(d, ".github", "workflows", "deploy-cloudflare.yml")))
        self.assertEqual(json.load(open(os.path.join(d, "factory.json")))["integrations"]["deploy"]["worker_name"], "my-cool-app")

    def test_bare_project_and_idempotent(self):
        d = self.scaffold({})
        self.assertEqual(self.config(d)["assets"]["directory"], "./public")
        self.assertTrue(os.path.isfile(os.path.join(d, "public", "index.html")))
        self.assertIn("wrangler", open(os.path.join(d, "package.json")).read())
        r = subprocess.run([sys.executable, "scripts/cf_scaffold.py", "--no-lock"], cwd=d, capture_output=True, text=True)
        self.assertIn("keep    wrangler.jsonc", r.stdout)  # second run never overwrites


class Config(unittest.TestCase):
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
        for n in names:
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
