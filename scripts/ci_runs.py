#!/usr/bin/env python3
"""Fetch the GitHub Actions run history into metrics/ci-runs.json for the dashboard.

  python3 scripts/ci_runs.py                 # repo from factory.json dashboard.github_repo, else git remote origin
  python3 scripts/ci_runs.py --repo owner/name --pages 3

Public repos need no credentials (60 API calls an hour). If GITHUB_TOKEN or GH_TOKEN is set it is
sent for a higher limit and for private repos (CI passes the job token). This is the only dashboard
script that uses the network; scripts/dashboard.py just reads the file, so the page stays offline.
metrics/ci-runs.json is a cache (git-ignored): run this again any time to refresh it.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "metrics", "ci-runs.json")
KEYS = ("id", "name", "event", "head_branch", "status", "conclusion",
        "created_at", "run_started_at", "updated_at", "html_url")


def parse_repo(url):
    """owner/name from a GitHub remote URL (https, ssh or a proxy path ending in /owner/name), or ''."""
    url = (url or "").strip()
    m = re.search(r"github\.com[:/]+([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url) or \
        re.search(r"/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url)
    return "%s/%s" % (m.group(1), m.group(2)) if m else ""


def repo_name(argv):
    if "--repo" in argv:
        return argv[argv.index("--repo") + 1]
    try:
        with open(os.path.join(ROOT, "factory.json"), encoding="utf-8") as fh:
            configured = (json.load(fh).get("dashboard") or {}).get("github_repo")
        if configured:
            return configured
    except (OSError, ValueError):
        pass
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True,
                             text=True, check=False).stdout
    except OSError:
        url = ""
    return parse_repo(url)


def fetch(repo, page):
    url = "https://api.github.com/repos/%s/actions/runs?per_page=100&page=%d" % (repo, page)
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "danfactory-dashboard"})
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("workflow_runs", [])


def write(runs, source, path=OUT):
    """Write a compact list, one run per line, newest first. Returns the run count."""
    runs = sorted(({k: r.get(k) for k in KEYS} for r in runs),
                  key=lambda r: r["created_at"] or "", reverse=True)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"source": %s, "fetched_at": "%s", "runs": [\n' % (json.dumps(source), now))
        f.write(",\n".join(json.dumps(r, separators=(",", ":")) for r in runs))
        f.write("\n]}\n")
    return len(runs)


def main(argv):
    repo = repo_name(argv)
    if not repo:
        print("No GitHub repo: set factory.json dashboard.github_repo or pass --repo owner/name.", file=sys.stderr)
        return 1
    pages = int(argv[argv.index("--pages") + 1]) if "--pages" in argv else 3
    runs, seen = [], set()
    for page in range(1, pages + 1):
        try:
            batch = fetch(repo, page)
        except Exception as err:  # noqa: BLE001 - network, rate limit or proxy
            print("Could not fetch page %d for %s: %s" % (page, repo, err), file=sys.stderr)
            if not runs:
                return 1
            break
        for r in batch:
            if r.get("id") not in seen:
                seen.add(r.get("id"))
                runs.append(r)
        if len(batch) < 100:
            break
    n = write(runs, "GitHub Actions runs API, " + repo)
    print("Wrote %d runs to metrics/ci-runs.json" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
