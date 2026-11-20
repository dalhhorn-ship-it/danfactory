"""FISH-7 (docs/specs/teach-agents-to-fish.md criteria 14-16): scripts/retro_failures.py and the retro skill text.
Criteria 14-15 are agent/user behaviour (skill text checked); the gathering is tested on temporary projects."""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import retro_failures as rf  # noqa: E402

NOW = datetime.datetime.now(datetime.timezone.utc)


def ts(days_ago=0):
    return (NOW - datetime.timedelta(days=days_ago)).isoformat(timespec="seconds")


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class Project(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="retro-fail-")
        self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, "metrics"))

    def jsonl(self, rel, rows):
        with open(os.path.join(self.d, rel), "w", encoding="utf-8") as fh:
            fh.write("not json\n" + "".join(json.dumps(r) + "\n" for r in rows))


class Gather(Project):
    def test_c14_three_sources_listed(self):
        self.jsonl("metrics/gate.local.jsonl", [{"ts": ts(1), "verdict": "fail", "codes": ["file-over-size"]}] * 3
                   + [{"ts": ts(1), "verdict": "pass", "codes": []}, {"ts": ts(1), "verdict": "fail", "codes": ["rare"]}])
        self.jsonl("metrics/guard.local.jsonl", [{"ts": ts(2), "path": "tests/acceptance/x.py", "why": "locked"}] * 3
                   + [{"ts": ts(40), "path": "old.py", "why": "x"}] * 5)
        os.makedirs(os.path.join(self.d, "issues", "blocked"))
        with open(os.path.join(self.d, "issues", "blocked", "ISS-0001.md"), "w", encoding="utf-8") as fh:
            fh.write("# ISS-0001: parser breaks on empty input\n")
        items = rf.gather(self.d)
        self.assertEqual([(i["kind"], i["subject"]) for i in items],
                         [("blocked", "ISS-0001"), ("gate", "file-over-size"), ("guard", "tests/acceptance/x.py")])
        out = rf.render(items)
        self.assertIn("context / tool / guardrail", out)
        self.assertIn("parser breaks on empty input", out)

    def test_c16_no_pack_still_runs_on_gate_and_guard(self):
        self.assertFalse(os.path.exists(os.path.join(self.d, "issues")))
        self.jsonl("metrics/guard.local.jsonl", [{"ts": ts(), "path": "a.py", "why": "w"}] * 3)
        items = rf.gather(self.d)
        self.assertEqual([i["kind"] for i in items], ["guard"])

    def test_c16_script_imports_nothing_from_the_pack(self):
        src = read("scripts/retro_failures.py")
        for mod in ("learn", "issues", "runner"):
            self.assertNotIn("import " + mod, src)

    def test_empty_data_says_so(self):
        self.assertIn("No recurring", rf.render(rf.gather(self.d)))

    def test_threshold_option(self):
        self.jsonl("metrics/guard.local.jsonl", [{"ts": ts(), "path": "a.py", "why": "w"}] * 2)
        self.assertEqual(rf.gather(self.d), [])
        self.assertEqual(len(rf.gather(self.d, threshold=2)), 1)


class SkillText(unittest.TestCase):
    def test_c14_c15_c16_retro_step(self):
        t = read(".claude/skills/retro/SKILL.md")
        for needle in ("scripts/retro_failures.py", "exactly one class", "context", "tool", "guardrail", "accept or drop",
                       "product-manager", "LEARNINGS.md", "without the pack it still runs on the gate and guard data"):
            self.assertIn(needle, t)

    def test_learnings_format_mentions_choice(self):
        self.assertIn("Fix the machine", read("docs/operating-model/LEARNINGS.md"))
