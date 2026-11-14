"""DOCS-1: agents read by index, long docs list their sections, doc size budget (docs/specs/docs-index-first.md)."""
import glob
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import docs_index  # noqa: E402
from obs import size  # noqa: E402


def doc(name, tokens, heads=()):
    return {"file": name, "title": name, "summary": "about " + name, "lines": 10, "tokens": tokens,
            "headings": [(i + 3, 2, h) for i, h in enumerate(heads)], "links": []}


class Agents(unittest.TestCase):
    def test_criterion_1_every_agent_has_a_finding_things_line(self):  # criterion 1
        files = sorted(glob.glob(os.path.join(ROOT, ".claude", "agents", "*.md")))
        self.assertGreaterEqual(len(files), 19)  # 19 in a project without the autonomy pack (no finder)
        for f in files:
            with open(f, encoding="utf-8") as fh:
                text = fh.read()
            line = next((x for x in text.splitlines() if x.startswith("**Finding things:**")), "")
            self.assertTrue(line, os.path.basename(f) + " has no Finding things line")
            self.assertIn("docs/INDEX.md", line, f)
            self.assertIn("docs_index.py --related", line, f)


class Sections(unittest.TestCase):
    def test_criterion_2_sections_only_over_the_threshold(self):
        out = docs_index.render([doc("a.md", 1501, ["One", "Two"]), doc("b.md", 1500, ["Three"])], "x")
        a = next(x for x in out.splitlines() if x.startswith("| a.md"))
        b = next(x for x in out.splitlines() if x.startswith("| b.md"))
        self.assertIn("sections: One:3, Two:4", a)
        self.assertNotIn("sections", b)

    def test_threshold_comes_from_factory_json(self):
        self.assertEqual(docs_index.sections_threshold(), 1500)

    def test_real_docs_over_the_threshold_get_their_sections(self):  # copies of the template have fewer docs
        parsed = [docs_index.parse(p) for p in docs_index.collect()]
        long_docs = [d for d in parsed if d["tokens"] > docs_index.sections_threshold() and d["headings"]]
        out = docs_index.render(long_docs, "x")
        self.assertEqual(out.count("sections:"), len([d for d in long_docs if any(h[1] == 2 for h in d["headings"])]))


class DocBudget(unittest.TestCase):
    B = dict(size.DEFAULTS)

    def flags(self, docs):
        d = {"files": [], "always_loaded": {"total": 0}, "counts": {"agents": 0}, "growth": {}, "docs": docs}
        return size.flags(d, self.B)

    def test_criterion_3_policy_flagged_with_the_action_record_is_not_split(self):
        f = self.flags([{"path": "docs/policies/x.md", "tokens": 3001}, {"path": "docs/specs/y.md", "tokens": 6000},
                        {"path": "docs/policies/ok.md", "tokens": 3000}])
        self.assertEqual([x["subject"] for x in f], ["docs/policies/x.md", "docs/specs/y.md"])
        self.assertEqual(f[0]["level"], "medium")
        self.assertIn("split by topic, or rely on the indexed sections", f[0]["action"])
        self.assertEqual(f[1]["level"], "low")
        self.assertIn("indexed record, not split", f[1]["action"])
        self.assertIn("3001 tokens", size.text(f[0]))

    def test_records_are_not_alerts_and_size_line_counts_docs(self):
        d = {"files": [], "always_loaded": {"total": 0, "claude_md": 0, "session_start": 0}, "counts": {"agents": 0}, "growth": {},
             "areas": {"code": {"files": 0, "lines": 0}}, "budgets": self.B,
             "docs": [{"path": "docs/specs/y.md", "tokens": 6000}, {"path": "docs/policies/x.md", "tokens": 3500}]}
        d["flags"] = size.flags(d, self.B)
        self.assertEqual(len(d["flags"]), 2)
        self.assertIn("2 docs over 3000 tokens", size.line(d))
        alerts = [size.text(f) for f in d["flags"] if f["level"] != "low"]
        self.assertEqual(len(alerts), 1)
        self.assertIn("docs/policies/x.md", alerts[0])

    def test_policies_and_guides_are_within_the_budget(self):  # the splitting is kept
        with open(os.path.join(ROOT, "factory.json"), encoding="utf-8") as fh:
            warn = size.budgets(json.load(fh))["doc_tokens_warn"]
        big = [r for r in size.doc_sizes(ROOT, size.current_files(ROOT))
               if r["tokens"] > warn and not r["path"].startswith(size.RECORD_DIRS) and r["path"] != "docs/TECH-DEBT.md"]
        self.assertEqual(big, [])

    def test_criterion_5_always_loaded_within_budget(self):
        self.assertLessEqual(size.always_loaded(ROOT)["total"], size.DEFAULTS["always_loaded_tokens_max"])


if __name__ == "__main__":
    unittest.main()
