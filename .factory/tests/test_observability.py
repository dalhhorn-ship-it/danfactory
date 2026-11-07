"""Observability tabs (scripts/obs): pure-function unit tests plus one temporary git repo for the chain."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import dashboard  # noqa: E402
from obs import model, sources, svg, tab_architecture, tab_decisions, tab_docs, tab_gates, tab_traceability, trace  # noqa: E402

FILES = {
    "factory.json": '{"project": {"name": "demo"}}',
    "docs/GOAL.md": "# Goal\n\n## Outcome\nShoppers pay online.\n\n## Users\n_x_\n",
    "docs/specs/demo-prd.md": "# PRD: Demo\n\n> Status: approved · 2026-11-07 · by user · Owner: pm · Backlog: M1 — Demo\n\n"
                              "## Acceptance criteria\n1. one\n2. two\n\n## Risks\n",
    "docs/specs/orphan.md": "# PRD: Orphan\n\n> Status: approved · Owner: pm · Backlog: M9 — Nowhere\n",
    "docs/specs/_TEMPLATE.md": "# PRD: <title>\n",
    "docs/decisions/0001-use-a.md": "# 0001 — Use A\n\n> Status: accepted · Date: 2026-11-07\n\nEntry is src/a.ts.\n",
    "docs/BACKLOG.md": "## Milestone: M1 — Demo\n- [x] DEM-1 Build it (S)\n- [x] DEM-2 Forgotten thing\n- [ ] Idea without id\n",
    "src/a.ts": 'import { b } from "./b";\nexport default { fetch(r, env) { return env.DB.prepare("select * from users"); } };\n',
    "src/b.ts": "export const b = 1;\n",
    "src/c.ts": "export const c = 2;\n",
    "tests/a.test.ts": "test('a', () => {});\n",
    "migrations/001.sql": "CREATE TABLE IF NOT EXISTS users (id INTEGER);\n",
    "wrangler.jsonc": '{\n // comment\n "name": "demo-worker", "main": "src/a.ts", /* block */\n'
                      ' "vars": {"URL": "http://x//y"},\n "d1_databases": [{"binding": "DB", "database_id": "secret"},],\n'
                      ' "kv_namespaces": [{"binding": "CACHE", "id": "secret"}],\n}\n',
}


def sh(root, *args):
    subprocess.run(args, cwd=root, check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))


def put(root, rel, text):
    os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
    with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
        fh.write(text)


class Units(unittest.TestCase):
    def test_wrangler_jsonc_comments_commas_and_no_secrets(self):
        w = sources.parse_wrangler(FILES["wrangler.jsonc"])
        self.assertEqual((w["name"], w["main"]), ("demo-worker", "src/a.ts"))
        self.assertEqual([(b["name"], b["kind"]) for b in w["bindings"]], [("CACHE", "kv_namespaces"), ("DB", "d1_databases")])
        self.assertNotIn("secret", json.dumps(w))
        self.assertIsNone(sources.parse_wrangler("{not json"))

    @unittest.skipUnless(sources.tomllib, "tomllib needs python 3.11+")
    def test_wrangler_toml(self):
        w = sources.parse_wrangler('name = "w"\nmain = "src/i.ts"\n[[r2_buckets]]\nbinding = "FILES"\nbucket_name = "x"\n', toml=True)
        self.assertEqual(w["bindings"], [{"name": "FILES", "kind": "r2_buckets"}])

    def test_headers_ids_and_refs(self):
        p = sources.parse_prd(FILES["docs/specs/demo-prd.md"], "demo-prd")
        self.assertEqual((p["title"], p["status"], p["approved"], p["backlog"], p["ac"]), ("Demo", "approved", "2026-11-07", "M1 — Demo", 2))
        self.assertIsNone(sources.parse_prd("# Design: x\n"))
        a = sources.parse_adr(FILES["docs/decisions/0001-use-a.md"], "0001")
        self.assertEqual((a["title"], a["status"]), ("Use A", "accepted"))
        self.assertEqual(sources.ID_RE.match("OBS-12 Title").group(1), "OBS-12")
        self.assertIsNone(sources.ID_RE.match("Slice 1"))
        self.assertEqual(trace.ref_keys("feat\n\nRefs: OBS-1, slug-x\nCo-Authored-By: x"), {"OBS-1", "slug-x"})
        self.assertTrue(sources.is_test("src/a.test.ts") and sources.is_test("tests/x.py") and not sources.is_test("src/a.ts"))

    def test_svg_deterministic_escaped_capped(self):
        els = [{"id": "app:%02d" % i, "type": "application-component", "name": "<script>%d" % i + "x" * 30, "drift": i == 0}
               for i in range(30)]
        layers = {"motivation": [], "application": els, "technology": []}
        out = svg.render(layers, [], {"motivation": "nothing yet"})
        self.assertEqual(out, svg.render(layers, [], {"motivation": "nothing yet"}))
        self.assertNotIn("<script>", out)
        self.assertIn("+6 more", out)
        self.assertIn("nothing yet", out)
        self.assertIn('class="am-app box drift"', out)
        self.assertIn('role="img"', out)

    def test_empty_states(self):
        root = tempfile.mkdtemp()
        arch = model.view(root)
        html = tab_architecture.render(arch)
        self.assertIn("No architecture yet", html)
        self.assertIn("wrangler.jsonc/toml", html)
        self.assertIn("No intent modelled yet", html)
        tr = trace.build(root, {}, arch)
        self.assertIn("No PRDs yet", tab_traceability.render(tr))
        self.assertIn("0 PRDs", tab_traceability.line(tr))
        self.assertIn("drift 0", tab_architecture.line(arch))


class Repo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = r = tempfile.mkdtemp()
        sh(r, "git", "init", "-q")
        for rel in ("factory.json", "docs/GOAL.md", "docs/specs/demo-prd.md", "docs/specs/orphan.md", "docs/specs/_TEMPLATE.md",
                    "docs/decisions/0001-use-a.md", "docs/BACKLOG.md"):
            put(r, rel, FILES[rel])
        sh(r, "git", "add", "-A")
        sh(r, "git", "commit", "-qm", "docs: start")
        for rel in ("src/a.ts", "src/b.ts", "src/c.ts", "tests/a.test.ts", "migrations/001.sql", "wrangler.jsonc"):
            put(r, rel, FILES[rel])
        sh(r, "git", "add", "-A")
        sh(r, "git", "commit", "-qm", "feat: a and b\n\nRefs: DEM-1")
        sh(r, "git", "tag", "v0.1.0")
        put(r, "docs/note.md", "later\n")
        sh(r, "git", "add", "-A")
        sh(r, "git", "commit", "-qm", "chore: later, no refs")
        cls.arch = model.view(r)

    def test_layers_relations_and_secrets(self):
        ids = {x["id"] for els in self.arch["layers"].values() for x in els}
        self.assertTrue({"goal:outcome", "req:demo-prd", "req:orphan", "adr:0001", "app:src/a.ts", "if:http", "data:users",
                         "node:demo-worker", "svc:DB", "svc:CACHE"} <= ids, ids)
        rels = {(r["type"], r["source"], r["target"]) for r in self.arch["relations"]}
        for r in (("realization", "req:demo-prd", "goal:outcome"), ("serving", "app:src/b.ts", "app:src/a.ts"),
                  ("influence", "adr:0001", "app:src/a.ts"), ("access", "app:src/a.ts", "data:users"),
                  ("serving", "svc:DB", "app:src/a.ts"), ("assignment", "node:demo-worker", "app:src/a.ts")):
            self.assertIn(r, rels)
        self.assertNotIn("secret", json.dumps(self.arch))
        self.assertEqual(self.arch["drift"]["unused_bindings"], ["svc:CACHE"])
        self.assertFalse(self.arch["drift"]["intent_modelled"])

    def test_drift_both_directions_and_deterministic_write(self):
        r = tempfile.mkdtemp()
        sh(r, "cp", "-r", self.root + "/.", r)
        self.assertTrue(model.write(r))
        first = open(os.path.join(r, model.MODEL_FILE), "rb").read()
        self.assertFalse(model.write(r))
        self.assertEqual(first, open(os.path.join(r, model.MODEL_FILE), "rb").read())
        m = json.loads(first)
        m["curated"]["elements"] = [
            {"id": "app:ghost", "type": "application-component", "name": "Ghost", "path": "src/ghost"},
            {"id": "app:entry", "type": "application-component", "name": "Entry", "path": "src/a.ts"}]
        put(r, model.MODEL_FILE, json.dumps(m))
        model.write(r)
        self.assertEqual(json.loads(open(os.path.join(r, model.MODEL_FILE)).read())["curated"]["elements"], m["curated"]["elements"])
        v = model.view(r)
        self.assertEqual(v["drift"]["designed_not_built"], ["app:ghost"])
        self.assertEqual(v["drift"]["built_not_designed"], ["app:src/b.ts", "app:src/c.ts"])
        entry = next(x for x in v["layers"]["application"] if x["id"] == "app:src/a.ts")
        self.assertEqual((entry["name"], entry["origin"]), ("Entry", "both"))
        self.assertFalse(v["drift"]["model_stale"])
        put(r, "src/d.ts", "export {}\n")
        self.assertTrue(model.view(r)["drift"]["model_stale"])
        self.assertIn("Built, not designed", tab_architecture.render(v))

    def test_traceability_chain_and_broken_links(self):
        backlog = dashboard.parse_backlog(FILES["docs/BACKLOG.md"])
        t = trace.build(self.root, {"progress": {"milestones": backlog}}, self.arch)
        chain = next(c for c in t["chains"] if c["prd"]["slug"] == "demo-prd")
        it = {i["id"]: i for i in chain["items"]}
        d1 = it["DEM-1"]
        self.assertEqual([c["subject"] for c in d1["commits"]], ["feat: a and b"])
        self.assertEqual(d1["components"], ["src/a.ts", "src/b.ts", "src/c.ts"])
        self.assertEqual((d1["tests"], d1["version"], d1["broken"]), (["tests/a.test.ts"], "v0.1.0", []))
        self.assertEqual(it["DEM-2"]["broken"], ["done, no commits"])
        self.assertIn("no ID or slug refs", it[""]["broken"])
        orphan = next(c for c in t["chains"] if c["prd"]["slug"] == "orphan")
        self.assertEqual(orphan["broken"], ["no items", "approved without date"])
        self.assertEqual((t["commits"], t["linked_commit_pct"], t["goal"]), (3, 33, True))
        html = tab_traceability.render(t)
        self.assertIn("DEM-1", html)
        self.assertIn("done, no commits", html)
        self.assertIn("2 PRDs", tab_traceability.line(t))


class Slice2(unittest.TestCase):
    def test_empty_states(self):
        root = tempfile.mkdtemp()
        base = {"architecture": model.view(root)}
        dec, gates, docs = (m.collect(root, base) for m in (tab_decisions, tab_gates, tab_docs))
        self.assertIn("No ADRs yet", tab_decisions.render(dec))
        self.assertIn("No backlog items yet", tab_gates.render(gates))
        self.assertIn("No docs graph yet", tab_docs.render(docs))
        self.assertIn("no ADRs yet", tab_decisions.line(dec))
        self.assertIn("not recorded yet", tab_gates.line(gates))
        self.assertIn("no docs graph", tab_docs.line(docs))

    def test_adr_chain_and_components(self):
        adr = lambda n, st, extra="": sources.parse_adr("# %s — T%s\n\n> Status: %s · Date: 2026-01-0%s%s\n" % (n, n, st, n[-1], extra), n)  # noqa: E731
        rows = [tab_decisions.parse(a) for a in (adr("0001", "superseded by 0002"), adr("0002", "accepted", " · Supersedes: 0001"),
                                                 adr("0003", "accepted", " · Supersedes: 0002"), adr("0004", "accepted"))]
        self.assertEqual(tab_decisions.chains(rows), [["0001", "0002", "0003"]])
        self.assertEqual(rows[1]["supersedes"], ["0001"])
        self.assertEqual(rows[0]["superseded_by"], "0002")
        self.assertEqual(rows[0]["date"], "2026-01-01")

    def test_decisions_repo_components(self):
        r = tempfile.mkdtemp()
        put(r, "docs/decisions/0001-a.md", "# 0001 — A\n\n> Status: superseded by 0002 · Date: 2026-01-01\n\nsrc/a.ts\n")
        put(r, "docs/decisions/0002-b.md", "# 0002 — B\n\n> Status: accepted · Date: 2026-02-01\nSupersedes: 0001\n\nsrc/a.ts\n")
        put(r, "src/a.ts", "export const a = 1;\n")
        d = tab_decisions.collect(r, {"architecture": model.view(r)})
        self.assertEqual(d["chains"], [["0001", "0002"]])
        self.assertEqual(d["adrs"][1]["components"], ["src/a.ts"])
        html = tab_decisions.render(d)
        self.assertIn("0001 → 0002", html)
        self.assertIn("src/a.ts", html)
        self.assertIn("1 supersedes chains", tab_decisions.line(d))

    def test_docs_health_matches_graph(self):
        r = tempfile.mkdtemp()
        sh(r, "git", "init", "-q")
        put(r, "docs/a.md", "# A\nSee docs/b.md and src/a.ts\n")
        put(r, "docs/b.md", "# B\n")
        put(r, "docs/lonely.md", "# L\n")
        put(r, "src/a.ts", "export const a = 1;\n")
        put(r, "src/b.ts", "export const b = 1;\n")
        graph = {"nodes": [{"id": i} for i in ("docs/a.md", "docs/b.md", "docs/lonely.md", "docs/INDEX.md")],
                 "edges": [{"from": "docs/a.md", "to": "docs/b.md"}]}
        put(r, "docs/knowledge-graph.json", json.dumps(graph))
        put(r, "docs/INDEX.md", "# I\n")
        sh(r, "git", "add", "-A")
        sh(r, "git", "commit", "-qm", "one", "--date=2020-01-01T00:00:00")
        put(r, "src/a.ts", "export const a = 2;\n")
        sh(r, "git", "add", "-A")
        sh(r, "git", "commit", "-qm", "two", "--date=2020-01-02T00:00:00")
        # force the doc to be older than the code it names
        sh(r, "git", "commit", "-q", "--allow-empty", "-m", "three")
        times = sources.commit_times(r)
        times["docs/a.md"] = times["src/a.ts"] - 100
        self.assertEqual([s["doc"] for s in tab_docs.stale_docs(r, graph["nodes"], times)], ["docs/a.md"])
        d = tab_docs.collect(r, {"architecture": model.view(r)})
        self.assertEqual(d["orphans"], ["docs/lonely.md"])
        self.assertEqual((d["nodes"], d["edges"]), (4, 1))
        self.assertEqual(d["uncovered"], ["src/b.ts"])  # src/a.ts is named in docs/a.md
        html = tab_docs.render(d)
        self.assertIn("docs/lonely.md", html)
        self.assertIn("Orphan docs (1)", html)
        self.assertIn("1 orphan", tab_docs.line(d))

    def test_gates_records_prd_and_deps(self):
        r = tempfile.mkdtemp()
        sh(r, "git", "init", "-q")
        put(r, "package.json", "{}")
        put(r, "src/alpha.ts", "x\n")
        put(r, "tests/alpha.test.ts", "x\n")
        put(r, "src/beta.ts", "x\n")
        put(r, "metrics/records.jsonl", json.dumps({"ts": "2026-11-01T10:00:00+00:00", "kind": "check", "sha": "abc"}) + "\nnot json\n")
        sh(r, "git", "add", "-A")
        sh(r, "git", "commit", "-qm", "x")
        base = {"architecture": model.view(r),
                "progress": {"milestones": [{"name": "M", "items": [
                    {"title": "DEM-1 Built", "state": "done"}, {"title": "Free idea", "state": "todo"},
                    {"title": "Gone", "state": "dropped"}]}]},
                "traceability": {"chains": [{"prd": {"slug": "p", "status": "approved"}, "items": [{"title": "Built"}]}]},
                "metrics": {"coverage": None, "coverage_min": 80}}
        d = tab_gates.collect(r, base)
        self.assertEqual((d["items_total"], d["items_no_prd"]), (2, 1))
        self.assertEqual(d["items"][0]["prd"], "p")
        self.assertEqual(d["check"]["sha"], "abc")
        self.assertIsNone(d["security"])
        self.assertEqual([x["path"] for x in d["deps"]], ["package.json"])
        comps = {c["path"]: c["tests"] for c in d["components"]}
        self.assertEqual((comps["src/alpha.ts"], comps["src/beta.ts"]), (1, 0))
        html = tab_gates.render(d)
        self.assertIn("not recorded yet", html)  # security audit and coverage
        self.assertIn("2026-11-01", html)
        self.assertIn("no PRD", html)
        self.assertIn("1/2 items without approved PRD", tab_gates.line(d))

    def test_metrics_record_command(self):
        import metrics
        self.assertIn("record", metrics.cmd_record.__name__)
        tmp = tempfile.mkdtemp()
        old = metrics.RECORDS, metrics.MDIR
        metrics.RECORDS, metrics.MDIR = os.path.join(tmp, "m", "records.jsonl"), os.path.join(tmp, "m")
        try:
            class A:
                kind = "security-audit"
            with contextlib.redirect_stdout(io.StringIO()):
                metrics.cmd_record(A, {})
            self.assertEqual(sources.last_record(tmp, "security-audit"), None)  # reads metrics/, not m/
            os.rename(os.path.join(tmp, "m"), os.path.join(tmp, "metrics"))
            self.assertEqual(sources.last_record(tmp, "security-audit")["kind"], "security-audit")
        finally:
            metrics.RECORDS, metrics.MDIR = old


if __name__ == "__main__":
    unittest.main()
