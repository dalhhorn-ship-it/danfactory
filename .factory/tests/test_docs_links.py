"""Doc-graph links: bare .md paths that resolve to a file count as edges (docs_index.py)."""
import os
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


if __name__ == "__main__":
    unittest.main()
