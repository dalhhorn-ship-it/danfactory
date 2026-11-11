#!/usr/bin/env python3
"""Scan an existing build (e.g. a Lovable/Bolt/v0 export) before adopting it into danfactory.

  python3 scripts/adopt_scan.py --target /path/to/existing-repo [--out docs/ADOPTION-REPORT.md]

Read-only on the target except for the report files it writes there
(docs/ADOPTION-REPORT.md + docs/adoption-scan.json; refused when the path goes through a symlink).
Stdlib only, no network. The target is untrusted and its code is never run: git is invoked with
the target's own config neutralised (fsmonitor, hooks, pager off; no system/global config; no
prompts; no optional locks) and the files are only read as text. Detects origin, stack, scripts, tests, CI, hosting, size, hot spots, and
security/quality signals, and turns them into findings with severities that adopt.py
seeds into docs/TECH-DEBT.md and the adopt skill turns into next-build advice.
"""
import argparse
import collections
import datetime
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adopt import open_nofollow, safe_target_path  # noqa: E402

SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".nuxt", "out", "coverage", ".venv", "venv",
             "__pycache__", ".turbo", ".vercel", ".wrangler", ".codegraph", "vendor", "target"}
CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte", ".py", ".go", ".rs", ".rb",
            ".php", ".java", ".kt", ".swift", ".sql", ".css", ".scss", ".html"}
TEST_RE = re.compile(r"(^|/)(__tests__|tests?|e2e|spec)/|\.(test|spec)\.[a-z]+$")
BOT_RE = re.compile(r"lovable|gpt-engineer|bolt|stackblitz|v0|vercel\[bot\]", re.I)
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


GIT_SAFE = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=" + os.devnull,
            "-c", "core.pager=cat", "-c", "core.untrackedCache=false", "-c", "protocol.allow=never",
            "-c", "core.sshCommand=false", "-c", "core.attributesFile=" + os.devnull]


def safe_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0", GIT_PAGER="cat")
    return env


def run(args, cwd):
    if args and args[0] == "git":
        args = GIT_SAFE + list(args[1:])
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=60, env=safe_env())
        return p.stdout if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def list_files(root):
    out = run(["git", "ls-files"], root)
    if out:
        files = [f for f in out.splitlines() if not (set(f.split("/")) & SKIP_DIRS)]
    else:
        files = []
        for d, dirs, names in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            files += [os.path.relpath(os.path.join(d, n), root) for n in names]
    return sorted(f for f in files if os.path.isfile(os.path.join(root, f)) and not os.path.islink(os.path.join(root, f)))


def read(root, rel, limit=400_000):
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def count_lines(root, rel):
    try:
        with open(os.path.join(root, rel), "rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def scan(root):
    files = list_files(root)
    pkg = {}
    if "package.json" in files:
        try:
            pkg = json.loads(read(root, "package.json"))
        except ValueError:
            pkg = {}
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    scripts = pkg.get("scripts", {}) or {}
    readme = read(root, "README.md", 20_000)
    has = lambda *names: any(n in files for n in names)  # noqa: E731
    any_prefix = lambda p: any(f.startswith(p) for f in files)  # noqa: E731

    # ---- origin
    log = run(["git", "log", "--format=%an|%ae|%cs"], root).splitlines()
    authors = collections.Counter(l.split("|")[0] for l in log if l)
    bot_commits = sum(n for a, n in authors.items() if BOT_RE.search(a))
    origin = "generic"
    evidence = []
    if "lovable-tagger" in deps or "lovable.dev" in readme or any(re.search("lovable|gpt-engineer", a, re.I) for a in authors):
        origin = "lovable"
        evidence = [e for e in ("lovable-tagger in devDependencies" if "lovable-tagger" in deps else "",
                                "README mentions lovable.dev" if "lovable.dev" in readme else "",
                                "%d commits by Lovable bot" % bot_commits if bot_commits else "") if e]
    elif any_prefix(".bolt/") or "bolt.new" in readme:
        origin, evidence = "bolt", ["bolt markers"]
    elif "v0.dev" in readme or "v0.app" in readme:
        origin, evidence = "v0", ["README mentions v0"]

    # ---- stack
    stack = []
    for key, label in (("vite", "Vite"), ("next", "Next.js"), ("react", "React"), ("vue", "Vue"), ("svelte", "Svelte"),
                       ("@sveltejs/kit", "SvelteKit"), ("astro", "Astro"), ("typescript", "TypeScript"),
                       ("tailwindcss", "Tailwind"), ("@supabase/supabase-js", "Supabase"), ("firebase", "Firebase"),
                       ("@tanstack/react-query", "React Query"), ("react-router-dom", "React Router"),
                       ("prisma", "Prisma"), ("drizzle-orm", "Drizzle"), ("stripe", "Stripe"), ("hono", "Hono")):
        if key in deps:
            stack.append(label)
    if has("components.json"):
        stack.append("shadcn/ui")
    if any_prefix("supabase/migrations/"):
        stack.append("Supabase migrations")
    if any_prefix("supabase/functions/"):
        stack.append("Supabase edge functions")
    if has("requirements.txt", "pyproject.toml"):
        stack.append("Python")
    lockfile = next((l for l in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock") if l in files), "")
    pm = {"package-lock.json": "npm", "pnpm-lock.yaml": "pnpm", "yarn.lock": "yarn", "bun.lockb": "bun", "bun.lock": "bun"}.get(lockfile, "npm")

    # ---- tests / CI / hosting
    test_files = [f for f in files if TEST_RE.search(f)]
    test_fw = [n for n in ("vitest", "jest", "@playwright/test", "cypress", "pytest") if n in deps or (n == "pytest" and "pytest" in read(root, "pyproject.toml"))]
    ci = [f for f in files if f.startswith(".github/workflows/")]
    hosting = [label for marker, label in (("vercel.json", "Vercel"), ("netlify.toml", "Netlify"), ("wrangler.toml", "Cloudflare"),
                                          ("wrangler.jsonc", "Cloudflare"), ("wrangler.json", "Cloudflare"), ("Dockerfile", "Docker"),
                                          ("fly.toml", "Fly.io"), ("render.yaml", "Render")) if marker in files]
    if origin == "lovable" and not hosting:
        hosting = ["Lovable hosting (assumed)"]

    # ---- size & hot spots
    code = [f for f in files if os.path.splitext(f)[1] in CODE_EXT]
    sizes = {f: count_lines(root, f) for f in code}
    by_dir = collections.Counter()
    for f, n in sizes.items():
        by_dir[f.split("/")[0] if "/" in f else "."] += n
    large = sorted(((f, n) for f, n in sizes.items() if n > 300 and not f.endswith((".sql", ".css"))), key=lambda x: -x[1])[:10]

    # ---- signals
    src_text = {f: read(root, f) for f in code if sizes[f] < 5000 and not TEST_RE.search(f)}
    todo = sum(len(re.findall(r"\b(TODO|FIXME|HACK|XXX)\b", t)) for t in src_text.values())
    any_count = sum(len(re.findall(r":\s*any\b|as any\b", t)) for f, t in src_text.items() if f.endswith((".ts", ".tsx")))
    console = sum(len(re.findall(r"console\.log\(", t)) for t in src_text.values())
    client_side = {f: t for f, t in src_text.items() if not f.startswith(("supabase/functions/", "server/", "api/"))}
    service_role = [f for f, t in client_side.items() if re.search(r"service_role|SUPABASE_SERVICE_ROLE", t)]
    secret_like = [f for f, t in client_side.items() if re.search(r"sk_live_[0-9a-zA-Z]{10,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}", t)]
    hardcoded_supabase = [f for f, t in src_text.items() if re.search(r"https://[a-z0-9]{10,}\.supabase\.co", t)]
    env_committed = [f for f in files if re.fullmatch(r"(.*/)?\.(env|dev\.vars)(\.[\w.-]+)?", f)
                     and not f.endswith((".example", ".sample", ".template"))]
    migrations = "\n".join(read(root, f) for f in files if f.startswith("supabase/migrations/") and f.endswith(".sql")).lower()
    tables = len(re.findall(r"create table", migrations))
    rls = len(re.findall(r"enable row level security", migrations))

    findings = []

    def add(sev, area, title, detail=""):
        findings.append({"severity": sev, "area": area, "title": title, "detail": detail})

    if service_role:
        add("critical", "security", "Supabase service_role referenced in client-side code", ", ".join(service_role[:5]))
    if secret_like:
        add("critical", "security", "Secret-looking keys in source", ", ".join(secret_like[:5]))
    if env_committed:
        add("high", "security", ".env / .dev.vars file(s) committed to git", ", ".join(env_committed))
    if tables and rls < tables:
        add("high", "security", "Row Level Security missing on some tables (%d tables, %d RLS enables)" % (tables, rls),
            "Supabase anon key is public by design; RLS policies are the access control.")
    if hardcoded_supabase:
        add("low", "config", "Supabase URL/anon key hard-coded instead of env vars", ", ".join(hardcoded_supabase[:3]))
    if not test_files:
        add("high", "quality", "No automated tests", "Add characterization tests on critical flows before refactoring.")
    elif len(test_files) < max(3, len(code) // 25):
        add("medium", "quality", "Thin test coverage (%d test files for %d code files)" % (len(test_files), len(code)))
    if not ci:
        add("medium", "delivery", "No CI workflow")
    if "test" not in scripts:
        add("medium", "delivery", "No `test` script in package.json")
    if not lockfile and pkg:
        add("medium", "delivery", "No lockfile committed (non-reproducible installs)")
    for f, n in large[:5]:
        add("medium" if n > 500 else "low", "maintainability", "Large file %s (%d lines)" % (f, n), "split by responsibility")
    if any_count > 20:
        add("low", "quality", "%d uses of `any` in TypeScript" % any_count)
    if console > 20:
        add("low", "quality", "%d console.log calls in source" % console)
    if todo:
        add("info", "quality", "%d TODO/FIXME markers" % todo)
    if origin == "lovable":
        add("info", "process", "Lovable two-way GitHub sync: decide hybrid (branches + PRs) or full move (stop editing in Lovable)")
        if "Lovable hosting (assumed)" in hosting:
            add("info", "delivery", "Hosting on Lovable: move to Cloudflare Workers static assets via git (ship skill)")
    findings.sort(key=lambda x: SEV_ORDER[x["severity"]])

    run_cmd = {"npm": "npm run", "pnpm": "pnpm", "yarn": "yarn", "bun": "bun run"}[pm]
    commands = {
        "build": "%s build" % run_cmd if "build" in scripts else "",
        "lint": "%s lint" % run_cmd if "lint" in scripts else "",
        "test": "%s test" % run_cmd if "test" in scripts else "",
        "dev": "%s dev" % run_cmd if "dev" in scripts else "",
    }
    return {
        "scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "name": clean(pkg.get("name") or os.path.basename(os.path.abspath(root))),
        "origin": origin, "origin_evidence": evidence, "stack": stack, "package_manager": pm,
        "scripts": scripts, "suggested_commands": commands,
        "tests": {"files": len(test_files), "frameworks": test_fw}, "ci": ci, "hosting": hosting,
        "size": {"files": len(files), "code_files": len(code), "code_lines": sum(sizes.values()),
                 "by_top_dir": by_dir.most_common(8)},
        "large_files": large,
        "git": {"commits": len(log), "first": log[-1].split("|")[2] if log else "", "last": log[0].split("|")[2] if log else "",
                "top_authors": authors.most_common(5), "bot_commits": bot_commits},
        "findings": findings,
    }


def clean(v):
    """Repo-derived text goes into a markdown report: no control characters or line breaks (no injected lines)."""
    return re.sub(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+", " ", str(v)).strip()


def report(s):
    sev_count = collections.Counter(f["severity"] for f in s["findings"])
    lines = [
        "# Adoption report: %s" % clean(s["name"]),
        "",
        "> Generated by danfactory `adopt_scan.py` at %s. Read-only scan; the adopt skill turns it into "
        "TECH-DEBT.md, BACKLOG.md and NEXT-BUILDS.md." % s["scanned_at"],
        "",
        "## Summary",
        "",
        "| | |", "|---|---|",
        "| Origin | %s%s |" % (s["origin"], " (" + "; ".join(clean(x) for x in s["origin_evidence"]) + ")" if s["origin_evidence"] else ""),
        "| Stack | %s |" % (", ".join(clean(x) for x in s["stack"]) or "unknown"),
        "| Size | %d files, %d code files, %s lines of code |" % (s["size"]["files"], s["size"]["code_files"], "{:,}".format(s["size"]["code_lines"])),
        "| Tests | %d test files%s |" % (s["tests"]["files"], " (" + ", ".join(clean(x) for x in s["tests"]["frameworks"]) + ")" if s["tests"]["frameworks"] else ""),
        "| CI | %s |" % (", ".join(clean(x) for x in s["ci"]) or "none"),
        "| Hosting | %s |" % (", ".join(clean(x) for x in s["hosting"]) or "unknown"),
        "| Git | %d commits (%s → %s), %d by builder bots |" % (s["git"]["commits"], s["git"]["first"] or "-", s["git"]["last"] or "-", s["git"]["bot_commits"]),
        "| Findings | %s |" % (", ".join("%d %s" % (sev_count[k], k) for k in SEV_ORDER if sev_count[k]) or "none"),
        "",
        "## Findings",
        "",
        "| Severity | Area | Finding | Detail |", "|---|---|---|---|",
    ]
    lines += ["| %s | %s | %s | %s |" % (f["severity"], f["area"], clean(f["title"]).replace("|", "\\|"), clean(f["detail"]).replace("|", "\\|"))
              for f in s["findings"]] or ["| – | – | none | |"]
    lines += ["", "## Where the code is", "", "| Top-level dir | Lines |", "|---|---:|"]
    lines += ["| %s | %s |" % (clean(d), "{:,}".format(n)) for d, n in s["size"]["by_top_dir"]]
    if s["large_files"]:
        lines += ["", "## Largest files", ""] + ["- %s (%d lines)" % (clean(f), n) for f, n in s["large_files"]]
    lines += ["", "## Suggested factory.json commands", "", "```json", json.dumps(s["suggested_commands"], indent=2), "```"]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=".")
    ap.add_argument("--out", default="docs/ADOPTION-REPORT.md")
    ap.add_argument("--print", action="store_true", dest="print_only", help="print the report, write nothing")
    a = ap.parse_args()
    root = os.path.abspath(a.target)
    if not os.path.isdir(root):
        print("no such directory: %s" % root, file=sys.stderr)
        return 2
    s = scan(root)
    text = report(s)
    if a.print_only:
        print(text)
        return 0
    rel_out = os.path.normpath(a.out)
    rel_json = os.path.join(os.path.dirname(rel_out), "adoption-scan.json")
    out, js = (safe_target_path(root, r) for r in (rel_out, rel_json))
    if out is None or js is None:
        print("refused: report path goes through a symlink or leaves the target (%s)" % rel_out, file=sys.stderr)
        return 2
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open_nofollow(out, "w") as fh:
        fh.write(text)
    with open_nofollow(js, "w") as fh:
        json.dump(s, fh, indent=1)
    print("adoption scan: %s (%s, %d findings) -> %s" % (s["name"], s["origin"], len(s["findings"]), os.path.relpath(out, root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
