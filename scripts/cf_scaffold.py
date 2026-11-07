#!/usr/bin/env python3
"""Scaffold a Cloudflare Worker that is created automatically by the first push to main.

  python3 scripts/cf_scaffold.py [--name my-app] [--no-lock]

Writes (only if absent): wrangler.jsonc, worker/index.ts (with /version and /health),
.github/workflows/deploy-cloudflare.yml, and for projects without one a minimal package.json +
public/index.html. Fills factory.json -> integrations.deploy. Detects Vite/Lovable SPAs
(assets from ./dist, SPA fallback). Never deploys anything itself: GitHub Actions creates the
Worker on the first merge to main (route B; needs CLOUDFLARE_API_TOKEN as a `production` environment secret).
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

WORKER = '''// Cloudflare Worker entry (danfactory scaffold).
// /version proves which commit is live (deploy-watcher); /health is a cheap smoke check.
// Everything else is served from static assets (your built app).
interface Env {
  ASSETS?: { fetch(request: Request): Promise<Response> };
  GIT_SHA?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);
    if (pathname === "/version") {
      return Response.json({ sha: env.GIT_SHA ?? "dev" }, { headers: { "cache-control": "no-store" } });
    }
    if (pathname === "/health") {
      return new Response("ok", { headers: { "cache-control": "no-store" } });
    }
    return env.ASSETS ? env.ASSETS.fetch(request) : new Response("Not found", { status: 404 });
  },
};
'''

PLACEHOLDER = '''<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{name}</title></head>
<body style="font-family:system-ui;margin:3rem;max-width:40rem">
<h1>{name}</h1><p>Deployed by danfactory via git → Cloudflare. Replace public/index.html with your app.</p>
</body>
</html>
'''


def slug(s):
    s = re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")
    return (s or "app")[:54]


def load(path, default=None):
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_if_absent(rel, content, done):
    path = os.path.join(ROOT, rel)
    if os.path.exists(path):
        done.append("keep    %s (exists)" % rel)
        return False
    os.makedirs(os.path.dirname(path) or ROOT, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    done.append("create  %s" % rel)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", help="Worker name (default: factory.json project.name)")
    ap.add_argument("--no-lock", action="store_true", help="don't run npm to create package-lock.json")
    a = ap.parse_args()
    factory = load("factory.json", {})
    pkg = load("package.json")
    name = slug(a.name or factory.get("project", {}).get("name") or (pkg or {}).get("name") or os.path.basename(ROOT))
    deps = {**(pkg or {}).get("dependencies", {}), **(pkg or {}).get("devDependencies", {})}
    spa = "vite" in deps or any(os.path.exists(os.path.join(ROOT, f)) for f in ("vite.config.ts", "vite.config.js"))
    done = []

    if pkg is None:  # no Node project yet: minimal static site the Worker serves
        write_if_absent("package.json", json.dumps({
            "name": name, "private": True,
            "scripts": {"build": "echo 'static site: nothing to build'", "dev": "wrangler dev"},
            "devDependencies": {"wrangler": "^4.21.0"}}, indent=2) + "\n", done)
        write_if_absent("public/index.html", PLACEHOLDER.format(name=name), done)
    assets_dir = "./dist" if spa else "./public"
    assets = {"directory": assets_dir, "binding": "ASSETS", "run_worker_first": ["/version", "/health"]}
    if spa:
        assets["not_found_handling"] = "single-page-application"
    config = {
        "$schema": "node_modules/wrangler/config-schema.json",
        "name": name,
        "main": "worker/index.ts",
        "compatibility_date": datetime.date.today().isoformat(),
        "assets": assets,
        "observability": {"enabled": True},
    }
    write_if_absent("wrangler.jsonc", "// Cloudflare Worker config (danfactory scaffold). Deploys only via git.\n"
                    + json.dumps(config, indent=2) + "\n", done)
    write_if_absent("worker/index.ts", WORKER, done)
    with open(os.path.join(ROOT, "templates", "deploy-cloudflare.yml"), encoding="utf-8") as fh:
        write_if_absent(".github/workflows/deploy-cloudflare.yml", fh.read(), done)

    if not a.no_lock and not os.path.exists(os.path.join(ROOT, "package-lock.json")) and shutil.which("npm") \
            and not any(os.path.exists(os.path.join(ROOT, l)) for l in ("pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock")):
        r = subprocess.run(["npm", "install", "--package-lock-only", "--no-audit", "--no-fund"], cwd=ROOT,
                           capture_output=True, text=True)
        done.append("create  package-lock.json" if r.returncode == 0 else "warn    npm lockfile not created: %s" % r.stderr[-200:])

    if factory:
        d = factory.setdefault("integrations", {}).setdefault("deploy", {})
        d.update({"provider": "cloudflare", "method": "git", "route": "B-github-actions", "product": "workers",
                  "worker_name": name, "project_name": name})
        cmds = factory.setdefault("commands", {})
        cmds.setdefault("build", "")
        if not cmds["build"]:
            cmds["build"] = "npm run build"
        with open(os.path.join(ROOT, "factory.json"), "w", encoding="utf-8") as fh:
            json.dump(factory, fh, indent=2)
            fh.write("\n")
        done.append("update  factory.json integrations.deploy (worker_name=%s)" % name)

    print("\n".join(done))
    print("""
Worker '{name}' is scaffolded ({kind}). Next:
  Recommended (route A, default): connect the repo in the Cloudflare dashboard (Workers & Pages -> Create ->
     Import a repository). Cloudflare builds production and previews; GitHub holds no Cloudflare key.
     Then you can delete .github/workflows/deploy-cloudflare.yml. See .claude/skills/ship/SKILL.md.
  Route B (GitHub Actions, written to .github/workflows/deploy-cloudflare.yml):
  1. GitHub repo -> Settings -> Environments -> production: restrict deployment branches to main
     (required reviewers optional; recommended for teams). Add CLOUDFLARE_API_TOKEN there as an
     environment secret, not a repo-wide one ("Edit Cloudflare Workers" API token, not R2 keys).
     CLOUDFLARE_ACCOUNT_ID is optional; if set, use the Account ID, never a Zone ID.
  2. Branch protection on main: require the "test" check. Commit package-lock.json (production needs it).
  3. Commit, open a PR, merge -> Worker created. Route B has no PR previews (use route A or `wrangler dev`).
  4. Put the URL from the deploy log into factory.json integrations.deploy (workers_subdomain, production_url)
""".format(name=name, kind="SPA from ./dist" if spa else "static assets from ./public"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
