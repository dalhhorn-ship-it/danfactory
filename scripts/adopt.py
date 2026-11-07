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

The target is untrusted. adopt.py never executes its code (the only subprocess is
`git config core.hooksPath`, which reads no hooks). Symlinks committed in the target are never
followed: every write, copy, merge and chmod goes through safe_target_path(), which refuses a path
when any existing component is a symlink or the real path leaves the target. Refused paths are
listed as "skip ... symlink" in the dry run and the apply output. Foreign files already under
.githooks/ and scripts/ are kept and listed as "note" lines, because a foreign hook will run
through core.hooksPath once applied.
"""
import argparse
import datetime
import json
import os
import shutil
import stat
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
    ("docs/specs/_TEMPLATE.md", "docs/specs/_TEMPLATE.md"),
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


def safe_target_path(target, rel):
    """Absolute path of `rel` inside `target`, or None when it is unsafe to touch.

    Unsafe: any existing component from the target root down is a symlink (lstat per component,
    so a dangling link counts), or the real path escapes realpath(target). Missing components are fine."""
    parts = [x for x in rel.replace("\\", "/").split("/") if x and x != "."]
    if os.path.isabs(rel) or ".." in parts:
        return None
    cur = target
    for part in parts:
        cur = os.path.join(cur, part)
        try:
            if stat.S_ISLNK(os.lstat(cur).st_mode):
                return None
        except FileNotFoundError:
            break
        except OSError:
            return None
    root = os.path.realpath(target)
    real = os.path.realpath(cur)
    if real != root and not real.startswith(root + os.sep):
        return None
    return os.path.join(target, rel)


def open_nofollow(path, mode, excl=False):
    """Open for writing without following a symlink at the final component (where supported)."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if excl else os.O_TRUNC) | getattr(os, "O_NOFOLLOW", 0)
    return os.fdopen(os.open(path, flags, 0o666), mode, **({} if "b" in mode else {"encoding": "utf-8"}))


class Plan:
    def __init__(self, target, apply):
        self.target, self.apply, self.actions = target, apply, []

    def note(self, kind, rel, why=""):
        if kind == "skip" and (kind, rel, why) in self.actions:
            return
        self.actions.append((kind, rel, why))

    def safe(self, rel):
        """Safe absolute path for rel, or None after recording a visible skip."""
        path = safe_target_path(self.target, rel)
        if path is None:
            self.note("skip", rel, "symlink")
        return path

    def write(self, rel, content, kind="create", why=""):
        path = self.safe(rel)
        if path is None:
            return
        self.note(kind, rel, why)
        if self.apply:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open_nofollow(path, "w") as fh:
                fh.write(content)

    def copy(self, src_rel, dst_rel):
        dst = self.safe(dst_rel)
        if dst is None:
            return
        if os.path.exists(dst):
            self.note("keep", dst_rel, "exists in project; not overwritten")
            return
        self.note("create", dst_rel)
        if self.apply:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            src = os.path.join(TEMPLATE, src_rel)
            with open(src, "rb") as fi, open_nofollow(dst, "wb", excl=True) as fo:
                shutil.copyfileobj(fi, fo)
            shutil.copymode(src, dst)


def merge_settings(plan):
    src = json.load(open(os.path.join(TEMPLATE, ".claude/settings.json")))
    rel = ".claude/settings.json"
    path = plan.safe(rel)
    if path is None:
        return
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
    path = plan.safe(rel)
    if path is None:
        return
    cur = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []
    add = [l for l in src if l.strip() and l not in cur and not l.startswith("#")]
    if add:
        plan.write(rel, "\n".join(cur + ["", "# danfactory"] + add) + "\n", "merge" if cur else "create",
                   "%d lines added" % len(add))


def merge_claude_md(plan):
    block = open(os.path.join(TEMPLATE, "CLAUDE.md"), encoding="utf-8").read()
    block = "%s\n%s\n%s\n" % (BLOCK_START, block.replace("# CLAUDE.md\n", "# danfactory operating rules\n", 1).strip(), BLOCK_END)
    path = plan.safe("CLAUDE.md")
    if path is None:
        return
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
    path = plan.safe(rel)
    if path is None:
        return
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


def foreign_files(plan, template_files):
    """List files under .githooks/ and scripts/ that the template does not ship (kept, never overwritten)."""
    for top, label in ((".githooks", "foreign hook kept: will run via core.hooksPath"),
                       ("scripts", "foreign script kept")):
        base = plan.safe(top)
        if base is None or not os.path.isdir(base):
            continue
        for d, dirs, names in os.walk(base, followlinks=False):
            rd = os.path.relpath(d, plan.target).replace(os.sep, "/")
            for x in sorted(dirs):
                if os.path.islink(os.path.join(d, x)):
                    plan.note("skip", rd + "/" + x, "symlink")
            dirs[:] = sorted(x for x in dirs if x not in SKIP_NAMES and not os.path.islink(os.path.join(d, x)))
            for n in sorted(names):
                rel = rd + "/" + n
                if n in SKIP_NAMES or n.endswith(".pyc") or rel in template_files:
                    continue
                if os.path.islink(os.path.join(d, n)):
                    plan.note("skip", rel, "symlink")
                else:
                    plan.note("note", rel, label)


def chmod_scripts(plan):
    """chmod 755 scripts and hooks without following symlinks (a link would reach outside the target)."""
    for rel in ("scripts", ".githooks", ".claude/hooks"):
        top = plan.safe(rel)
        if top is None or not os.path.isdir(top):
            continue
        for d, dirs, names in os.walk(top, followlinks=False):
            rd = os.path.relpath(d, plan.target).replace(os.sep, "/")
            for x in dirs:
                if os.path.islink(os.path.join(d, x)):
                    plan.note("skip", rd + "/" + x, "symlink")
            for n in names:
                if not (n.endswith((".py", ".sh")) or rel == ".githooks"):
                    continue
                p = os.path.join(d, n)
                if not stat.S_ISREG(os.lstat(p).st_mode):
                    plan.note("skip", rd + "/" + n, "symlink")
                    continue
                os.chmod(p, 0o755)


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
    scan_path = plan.safe("docs/adoption-scan.json")
    if scan_path and os.path.exists(scan_path):
        scan = json.load(open(scan_path))
    elif scan_path:
        plan.note("warn", "docs/adoption-scan.json", "missing: run adopt_scan.py first for seeded docs")

    template_files = set()
    for src, dst in COPY:
        for rel in tracked(src):
            if set(rel.split("/")) & SKIP_NAMES:
                continue
            template_files.add(dst + rel[len(src):])
            plan.copy(rel, dst + rel[len(src):])
    foreign_files(plan, template_files)
    for rel in SEED_IF_ABSENT:
        plan.copy(rel, rel)
    merge_settings(plan)
    merge_lines(plan, ".gitignore")
    merge_lines(plan, ".gitattributes")
    merge_claude_md(plan)
    factory_json(plan, scan)
    seed_registers(plan, scan)
    ci = open(os.path.join(TEMPLATE, ".github/workflows/ci.yml"), encoding="utf-8").read()
    ci_path = plan.safe(".github/workflows/danfactory.yml")
    if ci_path and not os.path.exists(ci_path):
        plan.write(".github/workflows/danfactory.yml", ci.replace("name: ci", "name: danfactory", 1), "create",
                   "factory checks, project tests, dashboard artifact")

    if a.apply:
        chmod_scripts(plan)
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
