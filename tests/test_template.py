"""Self-tests for danfactory hooks and scripts (stdlib unittest)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HOOKS = os.path.join(ROOT, ".claude", "hooks")


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
        self.assertEqual(self.bash("cat small.txt").returncode, 0)
        self.assertEqual(self.bash("git status").returncode, 0)


class RecordTokens(unittest.TestCase):
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

    def test_build_writes_artefacts(self):
        d = self.d.build()
        for name in ("index.html", "data.json", "SUMMARY.md"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "dashboard", name)), name)
        page = open(os.path.join(ROOT, "dashboard", "index.html"), encoding="utf-8").read()
        self.assertIn("<title>", page)
        self.assertIn("prefers-color-scheme: dark", page)
        self.assertIn("progress", d)


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
