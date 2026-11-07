#!/usr/bin/env python3
"""Fetch the GitHub Actions run history into metrics/ci-runs.json for the dashboard.

  python3 scripts/ci_runs.py                 # repo from factory.json dashboard.github_repo, else git remote origin
  python3 scripts/ci_runs.py --repo owner/name --pages 3

Public repos need no credentials (60 API calls an hour). If GITHUB_TOKEN or GH_TOKEN is set it is
sent (to api.github.com only) for a higher limit and for private repos; CI passes the job token via env.
This is the only dashboard script that uses the network; scripts/dashboard.py just reads the file, so the
page stays offline. metrics/ci-runs.json is a cache (git-ignored): run this again any time to refresh it.
Exit codes: 0 written, 1 no repo, bad repo name or nothing fetched on page 1 (the file is left alone).
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
REPO_RE = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")


def valid_repo(repo):
    """True for `owner/name` (letters, digits, dot, underscore, dash), and not a path-traversal name."""
    return bool(REPO_RE.fullmatch(repo or "")) and not any(p in (".", "..") for p in repo.split("/"))


def parse_repo(url):
    """owner/name from a GitHub remote URL (https, ssh or a proxy path ending in /owner/name), or ''."""
    url = (url or "").strip()
    m = re.search(r"github\.com[:/]+([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url) or \
        re.search(r"/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url)
    return "%s/%s" % (m.group(1), m.group(2)) if m else ""


def repo_name(argv):
    if "--repo" in argv:
        i = argv.index("--repo")
        return argv[i + 1] if i + 1 < len(argv) else ""
    try:
        with open(os.path.join(ROOT, "factory.json"), encoding="utf-8") as fh:
            configured = (json.load(fh).get("dashboard") or {}).get("github_repo")
        if configured:
            return configured
    except (OSError, ValueError, AttributeError):
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
    """Write a compact list, one run per line, newest first, only whitelisted keys. Returns the run count."""
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
    if not valid_repo(repo):
        print("Not a GitHub repo name (expected owner/name): %r" % repo, file=sys.stderr)
        return 1
    try:
        pages = int(argv[argv.index("--pages") + 1]) if "--pages" in argv else 3
    except (ValueError, IndexError):
        print("--pages needs a number.", file=sys.stderr)
        return 1
    runs, seen = [], set()
    for page in range(1, pages + 1):
        try:
            batch = fetch(repo, page)
        except Exception as err:  # noqa: BLE001 - network, rate limit or proxy
            print("Could not fetch page %d for %s: %s" % (page, repo, err), file=sys.stderr)
            if page == 1:
                return 1  # nothing fetched: keep the existing cache
            break  # keep what the earlier pages gave us
        for r in batch:
            if r.get("id") not in seen:
                seen.add(r.get("id"))
                runs.append(r)
        if len(batch) < 100:
            break
    n = write(runs, "GitHub Actions runs API, " + repo, OUT)
    print("Wrote %d runs to metrics/ci-runs.json" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
