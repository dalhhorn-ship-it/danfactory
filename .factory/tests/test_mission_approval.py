"""Mission approval (MISSION-1, docs/specs/mission-autopilot.md criteria 1-4 and 12; ADR 0012): the PRD write guard and the
`prd` gate check accept a PRD marked `by mission <slug>` only while a valid, live mission covers it in scope.
Temp git repos, no network, no model."""
import contextlib
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOOK = os.path.join(ROOT, ".claude", "hooks", "guard_prd_write.py")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
import gate  # noqa: E402
import _mission as M  # noqa: E402
import _prd  # noqa: E402
import mission as cli  # noqa: E402

UTC = datetime.timezone.utc
NOW = datetime.datetime.now(UTC).replace(microsecond=0)
PRD = "# PRD: Demo\n\n> Status: %s\n\n## Acceptance criteria\n1. a thing\n"
BY = "approved · 2026-11-16 · by mission %s"


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def header(slug="night", status="active", started=None, go='"go"', hours="10", features="5", caps=None, milestone="M5"):
    started = started or NOW - datetime.timedelta(hours=1)
    return M.START + "\n" + "\n".join([
        "slug: " + slug, "status: " + status, "go: " + go, "date: " + started.date().isoformat(),
        "started_at: " + iso(started), "branch: mission/" + slug, "milestone: " + milestone, "features: " + features,
        "caps: " + (caps or "usd=15 hours=%s continuations=40" % hours),
        "scope_in: the thing", "scope_out: the rest"]) + "\n" + M.END + "\n"


class Proj:
    """Temp project with a committed mission `night` and a backlog milestone M5 holding items linked to specs."""

    def __init__(self, mission=True, backlog=None, **hk):
        self.root = tempfile.mkdtemp()
        self.write("factory.json", json.dumps({"phase": "build", "gate": {}}))
        self.write("docs/BACKLOG.md", backlog if backlog is not None else (
            "# Backlog\n\n## Milestone: M5 — Night (mission: night)\n"
            "- [~] NIGHT-1 One (docs/specs/night-one.md)\n- [ ] NIGHT-2 Two (docs/specs/night-two.md)\n"
            "- [ ] OTHER-1 Stray (docs/specs/stray.md)\n\n## Milestone: M6 — Elsewhere\n- [~] ELSE-1 (docs/specs/night-else.md)\n"))
        for s in ("night-one", "night-two", "stray", "night-else", "night-unlinked"):
            self.write("docs/specs/%s.md" % s, PRD % (BY % "night"))
        if mission:
            self.write("docs/missions/night.md", "# Mission: Night\n\n" + header(**hk) + "\n## Brief\nx\n")
        self.g("init", "-q")
        self.commit("start")

    def g(self, *a, env=None):
        p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"] + list(a),
                           cwd=self.root, capture_output=True, text=True, env=env)
        assert p.returncode == 0, p.stderr
        return p.stdout

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, msg, when=None, trailer=""):
        self.g("add", "-A")
        env = dict(os.environ, GIT_AUTHOR_DATE=iso(when), GIT_COMMITTER_DATE=iso(when)) if when else None
        self.g("commit", "-q", "--allow-empty", "-m", msg + ("\n\n" + trailer if trailer else ""), env=env)

    def edit(self, rel):
        ev = {"tool_name": "Edit", "tool_input": {"file_path": os.path.join(self.root, rel)}, "cwd": self.root}
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.root)
        return subprocess.run([sys.executable, HOOK], input=json.dumps(ev), capture_output=True, text=True, env=env)


class Base(unittest.TestCase):
    def proj(self, **kw):
        p = Proj(**kw)
        self.addCleanup(shutil.rmtree, p.root, True)
        return p


class Approval(Base):
    def test_c1_no_mission_rejects_by_mission(self):
        p = self.proj(mission=False)
        self.assertEqual(_prd.prd_status(p.root, "night-one"), "unapproved")  # the first Status word alone would say approved
        self.assertFalse(_prd.item_approved(p.root, "NIGHT-1"))
        self.assertEqual(p.edit("src/app.py").returncode, 2)

    def test_c1_gate_rejects_by_mission_without_mission(self):
        p = self.proj(mission=False)
        base = p.g("rev-parse", "HEAD").strip()
        p.write("src/app.py", "x = 1\n")
        p.commit("code", trailer="Refs: NIGHT-1")
        c = {x["id"]: x for x in gate.run_gate(p.root, base, {"prd"})["checks"]}["prd"]
        self.assertEqual(c["status"], "fail")
        self.assertIn("no-approved-prd", c["codes"])

    def test_c2_in_scope_is_approved_in_guard_and_gate(self):
        p = self.proj()
        self.assertEqual(_prd.prd_status(p.root, "night-one"), "approved")
        self.assertEqual(M.approval(p.root, "night", "night-two"), (True, ""))
        self.assertEqual(p.edit("src/app.py").returncode, 0)
        base = p.g("rev-parse", "HEAD").strip()
        p.write("src/app.py", "x = 1\n")
        p.commit("code", trailer="Refs: NIGHT-1")
        c = {x["id"]: x for x in gate.run_gate(p.root, base, {"prd"})["checks"]}["prd"]
        self.assertEqual(c["status"], "pass", c["detail"])
        self.assertIn('covered by mission night (go: "go")', c["detail"])

    def test_c3_out_of_scope_is_unapproved_and_parked(self):
        p = self.proj(backlog="# Backlog\n\n## Milestone: M5 — Night\n- [~] NIGHT-1 One (docs/specs/night-one.md)\n"
                              "- [ ] NIGHT-2 Two (docs/specs/night-two.md)\n- [ ] OTHER-1 Stray (docs/specs/stray.md)\n"
                              "- [!] NIGHT-3 Three, parked: out of scope (docs/specs/night-three.md)\n"
                              "\n## Milestone: M6 — Elsewhere\n- [~] ELSE-1 (docs/specs/night-else.md)\n", features="1")
        m = M.load(p.root, "night")
        self.assertEqual(_prd.prd_status(p.root, "night-one"), "approved")
        for spec, why in (("night-two", "feature cap"), ("stray", "prefix"), ("night-else", "milestone"), ("night-unlinked", "milestone")):
            self.assertEqual(_prd.prd_status(p.root, spec), "unapproved", spec)
            self.assertFalse(M.in_scope(p.root, m, spec), spec)
            self.assertIn(why, {x["ref"]: x["why"] for x in M.parked(p.root, m)}[spec])
        self.assertIn("NIGHT-3", [x["ref"] for x in M.parked(p.root, m)])
        self.assertEqual(M.next_item(p.root, m)["id"], "NIGHT-1")  # other items continue

    def test_c4_expired_or_capped_is_unapproved(self):
        cases = {"expired": dict(started=NOW - datetime.timedelta(hours=12)), "stopped": dict(status="stopped"),
                 "done": dict(status="done")}
        for name, kw in cases.items():
            p = self.proj(**kw)
            self.assertEqual(_prd.prd_status(p.root, "night-one"), "unapproved", name)
            self.assertEqual(p.edit("src/app.py").returncode, 2, name)
        p = self.proj()
        st = M.load_state(p.root, "night")
        st["sessions"] = {"s1": 15.0}
        M.save_state(p.root, st)
        self.assertEqual(_prd.prd_status(p.root, "night-one"), "unapproved")  # budget
        st.update(sessions={}, continuations=40)
        M.save_state(p.root, st)
        self.assertEqual(_prd.prd_status(p.root, "night-one"), "unapproved")  # continuations

    def test_historical_gate_uses_commit_time(self):
        p = self.proj(started=NOW - datetime.timedelta(hours=12), hours="10")  # window ended 2 hours ago
        base = p.g("rev-parse", "HEAD").strip()
        p.write("src/a.py", "x = 1\n")
        p.commit("inside window", when=NOW - datetime.timedelta(hours=5), trailer="Refs: NIGHT-1")
        p.write("src/b.py", "x = 2\n")
        p.commit("after window", when=NOW - datetime.timedelta(hours=1), trailer="Refs: NIGHT-1")
        c = {x["id"]: x for x in gate.run_gate(p.root, base, {"prd"})["checks"]}["prd"]
        self.assertEqual(c["status"], "fail")
        self.assertIn("1 product-code commit(s) without", c["detail"])  # only the late one

    def test_invalid_missions(self):
        bads = {"go without a clear yes": dict(go='"looks good"'), "unquoted go": dict(go="go"),
                "future start": dict(started=NOW + datetime.timedelta(hours=2)),
                "empty scope": dict(milestone="")}
        for name, kw in bads.items():
            p = self.proj(**kw)
            self.assertNotEqual(M.validate(p.root, M.load(p.root, "night")), "", name)
            self.assertEqual(_prd.prd_status(p.root, "night-one"), "unapproved", name)

    def test_header_frozen_after_first_commit_but_status_may_change(self):
        p = self.proj()
        m = M.load(p.root, "night")
        self.assertEqual(M.validate(p.root, m), "")
        M.set_status(p.root, "night", "stopped")
        self.assertEqual(M.validate(p.root, M.load(p.root, "night")), "")
        M.set_status(p.root, "night", "active")
        with open(m["path"], encoding="utf-8") as fh:
            text = fh.read().replace("features: 5", "features: 50")
        p.write("docs/missions/night.md", text)
        self.assertIn("features", M.validate(p.root, M.load(p.root, "night")))
        self.assertEqual(_prd.prd_status(p.root, "night-one"), "unapproved")

    def test_uncommitted_mission_is_invalid(self):
        p = self.proj(mission=False)
        p.write("docs/missions/night.md", "# Mission: Night\n\n" + header() + "\n")
        self.assertIn("not committed", M.validate(p.root, M.load(p.root, "night")))

    def test_go_valid_and_curly_quotes(self):
        self.assertTrue(M.go_valid('"go"'))
        self.assertTrue(M.go_valid("“ok, go for it”"))
        for good in ('"Ok"', '"yes"', '"approved"', '"build it"'):
            self.assertTrue(M.go_valid(good), good)
        for bad in ('"looks good"', "go", '"going nowhere"', "", '"go', '"interesting"'):
            self.assertFalse(M.go_valid(bad), bad)

    def test_api_basics(self):
        p = self.proj()
        m = M.active(p.root)
        self.assertEqual((m["slug"], m["features"], m["caps"]), ("night", 5, {"usd": 15.0, "hours": 10.0, "continuations": 40}))
        self.assertEqual(M.expires_at(m) - m["started_at"], datetime.timedelta(hours=10))
        self.assertEqual(M.mission_of("> Status: approved · 2026-11-16 · by mission night-x"), "night-x")
        self.assertEqual(M.mission_of("> Status: approved · by user in chat"), "")
        st = M.load_state(p.root, "night")
        self.assertEqual((st["continuations"], st["ended"]), (0, None))
        self.assertEqual(M.cap_hit(m, st), "")
        self.assertEqual(M.cap_hit(m, dict(st, continuations=40)), "continuations")
        self.assertEqual(M.cap_hit(m, dict(st, sessions={"a": 9, "b": 6})), "budget")
        self.assertEqual(M.cap_hit(m, st, now=M.expires_at(m)), "wall-clock")
        self.assertEqual(M.cap_hit(dict(m, status="stopped"), st), "stopped")
        self.assertEqual([i["id"] for i in M.items(p.root, m)], ["NIGHT-1", "NIGHT-2", "OTHER-1"])
        self.assertEqual(M.next_item(p.root, m)["id"], "NIGHT-1")
        self.assertEqual(M.load_state(p.root, "other")["slug"], "other")  # a different slug resets
        self.assertIsNone(M.load(p.root, "night-report"))
        self.assertIsNone(M.load(p.root, "../x"))

    def test_next_item_plan_and_done(self):
        p = self.proj(backlog="# Backlog\n\n## Milestone: M5 — Night\n")
        m = M.load(p.root, "night")
        self.assertEqual(M.next_item(p.root, m)["id"], "PLAN")
        p.write("docs/BACKLOG.md", "## Milestone: M5 — Night\n- [x] A-1 a\n- [!] A-2 b\n- [-] A-3 c\n")
        self.assertIsNone(M.next_item(p.root, m))

    def test_active_is_earliest_started(self):
        p = self.proj()
        late = header(slug="later", started=NOW - datetime.timedelta(minutes=5))
        p.write("docs/missions/later.md", "# Mission: Later\n\n" + late)
        self.assertEqual(M.active(p.root)["slug"], "night")


class NoMission(Base):
    """Criterion 12: with no docs/missions/ nothing changes, and `_mission` is not even loaded for ordinary PRDs."""

    def test_c12_ordinary_prds_never_touch_mission_code(self):
        p = self.proj(mission=False)
        p.write("docs/specs/plain.md", PRD % "approved · 2026-11-12 · by user in chat")
        before = list(_prd._MISSION)
        self.assertEqual(_prd.prd_status(p.root, "plain"), "approved")
        self.assertEqual(_prd.prd_status(p.root, "plain", at=NOW), "approved")
        self.assertEqual(list(_prd._MISSION), before)
        self.assertIsNone(M.active(p.root))
        self.assertEqual(M.all_missions(p.root), [])


class Cli(Base):
    def run_cli(self, p, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(list(args), root=p.root)
        return rc, buf.getvalue()

    def test_start_status_stop(self):
        p = self.proj(mission=False)
        argv = ["start", "run1", "--go", "go build it", "--title", "Run one", "--scope-in", "a", "--scope-out", "b", "--milestone", "M7"]
        self.assertEqual(cli.main(argv, root=p.root), 0)
        m = M.load(p.root, "run1")
        self.assertEqual((m["status"], m["go"], m["milestone"], m["branch"]), ("active", '"go build it"', "M7", "mission/run1"))
        with open(os.path.join(p.root, "docs/BACKLOG.md"), encoding="utf-8") as fh:
            self.assertIn("## Milestone: M7 — Run one (mission: run1)", fh.read())
        self.assertIn("not committed", M.validate(p.root, m))
        p.commit("mission")
        self.assertEqual(M.validate(p.root, M.load(p.root, "run1")), "")
        self.assertEqual(cli.main(["start", "run2"] + argv[2:], root=p.root), 1)  # refuses while one is active
        rc, out = self.run_cli(p, "status", "run1")
        self.assertIn("valid", out)
        self.assertIn("PLAN", out)
        self.assertEqual(self.run_cli(p, "stop", "run1")[0], 0)
        self.assertEqual(M.load(p.root, "run1")["status"], "stopped")
        self.assertEqual(M.validate(p.root, M.load(p.root, "run1")), "")

    def test_start_refuses_weak_go(self):
        p = self.proj(mission=False)
        argv = ["start", "run1", "--go", "looks good", "--title", "T", "--scope-in", "a", "--scope-out", "b", "--milestone", "M7"]
        self.assertEqual(cli.main(argv, root=p.root), 1)
        self.assertIsNone(M.load(p.root, "run1"))


if __name__ == "__main__":
    unittest.main()
