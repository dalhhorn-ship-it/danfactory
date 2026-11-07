"""Deploy-workflow security checks (stdlib unittest, text/regex parsing, no network)."""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEPLOY = os.path.join(ROOT, "templates", "deploy-cloudflare.yml")
CI = os.path.join(ROOT, ".github", "workflows", "ci.yml")
SCAFFOLD = os.path.join(ROOT, "scripts", "cf_scaffold.py")


HAVE_ALL = all(os.path.isfile(p) for p in (DEPLOY, CI, SCAFFOLD))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def code_lines(text):
    return [l for l in text.splitlines() if not l.lstrip().startswith("#")]


def jobs(text):
    """Return {job_name: block_text} by splitting on 2-space-indented keys under `jobs:`."""
    lines = code_lines(text)
    start = next(i for i, l in enumerate(lines) if l.rstrip() == "jobs:")
    out, name = {}, None
    for l in lines[start + 1:]:
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", l)
        if m:
            name = m.group(1)
            out[name] = []
        elif name:
            out[name].append(l)
    return {k: "\n".join(v) for k, v in out.items()}


def pr_jobs(text):
    if not re.search(r"^\s{2}pull_request:", text, re.M):
        return {}
    res = {}
    for name, block in jobs(text).items():
        cond = re.search(r"^    if:(.*)$", block, re.M)
        if cond is None or "pull_request" in cond.group(1):
            res[name] = block
    return res


@unittest.skipUnless(HAVE_ALL, "workflow files absent (adopted copy)")
class WorkflowSecurity(unittest.TestCase):
    files = (DEPLOY, CI)

    def test_pr_jobs_have_no_secrets(self):
        for f in self.files:
            for name, block in pr_jobs(read(f)).items():
                self.assertNotIn("secrets.", block, "%s job %s references secrets" % (f, name))

    def test_all_uses_pinned_to_sha(self):
        for f in self.files:
            uses = re.findall(r"uses:\s*(\S+)", "\n".join(code_lines(read(f))))
            self.assertTrue(uses)
            for u in uses:
                self.assertRegex(u, r"@[0-9a-f]{40}$", "%s: %s not pinned" % (f, u))
            for l in code_lines(read(f)):
                if "uses:" in l:
                    self.assertRegex(l, r"@[0-9a-f]{40} # v\d", l)

    def test_permissions_contents_read(self):
        for f in self.files:
            self.assertRegex(read(f), r"(?m)^permissions:\n  contents: read\s*$", f)

    def test_no_github_context_in_run(self):
        for f in self.files:
            text = "\n".join(code_lines(read(f)))
            # single-line run: and block-scalar run: |
            for m in re.finditer(r"run:\s*(.*(?:\n(?: {10,}).*)*)", text):
                self.assertNotIn("${{ github.", m.group(1), f)
            self.assertNotRegex(text, r"run:[^\n]*\$\{\{\s*github\.")

    def test_deploy_job(self):
        deploy = jobs(read(DEPLOY))["deploy"]
        self.assertRegex(deploy, r"(?m)^    environment: production\s*$")
        self.assertNotIn("npm install", deploy)
        self.assertIn("package-lock.json", deploy)
        self.assertNotIn("pull_request", deploy.replace("github.event_name == 'push'", ""))

    def test_no_preview_job(self):
        self.assertNotIn("preview", jobs(read(DEPLOY)))
        self.assertNotIn("--preview-alias", read(DEPLOY))

    def test_secret_only_in_production_environment_job(self):
        for name, block in jobs(read(DEPLOY)).items():
            if "secrets." in block:
                self.assertIn("environment: production", block, name)


@unittest.skipUnless(HAVE_ALL, "scaffold files absent (adopted copy)")
class ScaffoldText(unittest.TestCase):
    def test_next_steps_not_repository_secret(self):
        text = read(SCAFFOLD)
        self.assertNotIn("repository secret", text)
        self.assertNotIn("Secrets and variables -> Actions", text)
        self.assertIn("production", text)


if __name__ == "__main__":
    unittest.main()
