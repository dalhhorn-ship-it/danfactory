"""Doc-graph links: bare .md paths that resolve to a file count as edges (docs_index.py)."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import docs_index  # noqa: E402


class Links(unittest.TestCase):
    def targets(self, line):
        return [m.group(1) or m.group(3) or m.group(4) for m in docs_index.LINK_RE.finditer(line)]

    def test_bare_paths_are_links(self):
        self.assertEqual(self.targets("see (docs/policies/security.md) and paths/x.md."),
                         ["docs/policies/security.md", "paths/x.md"])
        self.assertEqual(self.targets("[a](b.md) and `docs/c.md`"), ["b.md", "docs/c.md"])
        self.assertEqual(self.targets("https://x.org/y.md and README.mdx"), [])

    def test_real_repo_parse_resolves_bare_relative_path(self):
        doc = docs_index.parse(os.path.join(ROOT, "docs", "operating-model", "DECISION-TREE.md"))
        self.assertIn("docs/operating-model/paths/software-product.md", doc["links"])



class Related(unittest.TestCase):  # docs_index.py --related, upstreamed from lpdan
    G = {"nodes": [{"id": "docs/a.md", "title": "A", "summary": "about a"}, {"id": "docs/b.md", "title": "B", "summary": "about b"},
                   {"id": "docs/c.md", "title": "C"}, {"id": "docs/lone.md", "title": "Lone"}],
         "edges": [{"from": "docs/a.md", "to": "docs/b.md"}, {"from": "docs/c.md", "to": "docs/a.md"},
                   {"from": "docs/b.md", "to": "docs/c.md"}]}

    def run_cli(self, *args):
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "docs_index.py"), *args],
                              cwd=ROOT, capture_output=True, text=True)

    def test_exact_neighbours_with_summaries(self):
        self.assertEqual(docs_index.related(self.G, "docs/a.md"),
                         [("from", "docs/c.md", "C"), ("to", "docs/b.md", "about b")])

    def test_no_edges_and_unknown(self):
        self.assertEqual(docs_index.related(self.G, "docs/lone.md"), [])
        self.assertIsNone(docs_index.related(self.G, "docs/nope.md"))

    def test_cli(self):
        r = self.run_cli("--related", "docs/does-not-exist.md")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a doc", r.stdout)
        r = self.run_cli("--related", "docs/policies/token-economy.md")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("<- CLAUDE.md", r.stdout)
        self.assertNotIn("stale", r.stdout)


if __name__ == "__main__":
    unittest.main()
