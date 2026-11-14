"""Template ref lookup and template-file list (NEW-1, NEW-2; docs/specs/new-project-readiness.md criteria 1 and 3).
A local bare repo stands in for the upstream: no network. Every git call names its cwd; GIT_CEILING_DIRECTORIES keeps git in the temp dir."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "obs"))
import template_ref  # noqa: E402
import tplfiles  # noqa: E402

GITC = ["git", "-c", "user.name=t-ref", "-c", "user.email=t-ref@example.invalid", "-c", "commit.gpgsign=false"]


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tref-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["GIT_CEILING_DIRECTORIES"] = self.tmp
        self.addCleanup(os.environ.pop, "GIT_CEILING_DIRECTORIES", None)

    def git(self, cwd, *a):
        p = subprocess.run(GITC + list(a), cwd=cwd, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    def write(self, d, rel, text):
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as fh:
            fh.write(text)

    def upstream(self, versions):
        """Bare repo whose commits c1..cN hold the given {path: text} dicts; returns (bare path, [shas oldest first])."""
        w = os.path.join(self.tmp, "up")
        os.makedirs(w)
        self.git(w, "init", "-q")
        shas = []
        for files in versions:
            for rel in os.listdir(w):
                if rel != ".git":
                    os.remove(os.path.join(w, rel))
            for rel, text in files.items():
                self.write(w, rel, text)
            self.git(w, "add", "-A")
            self.git(w, "commit", "-q", "--allow-empty", "-m", "c%d" % (len(shas) + 1))
            shas.append(self.git(w, "rev-parse", "HEAD"))
        bare = os.path.join(self.tmp, "up.git")
        self.git(self.tmp, "clone", "-q", "--bare", w, bare)
        return bare, shas

    def copy_of(self, files):
        """A new repo with its own first commit holding `files` (what "Use this template" makes)."""
        d = os.path.join(self.tmp, "copy")
        os.makedirs(d)
        self.git(d, "init", "-q")
        for rel, text in files.items():
            self.write(d, rel, text)
        self.git(d, "add", "-A")
        self.git(d, "commit", "-q", "-m", "Initial commit")
        return d


V = [{"a.py": "1\n", "b.py": "x\n"}, {"a.py": "2\n", "b.py": "x\n"}, {"a.py": "3\n", "b.py": "x\n"}]


class Resolve(Repo):
    def test_head_that_exists_upstream_is_used(self):
        bare, shas = self.upstream(V)
        clone = os.path.join(self.tmp, "clone")
        self.git(self.tmp, "clone", "-q", bare, clone)
        self.assertEqual(template_ref.resolve(clone, bare), (shas[2], ""))

    def test_copy_with_its_own_commit_gets_the_newest_exact_match(self):
        bare, shas = self.upstream(V + [{"a.py": "3\n", "b.py": "x\n"}])  # c4 equals c3's files: newest wins
        d = self.copy_of(V[1])
        self.assertEqual(template_ref.resolve(d, bare), (shas[1], ""))
        d2 = os.path.join(self.tmp, "copy2")
        shutil.copytree(d, d2)
        self.write(d2, "a.py", "3\n")
        self.git(d2, "commit", "-qam", "edit")
        self.assertEqual(template_ref.resolve(d2, bare)[0], shas[3])

    def test_no_match_falls_back_to_the_main_head_with_a_note(self):
        bare, shas = self.upstream(V)
        d = self.copy_of({"a.py": "99\n", "b.py": "x\n"})
        ref, note = template_ref.resolve(d, bare)
        self.assertEqual(ref, shas[2])
        self.assertIn("main head", note)

    def test_unreachable_upstream_leaves_the_ref_empty_with_a_note(self):
        d = self.copy_of(V[0])
        ref, note = template_ref.resolve(d, os.path.join(self.tmp, "nowhere.git"))
        self.assertEqual(ref, "")
        self.assertIn("could not reach", note)

    def test_subset_mode_matches_the_listed_files_only(self):
        bare, shas = self.upstream([{"a.py": "1\n", "b.py": "x\n"}, {"a.py": "2\n", "b.py": "y\n"}])
        h = tplfiles.blob_hash
        self.write(self.tmp, "w/a.py", "1\n")
        want = {"a.py": h(os.path.join(self.tmp, "w", "a.py"))}
        d = self.copy_of({"z.py": "z\n"})
        self.assertEqual(template_ref.resolve(d, bare, wanted=want, exact=False), (shas[0], ""))

    def test_cli_prints_the_ref_and_notes_on_stderr(self):
        bare, shas = self.upstream(V)
        d = self.copy_of(V[0])
        self.write(d, "factory.json", json.dumps({"template": {"source_repo": bare}}))
        p = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "template_ref.py"), d], capture_output=True, text=True,
                           env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), shas[0])


class TemplateFiles(Repo):
    def test_snapshot_prune_and_owned(self):
        d = self.copy_of({"a.py": "1\n", "docs/x.md": "doc\n"})
        tplfiles.write(d, tplfiles.snapshot(d))
        self.assertEqual(tplfiles.owned(d), {"a.py", "docs/x.md"})
        self.assertEqual(tplfiles.read(d)["a.py"], self.git(d, "hash-object", "a.py"))  # same value as git's
        self.write(d, "a.py", "edited\n")  # an edited template file is the project's again
        self.assertEqual(tplfiles.owned(d), {"docs/x.md"})
        os.remove(os.path.join(d, "docs", "x.md"))
        self.assertEqual(tplfiles.prune(d), 0)  # a.py changed, x.md gone
        self.assertEqual(tplfiles.owned(d), set())

    def test_no_list_means_nothing_is_owned(self):  # the template repo itself
        d = self.copy_of({"a.py": "1\n"})
        self.assertEqual(tplfiles.owned(d), set())


if __name__ == "__main__":
    unittest.main()
