"""Morning report and Missions tab (scripts/mission_report.py, scripts/obs/tab_missions.py, ADR 0012, MISSION-4) plus the
parallel-build docs rules (MISSION-5). Mission files are real, built in temp git repos in the ADR's format. No network."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
import dashboard  # noqa: E402
import mission_report  # noqa: E402
from obs import tab_missions  # noqa: E402

START = "2026-11-16T22:00:00Z"
MISSION = """# Demo mission

<!-- mission:start -->
slug: demo
status: active
go: "go"
date: 2026-11-16
started_at: {start}
branch: mission/demo
milestone: M5
features: 3
caps: usd=15 hours=10 continuations=40
scope_in: reports
scope_out: billing
<!-- mission:end -->

## Brief
Build reports. Reply go to start.

## Decision log
- 2026-11-17 Assumption: CSV is enough, no PDF.
- 2026-11-17 Parked: billing export is out of scope.
"""
BACKLOG = """# Backlog

## Milestone: M5 — Demo (mission: demo)
- [x] DEMO-1 Report page (docs/specs/demo-report-page.md)
- [x] DEMO-2 CSV export (docs/specs/demo-csv.md)
- [!] DEMO-3 Billing export parked: out of scope (docs/specs/demo-billing.md)
"""


def ts(h):
    t = datetime.datetime(2026, 11, 16, 22, 0, tzinfo=datetime.timezone.utc) + datetime.timedelta(hours=h)
    return t.isoformat(timespec="seconds")


class Proj:
    def __init__(self, with_mission=True, backlog=BACKLOG):
        self.root = tempfile.mkdtemp()
        self.g("init", "-q", "-b", "main")
        self.write("factory.json", json.dumps({"dashboard": {"github_repo": ""}}))
        if with_mission:
            self.write("docs/missions/demo.md", MISSION.format(start=START))
            self.write("docs/BACKLOG.md", backlog)
            self.g("add", "-A")
            self.g("commit", "-qm", "mission")

    def g(self, *a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=self.root, capture_output=True, text=True).stdout

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)

    def read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as fh:
            return fh.read()

    def state(self, **kw):
        s = {"slug": "demo", "continuations": 7, "sessions": {"s1": 1.5, "s2": 2.25}, "ended": None}
        s.update(kw)
        self.write(".factory/mission-state.json", json.dumps(s))

    def gate(self, *rows):
        self.write("metrics/gate.local.jsonl", "".join(json.dumps(r) + "\n" for r in rows))


class ReportTests(unittest.TestCase):
    def proj(self, **kw):
        p = Proj(**kw)
        self.addCleanup(shutil.rmtree, p.root, True)
        return p

    def report(self, p, reason):
        path = mission_report.write(p.root, "demo", reason)
        self.assertEqual(os.path.realpath(path), os.path.realpath(os.path.join(p.root, "docs/missions/demo-report.md")))
        return p.read("docs/missions/demo-report.md")

    def test_has_verdict_first_and_all_six_sections(self):
        p = self.proj()
        p.state()
        p.gate({"ts": ts(1), "verdict": "pass", "sha": "abcdef1234567", "codes": []},
               {"ts": ts(2), "verdict": "fail", "sha": "1111111111111", "codes": ["no-approved-prd"]},
               {"ts": ts(-5), "verdict": "pass", "sha": "oldoldold", "codes": []})  # before the start: not listed
        text = self.report(p, "done")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        self.assertTrue(lines[1].startswith("Verdict: done with parked items"), lines[:3])
        heads = [ln for ln in text.splitlines() if ln.startswith("## ")]
        self.assertEqual(heads, ["## Shipped", "## Assumptions", "## Parked", "## Cost", "## Time", "## Gate verdicts"])
        self.assertIn("DEMO-1 Report page", text)
        self.assertIn("`demo-csv`", text)
        self.assertIn("CSV is enough", text)
        self.assertIn("DEMO-3", text)
        self.assertIn("billing export is out of scope", text)
        self.assertIn("$3.75", text)
        self.assertIn("$15.00", text)
        self.assertIn("7 of 40", text)
        self.assertIn("2026-11-16T22:00:00Z", text)
        self.assertIn("abcdef1234", text)
        self.assertIn("no-approved-prd", text)
        self.assertNotIn("oldoldold", text)

    def test_verdict_variants(self):
        p = self.proj(backlog=BACKLOG.replace("[!] DEMO-3 Billing export parked: out of scope (docs/specs/demo-billing.md)",
                                              "[x] DEMO-3 Billing (docs/specs/demo-billing.md)"))
        p.write("docs/missions/demo.md", MISSION.format(start=START).replace("- 2026-11-17 Parked: billing export is out of scope.\n", ""))
        self.assertIn("Verdict: done.", self.report(p, "done"))
        for cap in ("budget", "wall-clock", "continuations"):
            text = self.report(p, cap)
            self.assertIn("Verdict: stopped at %s" % cap, text)
        self.assertIn("stopped by the user", self.report(p, "stopped"))

    def test_status_is_set_and_reason_comes_from_state(self):
        p = self.proj()
        p.state(ended={"reason": "budget", "ts": ts(3)})
        text = self.report(p, "")
        self.assertIn("stopped at budget", text)
        self.assertIn("status: stopped", p.read("docs/missions/demo.md"))
        self.assertIn("Hours: 3.0", text)
        self.report(p, "done")
        self.assertIn("status: done", p.read("docs/missions/demo.md"))

    def test_no_state_no_gate_rows_say_so_and_it_is_regenerable(self):
        p = self.proj()
        first = self.report(p, "stopped")
        self.assertIn("Spend unknown", first)
        self.assertIn("No gate runs recorded", first)
        self.assertIn("## Gate verdicts", self.report(p, "stopped"))

    def test_unknown_mission_and_cli(self):
        p = self.proj()
        with self.assertRaises(ValueError):
            mission_report.write(p.root, "nope", "done")
        self.assertEqual(mission_report.main([], root=p.root), 2)
        self.assertEqual(mission_report.main(["nope"], root=p.root), 1)
        self.assertEqual(mission_report.main(["demo", "--reason", "done"], root=p.root), 0)


class TabTests(unittest.TestCase):
    def test_empty_state_without_missions_dir(self):
        p = Proj(with_mission=False)
        self.addCleanup(shutil.rmtree, p.root, True)
        data = tab_missions.collect(p.root, {})
        self.assertIsNone(data["latest"])
        self.assertEqual(tab_missions.line(data), "")
        self.assertIn("No missions yet", tab_missions.render(data))

    def test_malformed_mission_file_does_not_fail(self):
        p = Proj(with_mission=False)
        self.addCleanup(shutil.rmtree, p.root, True)
        p.write("docs/missions/broken.md", "no header here\n")
        p.write("docs/missions/_TEMPLATE.md", "template\n")
        self.assertIn("No missions yet", tab_missions.render(tab_missions.collect(p.root, {})))

    def test_latest_mission_verdict_and_report_link(self):
        p = Proj()
        self.addCleanup(shutil.rmtree, p.root, True)
        before = tab_missions.render(tab_missions.collect(p.root, {}))
        self.assertIn("no report yet", before)
        mission_report.write(p.root, "demo", "continuations")
        p.write("factory.json", json.dumps({"dashboard": {"github_repo": "o/r"}}))
        data = tab_missions.collect(p.root, {})
        self.assertIn("stopped at continuations", data["latest"]["verdict"])
        self.assertIn("docs/missions/demo-report.md", tab_missions.line(data))
        html = tab_missions.render(data)
        self.assertIn("https://github.com/o/r/blob/mission/demo/docs/missions/demo-report.md", html)
        self.assertIn("stopped at continuations", html)

    def test_dashboard_has_missions_tab_and_builds_without_missions(self):
        self.assertIn(("missions", "Missions", tab_missions), dashboard.TABS)
        self.assertEqual(sum(1 for t in dashboard.TABS if t[0] == "missions"), 1)
        p = Proj(with_mission=False)
        self.addCleanup(shutil.rmtree, p.root, True)
        panel = tab_missions.render(tab_missions.collect(p.root, {}))
        self.assertIn("Missions", panel)


class DocsRuleTests(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            return fh.read()

    def test_agent_rules_and_routing_section(self):
        dev = self.read(".claude/agents/developer.md")
        self.assertIn("cross-slice request", dev)
        self.assertIn("**Finding things:**", dev)
        arch = self.read(".claude/agents/software-architect.md")
        self.assertIn("Owns", arch)
        self.assertIn("**Finding things:**", arch)
        routing = self.read("docs/operating-model/AGENT-ROUTING.md")
        self.assertIn("## Parallel build", routing)
        self.assertIn("slices.py land", routing)
        self.assertIn("build.max_parallel", routing)

    def test_factory_json_max_parallel(self):
        self.assertEqual(json.loads(self.read("factory.json"))["build"]["max_parallel"], 3)


if __name__ == "__main__":
    unittest.main()
