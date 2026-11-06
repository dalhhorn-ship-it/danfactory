#!/usr/bin/env python3
"""Install danfactory into an existing build without clobbering it.

  python3 scripts/adopt.py --target /path/to/existing-repo            # dry run: print the plan
  python3 scripts/adopt.py --target /path/to/existing-repo --apply    # do it

Run from a danfactory checkout (the adopt skill clones one to a temp dir). Rules:
  * never overwrites a file the project already has; merges instead where it is safe
    (.claude/settings.json, .gitignore, .gitattributes, CLAUDE.md block, factory.json)
  * project-owned docs (GOAL, OPERATING-MODEL, BACKLOG, TECH-DEBT) are created only if absent,
    seeded from docs/adoption-scan.json when present (run adopt_scan.py first)
  * README.md stays the project's; the template README is copied as docs/TEMPLATE-GUIDE.md
  * CI is added as .github/workflows/danfactory.yml (separate from any existing workflow)
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

TEMPLATE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BLOCK_START, BLOCK_END = "<!-- danfactory:start -->", "<!-- danfactory:end -->"

# (source in template, destination in project); directories are copied file by file
COPY = [
    (".claude/hooks", ".claude/hooks"),
    (".claude/agents", ".claude/agents"),
    (".claude/skills", ".claude/skills"),
    (".githooks", ".githooks"),
    (".factory/tests", ".factory/tests"),
    ("scripts", "scripts"),  # existing files with the same name are kept and reported
    ("templates", "templates"),
    ("docs/policies", "docs/policies"),
    ("docs/operating-model", "docs/operating-model"),
    ("docs/decisions/0000-template.md", "docs/decisions/0000-template.md"),
    ("README.md", "docs/TEMPLATE-GUIDE.md"),
]
SEED_IF_ABSENT = ["docs/GOAL.md", "docs/OPERATING-MODEL.md"]
SKIP_NAMES = {"__pycache__", ".allow-large-read"}


def on_demand_skills():
    try:
        return set(json.load(open(os.path.join(TEMPLATE, "factory.json")))["integrations"]["skills"])
    except (OSError, ValueError, KeyError):
        return {"security-audit", "cloudflare-deploy"}


def tracked(rel):
    """Template files under `rel`, without git (the installed plugin copy may not be a git checkout).

    Skips caches and the git-ignored on-demand skills (installed per project when needed)."""
    root = os.path.join(TEMPLATE, rel)
    if os.path.isfile(root):
        return [rel]
    skip_skills = {".claude/skills/" + n for n in on_demand_skills()}
    out = []
    for d, dirs, names in os.walk(root):
        rd = os.path.relpath(d, TEMPLATE).replace(os.sep, "/")
        dirs[:] = sorted(x for x in dirs if x not in SKIP_NAMES and (rd + "/" + x) not in skip_skills)
        out += [rd + "/" + n for n in sorted(names) if n not in SKIP_NAMES and not n.endswith(".pyc")]
    return out


class Plan:
    def __init__(self, target, apply):
        self.target, self.apply, self.actions = target, apply, []

    def note(self, kind, rel, why=""):
        self.actions.append((kind, rel, why))

    def write(self, rel, content, kind="create", why=""):
        self.note(kind, rel, why)
        if self.apply:
            path = os.path.join(self.target, rel)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)

    def copy(self, src_rel, dst_rel):
        dst = os.path.join(self.target, dst_rel)
        if os.path.exists(dst):
            self.note("keep", dst_rel, "exists in project; not overwritten")
            return
        self.note("create", dst_rel)
        if self.apply:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(TEMPLATE, src_rel), dst)


def merge_settings(plan):
    src = json.load(open(os.path.join(TEMPLATE, ".claude/settings.json")))
    rel = ".claude/settings.json"
    path = os.path.join(plan.target, rel)
    if not os.path.exists(path):
        plan.write(rel, json.dumps(src, indent=2) + "\n")
        return
    cur = json.load(open(path))
    for k, v in src.get("env", {}).items():
        cur.setdefault("env", {}).setdefault(k, v)
    perms = cur.setdefault("permissions", {})
    for key in ("allow", "deny"):
        merged = perms.get(key, [])
        merged += [x for x in src["permissions"].get(key, []) if x not in merged]
        perms[key] = merged
    hooks = cur.setdefault("hooks", {})
    for event, groups in src.get("hooks", {}).items():
        existing = json.dumps(hooks.get(event, []))
        hooks.setdefault(event, [])
        hooks[event] += [g for g in groups if g["hooks"][0]["command"] not in existing]
    plan.write(rel, json.dumps(cur, indent=2) + "\n", "merge", "env, permissions and hooks added")


def merge_lines(plan, rel):
    src = open(os.path.join(TEMPLATE, rel), encoding="utf-8").read().splitlines()
    path = os.path.join(plan.target, rel)
    cur = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []
    add = [l for l in src if l.strip() and l not in cur and not l.startswith("#")]
    if add:
        plan.write(rel, "\n".join(cur + ["", "# danfactory"] + add) + "\n", "merge" if cur else "create",
                   "%d lines added" % len(add))


def merge_claude_md(plan):
    block = open(os.path.join(TEMPLATE, "CLAUDE.md"), encoding="utf-8").read()
    block = "%s\n%s\n%s\n" % (BLOCK_START, block.replace("# CLAUDE.md\n", "# danfactory operating rules\n", 1).strip(), BLOCK_END)
    path = os.path.join(plan.target, "CLAUDE.md")
    if not os.path.exists(path):
        plan.write("CLAUDE.md", block)
        return
    cur = open(path, encoding="utf-8").read()
    if BLOCK_START in cur:
        start, end = cur.index(BLOCK_START), cur.index(BLOCK_END) + len(BLOCK_END)
        plan.write("CLAUDE.md", cur[:start] + block.strip() + cur[end:], "merge", "danfactory block refreshed")
    else:
        plan.write("CLAUDE.md", cur.rstrip() + "\n\n" + block, "merge", "danfactory block appended; your rules kept above it")


def factory_json(plan, scan):
    rel = "factory.json"
    tpl = json.load(open(os.path.join(TEMPLATE, rel)))
    path = os.path.join(plan.target, rel)
    if os.path.exists(path):
        plan.note("keep", rel, "exists; review commands/budgets by hand")
        return
    tpl["project"]["name"] = scan.get("name", os.path.basename(plan.target)) if scan else os.path.basename(plan.target)
    tpl["phase"] = "brainstorm"
    tpl["adopted"] = {"from": scan.get("origin", "unknown") if scan else "unknown",
                      "on": datetime.date.today().isoformat(), "template_version": tpl["template"]["decision_tree_version"]}
    if scan:
        for k, v in scan.get("suggested_commands", {}).items():
            if k in tpl["commands"] and v:
                tpl["commands"][k] = v
    plan.write(rel, json.dumps(tpl, indent=2) + "\n", "create", "seeded from the scan" if scan else "")


def seed_registers(plan, scan):
    if not os.path.exists(os.path.join(plan.target, "docs/TECH-DEBT.md")):
        lines = ["# Tech debt register", "",
                 "> Seeded from docs/ADOPTION-REPORT.md when the build was adopted; curate it. The dashboard reads this file.",
                 "", "Format: `- [ ] TD-NNN Title — impact: high|medium|low · effort: S|M|L · area: <area>`", "", "## Open", ""]
        impact = {"critical": "high", "high": "high", "medium": "medium", "low": "low"}
        n = 0
        for f in (scan or {}).get("findings", []):
            if f["severity"] in impact:
                n += 1
                lines.append("- [ ] TD-%03d %s — impact: %s · effort: M · area: %s" % (n, f["title"], impact[f["severity"]], f["area"]))
        lines += ["", "## Resolved", ""]
        plan.write("docs/TECH-DEBT.md", "\n".join(lines) + "\n", "create", "%d items from the scan" % n)
    if not os.path.exists(os.path.join(plan.target, "docs/BACKLOG.md")):
        sec = [f for f in (scan or {}).get("findings", []) if f["severity"] in ("critical", "high")]
        lines = ["# Backlog", "",
                 "> Milestones and work items; the dashboard reads this file. Seeded at adoption: M0 records what exists, "
                 "M1 makes it safe to change. The product-manager agent refines it.", "",
                 "Items: `- [ ]` todo · `- [~]` doing · `- [x]` done · `- [!]` blocked · `- [-]` dropped. Optional `(S|M|L)` and `#tags`.", "",
                 "## Milestone: M0 — Adopted into danfactory (target: %s)" % datetime.date.today().isoformat(),
                 "- [x] Existing build scanned (docs/ADOPTION-REPORT.md) #adopt",
                 "- [x] danfactory installed (hooks, agents, docs index, dashboard) #adopt",
                 "- [ ] Goal confirmed from the as-built state (docs/GOAL.md) #process",
                 "- [ ] Operating model chosen (docs/OPERATING-MODEL.md) #process", "",
                 "## Milestone: M1 — Safe to change (target: )"]
        lines += ["- [ ] Fix: %s (M) #security" % f["title"] for f in sec if f["area"] == "security"]
        lines += ["- [ ] Characterization tests for the critical user flows (M) #quality",
                  "- [ ] CI runs lint + tests on every PR (S) #delivery",
                  "- [ ] Deploy via git to Cloudflare with preview URLs (M) #delivery", "",
                  "## Unplanned", ""]
        plan.write("docs/BACKLOG.md", "\n".join(lines) + "\n", "create", "seeded from the scan")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    target = os.path.abspath(a.target)
    if os.path.samefile(target, TEMPLATE):
        print("target is the template itself", file=sys.stderr)
        return 2
    plan = Plan(target, a.apply)
    scan = None
    scan_path = os.path.join(target, "docs/adoption-scan.json")
    if os.path.exists(scan_path):
        scan = json.load(open(scan_path))
    else:
        plan.note("warn", "docs/adoption-scan.json", "missing: run adopt_scan.py first for seeded docs")

    for src, dst in COPY:
        for rel in tracked(src):
            if set(rel.split("/")) & SKIP_NAMES:
                continue
            plan.copy(rel, dst + rel[len(src):])
    for rel in SEED_IF_ABSENT:
        plan.copy(rel, rel)
    merge_settings(plan)
    merge_lines(plan, ".gitignore")
    merge_lines(plan, ".gitattributes")
    merge_claude_md(plan)
    factory_json(plan, scan)
    seed_registers(plan, scan)
    ci = open(os.path.join(TEMPLATE, ".github/workflows/ci.yml"), encoding="utf-8").read()
    if not os.path.exists(os.path.join(target, ".github/workflows/danfactory.yml")):
        plan.write(".github/workflows/danfactory.yml", ci.replace("name: ci", "name: danfactory", 1), "create",
                   "factory checks, project tests, dashboard artifact")

    if a.apply:
        for rel in ("scripts", ".githooks", ".claude/hooks"):
            for d, _, names in os.walk(os.path.join(target, rel)):
                for n in names:
                    if n.endswith((".py", ".sh")) or rel == ".githooks":
                        os.chmod(os.path.join(d, n), 0o755)
        subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=target, check=False)

    counts = {}
    for kind, rel, why in plan.actions:
        counts[kind] = counts.get(kind, 0) + 1
    print("%s: %s" % ("APPLIED" if a.apply else "DRY RUN", ", ".join("%d %s" % (v, k) for k, v in sorted(counts.items()))))
    for kind, rel, why in plan.actions:
        if kind != "create" or not rel.startswith((".claude/", "scripts/", "docs/operating-model/", ".factory/", "templates/", "docs/policies/")):
            print("  %-6s %s%s" % (kind, rel, "  — " + why if why else ""))
    if not a.apply:
        print("\nRe-run with --apply to make these changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
