#!/usr/bin/env python3
"""Merge gate: one command, one verdict with reason codes. Same locally and in CI. Stdlib only, Python 3.8+.
Design: docs/decisions/0007-merge-gate-and-acceptance-suite.md. Policy: docs/policies/merge-gate.md.

  python3 scripts/gate.py [--base REF] [--json] [--summary FILE] [--only ids] [--no-record]

Exit codes: 0 pass, 1 fail, 2 usage error. Checks run in a fixed order (CHECKS); each returns
{id, status: pass|fail|warn|skip, codes, detail, seconds}. `warn` never fails the verdict.

Base: --base, else merge-base with origin/<gate.base_branch>, else HEAD~1. An empty or all-zero --base (what CI
passes for a first push) and a base that does not resolve are treated as "not given". With no base the diff checks
(protected, review, security) report skip.

Diff scope: path checks use `git diff --name-status BASE` (committed range plus working tree changes of tracked
files) plus untracked files that are not ignored. The security scan reads only the added lines of that same
tracked diff; untracked files are scanned only once they are staged or committed.

Acceptance JSON, printed by `python3 scripts/acceptance.py run --json` (AUTO-2):
  {"tests": [{"id": str, "status": "pass|fail|error|skip"}], "admitted": [ids]}
compared with metrics/acceptance-baseline.json {"passing": [ids], ...} by compare_acceptance().
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

DEFAULTS = {"base_branch": "main", "protected": ["tests/acceptance/**"], "review": "advisory", "prd": "required",
            "security_ignore": [".factory/tests/**", "evals/**"]}
TRAILER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*):[ \t]*(.+?)[ \t]*$")
BASELINE = "metrics/acceptance-baseline.json"
MANIFEST = "tests/acceptance/manifest.json"
LOCAL = "metrics/gate.local.jsonl"
TAIL = 300


# ---------------------------------------------------------------- helpers

WRAP = None  # --sandbox (and the fixer runner) set this to sandbox.TreeSandbox.gate_wrap: (cmd, root, shell) -> (cmd, shell, env)


def sh(cmd, root, shell=False):
    """(returncode, stdout+stderr). Never raises for a missing binary."""
    env = None
    if WRAP:
        cmd, shell, env = WRAP(cmd, root, shell)
    try:
        p = subprocess.run(cmd, cwd=root, shell=shell, env=env, capture_output=True, text=True, errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except OSError as ex:
        return 127, str(ex)


def git(root, *args):
    rc, out = sh(["git", "-c", "core.quotepath=off"] + list(args), root)
    return out if rc == 0 else None


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def config(root):
    f = read_json(os.path.join(root, "factory.json"), {}) or {}
    g = dict(DEFAULTS)
    g.update(f.get("gate") or {})
    return f, g


def tail(out, n=6):
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return " | ".join(lines[-n:])[-TAIL:]


def glob_re(pat):
    out, i = "", 0
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pat.startswith("**", i):
            out, i = out + ".*", i + 2
        elif c == "*":
            out, i = out + "[^/]*", i + 1
        elif c == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(c), i + 1
    return re.compile(out)


def matches(path, pats):
    return any(glob_re(p).fullmatch(path) for p in pats)


def trailers(message):
    """{key.lower(): [values, newest first order kept as written]} from the last paragraph of a commit message.
    A one-paragraph message (subject only) has no trailers."""
    paras = [p for p in re.split(r"\n\s*\n", message.strip()) if p.strip()]
    out = {}
    if len(paras) < 2:
        return out
    for line in paras[-1].splitlines():
        m = TRAILER_RE.match(line.strip())
        if m:
            out.setdefault(m.group(1).lower(), []).append(m.group(2))
    return out


def commits(root, base, *paths):
    """Non-merge commits in base..HEAD (newest first) as [{sha, trailers}], optionally touching paths."""
    args = ["log", "--no-merges", "--format=%H%x00%B%x01", "%s..HEAD" % base]
    if paths:
        args += ["--"] + list(paths)
    out = git(root, *args)
    res = []
    for rec in (out or "").split("\x01"):
        rec = rec.strip("\n")
        if "\x00" in rec:
            sha, msg = rec.split("\x00", 1)
            res.append({"sha": sha.strip(), "trailers": trailers(msg)})
    return res


def approved_slugs(root):
    try:
        from obs import sources
        return {p["slug"] for p in sources.prds(root) if p["status"] == "approved"}
    except Exception:  # noqa: BLE001 - fall back to a plain header parse
        import glob
        res = set()
        for p in glob.glob(os.path.join(root, "docs", "specs", "*.md")):
            with open(p, encoding="utf-8", errors="replace") as fh:
                m = re.search(r"(?m)^>\s*Status:\s*([\w-]+)", fh.read())
            if m and m.group(1).lower() == "approved" and not os.path.basename(p).startswith("_"):
                res.add(os.path.basename(p)[:-3])
        return res


def valid_acceptance_change(root, tr):
    """True when a commit's trailers hold `Acceptance-Change: <slug>` for an approved PRD (and, once a manifest
    exists, a slug the manifest knows)."""
    slugs = approved_slugs(root)
    manifest = read_json(os.path.join(root, MANIFEST))
    known = set((manifest or {}).get("prds") or {}) if isinstance(manifest, dict) else None
    for slug in tr.get("acceptance-change", []):
        if slug in slugs and (known is None or slug in known):
            return True
    return False


def changes(root, base):
    """[(status, path)] of tracked changes against base (A, M, D, ...) plus untracked, not ignored files as A."""
    toks = (git(root, "diff", "--name-status", "-z", "--no-renames", base) or "").split("\0")
    res = [(toks[i][:1], toks[i + 1]) for i in range(0, len(toks) - 1, 2) if toks[i]]
    for p in (git(root, "ls-files", "--others", "--exclude-standard", "-z") or "").split("\0"):
        if p:
            res.append(("?", p))
    return res


# ---------------------------------------------------------------- pure comparison (acceptance)

def compare_acceptance(result, baseline):
    """(codes, detail) from the acceptance JSON and the baseline {"passing": [ids]}.
    acceptance-regression: a baseline id that is not passing now (fail, error, skip or missing).
    test-not-admitted: a test id in the suite that is not in `admitted`.
    Newly passing tests are informational only (fix: `acceptance.py baseline`)."""
    tests = {t.get("id"): t.get("status") for t in (result or {}).get("tests") or [] if isinstance(t, dict)}
    admitted = set((result or {}).get("admitted") or [])
    passing = set((baseline or {}).get("passing") or [])
    regress = sorted(i for i in passing if tests.get(i) != "pass")
    unadmitted = sorted(i for i in tests if i not in admitted)
    newly = sorted(i for i, s in tests.items() if s == "pass" and i not in passing)
    codes, bits = [], []
    if regress:
        codes.append("acceptance-regression")
        bits.append("regressed: " + ", ".join(regress[:5]) + (" ..." if len(regress) > 5 else ""))
    if unadmitted:
        codes.append("test-not-admitted")
        bits.append("not admitted: " + ", ".join(unadmitted[:5]) + (" ..." if len(unadmitted) > 5 else ""))
    if not bits:
        bits.append("%d tests, %d in baseline" % (len(tests), len(passing)))
    if newly:
        bits.append("%d newly passing: run `python3 scripts/acceptance.py baseline`" % len(newly))
    return codes, "; ".join(bits)


# ---------------------------------------------------------------- checks
# Each takes a context dict {root, factory, gate, base, template} and returns (status, codes, detail).

def run_cmd(cmd, root, code):
    rc, out = sh(cmd, root, shell=True)
    if rc == 0:
        return "pass", [], cmd
    return "fail", [code], "exit %d: %s" % (rc, tail(out))


def c_structure(ctx):
    if not os.path.isfile(os.path.join(ctx["root"], "scripts", "check.sh")):
        return "skip", [], "no scripts/check.sh"
    return run_cmd("bash scripts/check.sh", ctx["root"], "structure-failed")


def c_build(ctx):
    cmd = (ctx["factory"].get("commands") or {}).get("build")
    return run_cmd(cmd, ctx["root"], "build-failed") if cmd else ("skip", [], "commands.build not set")


def c_lint(ctx):
    cmd = (ctx["factory"].get("commands") or {}).get("lint")
    return run_cmd(cmd, ctx["root"], "lint-failed") if cmd else ("skip", [], "commands.lint not set")


def includes_acceptance(cmd):
    """Cheap heuristic: would commands.test discover tests/acceptance? (open issues' tests fail by design there)."""
    c = cmd or ""
    if re.search(r"ignore|exclude|deselect|skip|--dir|-k\s", c):
        return False
    if "tests/acceptance" in c:
        return True
    if "acceptance" in c:
        return False
    args = c.split()
    if re.search(r"unittest\s+discover", c):  # bare, or started from the root or tests/
        m = re.search(r"\s-s\s*(\S+)", c)
        return not m or m.group(1).strip("./") in ("", "tests")
    for i, w in enumerate(args):
        if w in ("pytest", "py.test", "vitest", "jest") and not [x for x in args[i + 1:] if not x.startswith("-") and x != "run"]:
            return True
        if w == "pytest" or w == "vitest" or w == "jest":
            return any(x.strip("./") in ("", "tests") for x in args[i + 1:] if not x.startswith("-"))
    return "go test ./..." in c


def c_tests(ctx):
    if ctx["template"]:
        return "skip", [], "covered by structure (check.sh)"
    if not (ctx["factory"].get("commands") or {}).get("test"):
        return "skip", [], "commands.test not set"
    t0 = time.monotonic()
    st, codes, detail = run_cmd("python3 scripts/metrics.py test", ctx["root"], "tests-failed")
    budget = (ctx["factory"].get("budgets") or {}).get("test_seconds")
    secs = time.monotonic() - t0
    if st == "pass" and budget and secs > budget:
        return "warn", ["tests-over-budget"], "%.0fs over the %ss budget" % (secs, budget)
    if st == "pass" and includes_acceptance(ctx["factory"]["commands"]["test"]):
        return "warn", ["tests-include-acceptance"], "commands.test would run tests/acceptance, which fails by design while issues are open: exclude it (the acceptance check runs it)"
    return st, codes, detail


def c_coverage(ctx):
    rows = []
    path = os.path.join(ctx["root"], "metrics", "history.jsonl")
    try:
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(r, dict) and r.get("kind") == "test" and r.get("scope") == "full" \
                        and isinstance(r.get("coverage_pct"), (int, float)):
                    rows.append(r["coverage_pct"])
    except OSError:
        pass
    if not rows:
        return "skip", [], "no coverage reported"
    b = ctx["factory"].get("budgets") or {}
    cur, codes = rows[-1], []
    if cur < b.get("min_coverage_pct", 0):
        codes.append("coverage-below-min")
    if len(rows) > 1 and rows[-2] - cur > b.get("max_coverage_drop_pct", 100):
        codes.append("coverage-dropped")
    return ("fail" if codes else "pass"), codes, "%.1f%% (previous %s)" % (cur, "%.1f%%" % rows[-2] if len(rows) > 1 else "none")


def c_acceptance(ctx):
    root = ctx["root"]
    have = os.path.isfile(os.path.join(root, "scripts", "acceptance.py")) and os.path.isfile(os.path.join(root, MANIFEST))
    baseline = read_json(os.path.join(root, BASELINE), {})
    if not have:
        if isinstance(baseline, dict) and baseline.get("passing"):
            return "fail", ["acceptance-error"], "baseline lists %d passing test(s) but scripts/acceptance.py or %s is missing" % (
                len(baseline["passing"]), MANIFEST)
        return "skip", [], "no acceptance suite"
    rc, out = sh(["python3", "scripts/acceptance.py", "run", "--json"], root)
    try:
        result = json.loads(out)
        if not isinstance(result, dict):
            raise ValueError
    except ValueError:
        return "fail", ["acceptance-error"], "acceptance.py run --json gave no valid JSON (exit %d): %s" % (rc, tail(out, 3))
    if result.get("error") or result.get("collection_errors"):
        why = result.get("error") or "; ".join("%s: %s" % (e.get("module"), e.get("error")) for e in result["collection_errors"][:3])
        return "fail", ["acceptance-error"], "suite did not load: " + str(why)[:TAIL]
    ctx["acceptance_passing"] = sorted(t["id"] for t in result.get("tests") or [] if isinstance(t, dict) and t.get("status") == "pass")
    codes, detail = compare_acceptance(result, baseline)
    if codes:
        return "fail", codes, detail
    warn, bits = [], []
    man = read_json(os.path.join(root, MANIFEST), {}) or {}
    nq = sum(len(v) for v in (man.get("questions") or {}).values() if isinstance(v, list))
    if nq:
        warn.append("open-prd-questions")
        bits.append("%d open PRD question(s): answer them in a PRD revision" % nq)
    try:
        import acceptance
        miss = acceptance.unmapped_criteria(root)
    except Exception:  # noqa: BLE001
        miss = {}
    if miss:
        warn.append("acceptance-unmapped")
        bits.append("criteria without a test: " + ", ".join("%s #%s" % (k, ",".join(v)) for k, v in sorted(miss.items())))
    if warn:
        return "warn", warn, detail + "; " + "; ".join(bits)
    return "pass", [], detail


def c_protected(ctx):
    root, base = ctx["root"], ctx["base"]
    if not base:
        return "skip", [], "no base to diff against"
    pats = ctx["gate"].get("protected") or []
    chg = changes(root, base)
    hit = sorted({p for _s, p in chg if matches(p, pats)})
    bad = []
    for p in hit:
        dirty = (git(root, "status", "--porcelain", "--", p) or "").strip()
        cs = commits(root, base, p)
        if dirty or not cs or not all(valid_acceptance_change(root, c["trailers"]) for c in cs):
            bad.append(p)
    codes, bits = [], []
    if bad:
        codes.append("protected-path")
        bits.append("protected paths changed without a valid Acceptance-Change trailer: " + ", ".join(bad[:5])
                    + (" ..." if len(bad) > 5 else ""))
    old = (git(root, "show", "%s:%s" % (base, BASELINE)))
    if old is not None:
        try:
            was = set(json.loads(old).get("passing") or [])
        except (ValueError, AttributeError):
            was = set()
        now = set((read_json(os.path.join(root, BASELINE), {}) or {}).get("passing") or [])
        if was - now:
            cs = commits(root, base, BASELINE)
            dirty = (git(root, "status", "--porcelain", "--", BASELINE) or "").strip()
            if dirty or not cs or not all(valid_acceptance_change(root, c["trailers"]) for c in cs):
                codes.append("baseline-shrunk")
                bits.append("baseline lost %d id(s)" % len(was - now))
    return ("fail" if codes else "pass"), codes, "; ".join(bits) or ("%d protected path(s) changed with trailer" % len(hit) if hit else "no protected path changed")


def c_review(ctx):
    mode = ctx["gate"].get("review", "advisory")
    if mode == "off":
        return "skip", [], "gate.review is off"
    if not ctx["base"]:
        return "skip", [], "no base to diff against"
    cs = commits(ctx["root"], ctx["base"])
    if not cs:
        return "skip", [], "no commits in range"
    verdict = next((c["trailers"]["review"][-1].lower() for c in cs if "review" in c["trailers"]), None)
    if verdict == "fix-first":
        return "fail", ["review-fix-first"], "latest review trailer says fix-first"
    if verdict == "ship":
        return "pass", [], "Review: ship"
    if mode == "required":
        return "fail", ["review-missing"], "no Review: ship trailer in range"
    return "warn", ["review-missing"], "no Review trailer in range (advisory)"


from gate_checks import added_lines, c_prd, c_security, c_size, scan  # noqa: E402,F401  (after the helpers: gate_checks reads them lazily)

CHECKS = (("structure", c_structure), ("build", c_build), ("lint", c_lint), ("tests", c_tests),
          ("coverage", c_coverage), ("acceptance", c_acceptance), ("protected", c_protected),
          ("prd", c_prd), ("review", c_review), ("security", c_security), ("size", c_size))


# ---------------------------------------------------------------- run

def resolve_base(root, gate, given):
    """(short sha of the base commit or None, note on why a fallback was used or "")."""
    note = ""
    if given and not re.fullmatch(r"0+", given.strip()):
        out = git(root, "rev-parse", "--verify", "--quiet", given.strip() + "^{commit}")
        if out:
            return out.strip(), ""
        note = "--base %s does not resolve to a commit" % given.strip()
    elif given:
        note = "--base is all zeros (first push)"
    mb = git(root, "merge-base", "HEAD", "origin/%s" % gate.get("base_branch", "main"))
    if mb and mb.strip() != (git(root, "rev-parse", "HEAD") or "").strip():
        return mb.strip(), (note + "; used merge-base with origin/%s" % gate.get("base_branch", "main")) if note else ""
    out = git(root, "rev-parse", "--verify", "--quiet", "HEAD~1^{commit}")
    if out:
        return out.strip(), (note + "; " if note else "") + "no origin/%s merge-base, used HEAD~1" % gate.get("base_branch", "main")
    return None, (note + "; " if note else "") + "no base commit available, diff checks skipped"


def is_template(root):
    try:
        sys.path.insert(0, os.path.join(root, ".claude", "hooks"))
        from _common import template_mode
        return bool(template_mode(root=root))
    except Exception:  # noqa: BLE001
        return False
    finally:
        sys.path.pop(0)


def run_gate(root, base=None, only=None):
    factory, gate = config(root)
    base_sha, base_note = resolve_base(root, gate, base)
    ctx = {"root": root, "factory": factory, "gate": gate, "base": base_sha, "template": is_template(root)}
    t_all, checks = time.monotonic(), []
    for cid, fn in CHECKS:
        if only and cid not in only:
            continue
        t0 = time.monotonic()
        try:
            st, codes, detail = fn(ctx)
        except Exception as ex:  # noqa: BLE001 - a crashing check must fail the gate, not hide
            st, codes, detail = "fail", [cid + "-failed"], "check crashed: %s" % ex
        row = {"id": cid, "status": st, "codes": codes, "detail": detail, "seconds": round(time.monotonic() - t0, 2)}
        if cid == "acceptance" and "acceptance_passing" in ctx:
            row["passing"] = ctx["acceptance_passing"]  # the dashboard reads it
        checks.append(row)
    sha = (git(root, "rev-parse", "--short", "HEAD") or "").strip() or None
    v = {"verdict": "fail" if any(c["status"] == "fail" for c in checks) else "pass", "sha": sha,
         "base": base_sha[:7] if base_sha else None,
         "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
         "seconds": round(time.monotonic() - t_all, 2), "checks": checks,
         "codes": list(dict.fromkeys(c for ch in checks for c in ch["codes"]))}
    if base_note:
        v["base_note"] = base_note.lstrip("; ")
    if only:
        v["only"] = sorted(only)
    return v


def record(root, v):
    os.makedirs(os.path.join(root, "metrics"), exist_ok=True)
    with open(os.path.join(root, LOCAL), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(v) + "\n")


def summary_md(v):
    rows = ["**Merge gate: %s** (%.1fs, base %s, sha %s)" % (v["verdict"].upper(), v["seconds"], v["base"] or "none", v["sha"] or "?"),
            "", "| check | status | codes | seconds |", "|---|---|---|---|"]
    for c in v["checks"]:
        rows.append("| %s | %s | %s | %.1f |" % (c["id"], c["status"], ", ".join(c["codes"]) or "-", c["seconds"]))
    bad = [c for c in v["checks"] if c["status"] in ("fail", "warn")]
    if v.get("base_note"):
        rows += ["", "base-fallback: %s" % v["base_note"]]
    if bad:
        rows += [""] + ["- `%s`: %s" % (c["id"], c["detail"].replace("|", "/")) for c in bad]
    return "\n".join(rows) + "\n"


def human(v):
    out = ["gate: %s (%.1fs) base=%s sha=%s%s" % (v["verdict"].upper(), v["seconds"], v["base"] or "none", v["sha"] or "?",
                                                   "  codes: " + ", ".join(v["codes"]) if v["codes"] else "")]
    if v.get("base_note"):
        out.append("  base-fallback: %s" % v["base_note"])
    for c in v["checks"]:
        out.append("  %-4s %-10s %5.1fs  %s%s" % (c["status"], c["id"], c["seconds"],
                                                  ("[%s] " % ",".join(c["codes"])) if c["codes"] else "", c["detail"]))
    return "\n".join(out)


def main(argv=None, root=ROOT):
    ap = argparse.ArgumentParser(prog="gate.py", description="Merge gate: one verdict with reason codes (docs/policies/merge-gate.md)")
    ap.add_argument("--base", default=None, help="ref to diff against (default: merge-base with origin/<base_branch>, else HEAD~1)")
    ap.add_argument("--json", action="store_true", help="print the verdict as JSON")
    ap.add_argument("--summary", metavar="FILE", help="write a Markdown summary (CI step summary)")
    ap.add_argument("--only", help="comma-separated check ids (%s)" % ",".join(c for c, _ in CHECKS))
    ap.add_argument("--sandbox", action="store_true", help="run build, lint, tests and the acceptance suite in bubblewrap without network "
                    "and with a scrubbed environment (the fixer runner always does)")
    ap.add_argument("--no-record", action="store_true", help="do not append to %s" % LOCAL)
    try:
        a = ap.parse_args(argv)
    except SystemExit as ex:
        return 0 if ex.code in (0, None) else 2
    only = None
    if a.only:
        only = {x.strip() for x in a.only.split(",") if x.strip()}
        unknown = only - {c for c, _ in CHECKS}
        if unknown or not only:
            print("unknown check id(s): %s (known: %s)" % (", ".join(sorted(unknown)), ", ".join(c for c, _ in CHECKS)), file=sys.stderr)
            return 2
    global WRAP
    ts = None
    if a.sandbox:
        import sandbox
        try:
            ts = sandbox.TreeSandbox(root)
        except sandbox.SandboxUnavailable as ex:
            print("gate --sandbox: %s" % ex, file=sys.stderr)
            return 2
        WRAP = ts.gate_wrap
    try:
        v = run_gate(root, a.base, only)
    finally:
        WRAP = None
        if ts:
            ts.close()
    if not a.no_record:
        try:
            record(root, v)
        except OSError as ex:
            print("could not record verdict: %s" % ex, file=sys.stderr)
    if a.summary:
        try:
            mode = "a" if os.path.abspath(a.summary) == os.path.abspath(os.environ.get("GITHUB_STEP_SUMMARY", "\0")) else "w"
            with open(a.summary, mode, encoding="utf-8") as fh:
                fh.write(summary_md(v))
        except OSError as ex:
            print("could not write summary: %s" % ex, file=sys.stderr)
    print(json.dumps(v, indent=2) if a.json else human(v))
    return 0 if v["verdict"] == "pass" else 1


if __name__ == "__main__":
    import gate  # the imported copy owns WRAP, which gate_checks reads through `import gate`
    sys.exit(gate.main())
