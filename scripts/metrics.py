#!/usr/bin/env python3
"""Delivery & token metrics: record runs, then report trends + improvement suggestions.

  python3 scripts/metrics.py test [--affected]          run tests (+coverage), record time/result
  python3 scripts/metrics.py deploy [--env prod]        run commands.deploy, record time/result
  python3 scripts/metrics.py deploy --seconds 312 --status ok   record an external deploy (CI)
  python3 scripts/metrics.py report                     write metrics/REPORT.md (alerts + suggestions)

Each command also regenerates dashboard/ (scripts/dashboard.py) unless --no-dashboard.

Commands and budgets live in factory.json. History is append-only JSONL in metrics/ and is
committed, so trends survive ephemeral (cloud) sessions. Test output is truncated to the tail
on failure so the agent's context isn't flooded.
"""
import argparse
import datetime
import json
import os
import re
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MDIR = os.path.join(ROOT, "metrics")
HISTORY = os.path.join(MDIR, "history.jsonl")
TOKENS = os.path.join(MDIR, "tokens.jsonl")
REPORT = os.path.join(MDIR, "REPORT.md")
TAIL = 40


def factory():
    with open(os.path.join(ROOT, "factory.json"), encoding="utf-8") as fh:
        return json.load(fh)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def git_sha():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=False).stdout.strip() or None
    except OSError:
        return None


def append(path, row):
    os.makedirs(MDIR, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def load(path):
    rows = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    return rows


# ---------- coverage parsing ----------

def _json(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _istanbul(p):
    return _json(p)["total"]["lines"]["pct"]


def _coveragepy_json(p):
    return _json(p)["totals"]["percent_covered"]


def _cobertura(p):
    return float(ET.parse(p).getroot().get("line-rate")) * 100


def _lcov(p):
    found = hit = 0
    with open(p, encoding="utf-8") as fh:
        lines = fh.readlines()
    for line in lines:
        if line.startswith("LF:"):
            found += int(line[3:])
        elif line.startswith("LH:"):
            hit += int(line[3:])
    return 100.0 * hit / found if found else None


def _jacoco(p):
    for c in ET.parse(p).getroot().findall("counter"):
        if c.get("type") == "LINE":
            m, h = int(c.get("missed")), int(c.get("covered"))
            return 100.0 * h / (m + h) if m + h else None


PARSERS = {"istanbul": _istanbul, "coveragepy": _coveragepy_json, "cobertura": _cobertura,
           "lcov": _lcov, "jacoco": _jacoco}
AUTO = [("coverage/coverage-summary.json", "istanbul"), ("coverage.json", "coveragepy"),
        ("coverage.xml", "cobertura"), ("coverage/cobertura-coverage.xml", "cobertura"),
        ("coverage/lcov.info", "lcov"), ("lcov.info", "lcov"),
        ("target/site/jacoco/jacoco.xml", "jacoco"), ("build/reports/jacoco/test/jacocoTestReport.xml", "jacoco")]


def coverage(cfg):
    fmt, path = cfg.get("format", "auto"), cfg.get("file", "")
    candidates = [(path, fmt)] if path and fmt != "auto" else AUTO
    for p, f in candidates:
        full = os.path.join(ROOT, p)
        if os.path.isfile(full):
            try:
                v = PARSERS[f](full)
                return round(float(v), 2) if v is not None else None
            except Exception:  # noqa: BLE001 - a bad report should not fail the run
                return None
    return None


# ---------- run & record ----------

def run(cmd):
    t0 = time.monotonic()
    proc = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True)
    secs = round(time.monotonic() - t0, 2)
    return proc.returncode, secs, (proc.stdout + proc.stderr).splitlines()


def counts(lines):
    text = "\n".join(lines[-200:])
    out = {}
    for key, pat in (("passed", r"(\d+) passed"), ("failed", r"(\d+) failed"), ("skipped", r"(\d+) skipped")):
        m = re.findall(pat, text)
        if m:
            out[key] = int(m[-1])
    return out


def cmd_test(a, f):
    key = "test_affected" if a.affected else ("coverage" if f["commands"].get("coverage") else "test")
    cmd = f["commands"].get(key) or f["commands"].get("test")
    if not cmd:
        print("factory.json commands.test is empty -- set it (the choose-path skill does this).")
        return 2
    code, secs, lines = run(cmd)
    row = {"ts": now(), "kind": "test", "scope": "affected" if a.affected else "full", "sha": git_sha(),
           "command": cmd, "ok": code == 0, "seconds": secs, **counts(lines)}
    if not a.affected:
        row["coverage_pct"] = coverage(f.get("coverage_report", {}))
    append(HISTORY, row)
    budget = f["budgets"]["affected_test_seconds" if a.affected else "test_seconds"]
    print("tests %s in %.1fs (budget %ss)%s" % ("PASSED" if row["ok"] else "FAILED", secs, budget,
          "" if row.get("coverage_pct") is None else ", coverage %.1f%%" % row["coverage_pct"]))
    if not row["ok"] or a.verbose:
        print("--- last %d lines ---" % TAIL)
        print("\n".join(lines[-TAIL:]))
    return code


def cmd_deploy(a, f):
    if a.seconds is not None:
        ok, secs = a.status == "ok", a.seconds
    else:
        cmd = f["commands"].get("deploy")
        if not cmd:
            print("factory.json commands.deploy is empty.")
            return 2
        code, secs, lines = run(cmd)
        ok = code == 0
        if not ok:
            print("\n".join(lines[-TAIL:]))
    append(HISTORY, {"ts": now(), "kind": "deploy", "env": a.env, "sha": git_sha(), "ok": ok, "seconds": secs})
    print("deploy %s in %.1fs" % ("OK" if ok else "FAILED", secs))
    return 0 if ok else 1


# ---------- report ----------

def wt(row):
    """Cost-weighted tokens (input-equivalents); falls back for rows recorded before weighting existed."""
    if "weighted_tokens" in row:
        return row["weighted_tokens"]
    return round(row.get("input_tokens", 0) + 5 * row.get("output_tokens", 0)
                 + 1.25 * row.get("cache_creation_input_tokens", 0) + 0.1 * row.get("cache_read_input_tokens", 0))


def med(xs):
    return statistics.median(xs) if xs else None


def analyse(f, hist, toks):
    b = f["budgets"]
    alerts, ideas, table = [], [], []
    full = [r for r in hist if r["kind"] == "test" and r.get("scope") == "full"]
    aff = [r for r in hist if r["kind"] == "test" and r.get("scope") == "affected"]
    deps = [r for r in hist if r["kind"] == "deploy"]

    if not f["commands"].get("test"):
        ideas.append("Set `commands.test` in factory.json so test time and coverage are tracked.")
    if full:
        last = full[-1]
        prev = [r["seconds"] for r in full[-11:-1]]
        table.append(("Full test run", "%.1fs" % last["seconds"], "%ss" % b["test_seconds"],
                      "median %.1fs (n=%d)" % (med(prev), len(prev)) if prev else "-"))
        if last["seconds"] > b["test_seconds"]:
            alerts.append("Full tests take %.0fs (budget %ss)." % (last["seconds"], b["test_seconds"]))
            ideas += [
                "Run only affected tests in the inner loop: set `commands.test_affected` "
                "(e.g. `git diff --name-only HEAD | codegraph affected --stdin --quiet | xargs <runner>`).",
                "Parallelise the runner (pytest -n auto, vitest/jest workers, go test -p, gradle --parallel).",
                "Tag slow/integration tests and keep them out of the inner loop; run them in CI only.",
                "Delegate test runs to the `test-runner` subagent so long logs never enter the main context.",
            ]
        if prev and last["seconds"] > 1.25 * med(prev):
            alerts.append("Test time up %.0f%% vs recent median." % (100 * (last["seconds"] / med(prev) - 1)))
            ideas.append("Find the new slow tests (pytest --durations=15, vitest --reporter=verbose, jest --verbose).")
        cov = [r["coverage_pct"] for r in full if r.get("coverage_pct") is not None]
        if cov:
            table.append(("Coverage", "%.1f%%" % cov[-1], ">= %s%%" % b["min_coverage_pct"],
                          "prev %.1f%%" % cov[-2] if len(cov) > 1 else "-"))
            if cov[-1] < b["min_coverage_pct"]:
                alerts.append("Coverage %.1f%% below %s%%." % (cov[-1], b["min_coverage_pct"]))
                ideas.append("Add tests for the least-covered changed files first (diff coverage beats total coverage).")
            if len(cov) > 1 and cov[-2] - cov[-1] > b["max_coverage_drop_pct"]:
                alerts.append("Coverage dropped %.1f pts." % (cov[-2] - cov[-1]))
        elif f["commands"].get("coverage"):
            ideas.append("Coverage command set but no report found: set `coverage_report.file`/`format` in factory.json.")
        by_sha = {}
        for r in full:
            if r.get("sha"):
                by_sha.setdefault(r["sha"], set()).add(r["ok"])
        flaky = [s for s, oks in by_sha.items() if oks == {True, False}]
        if flaky:
            alerts.append("Possible flaky tests: same commit both passed and failed (%s)." % ", ".join(flaky[-3:]))
            ideas.append("Quarantine-by-fixing: reproduce flaky tests with repeated runs; don't skip them.")
        recent = full[-10:]
        rate = 100.0 * sum(not r["ok"] for r in recent) / len(recent)
        table.append(("Test failure rate (last %d)" % len(recent), "%.0f%%" % rate, "-", "-"))
    if aff:
        last = aff[-1]
        table.append(("Affected test run", "%.1fs" % last["seconds"], "%ss" % b["affected_test_seconds"], "-"))
        if last["seconds"] > b["affected_test_seconds"]:
            alerts.append("Affected tests take %.0fs (budget %ss)." % (last["seconds"], b["affected_test_seconds"]))
    if deps:
        last = deps[-1]
        recent = deps[-10:]
        fail = 100.0 * sum(not r["ok"] for r in recent) / len(recent)
        table.append(("Deploy duration", "%.0fs" % last["seconds"], "%ss" % b["deploy_seconds"],
                      "%d deploys, %.0f%% failed (last 10)" % (len(deps), fail)))
        if last["seconds"] > b["deploy_seconds"]:
            alerts.append("Deploy takes %.0fs (budget %ss)." % (last["seconds"], b["deploy_seconds"]))
            ideas += [
                "Skip docs/metrics-only builds (Workers Builds watch paths / paths-ignore) and turn on the build cache.",
                "Test once: run tests on the PR; let main only build + deploy (see templates/deploy-cloudflare.yml).",
                "Never wait on the build: push, launch deploy-watcher in the background (docs/policies/async-delivery.md).",
            ]
        if fail > 20:
            alerts.append("Deploy failure rate %.0f%% over last %d." % (fail, len(recent)))
            ideas.append("Add a pre-deploy smoke check (engineering:deploy-checklist) and make deploys idempotent.")
    if toks:
        last = toks[-1]
        recent = toks[-10:]
        avg = sum(wt(r) for r in recent) / len(recent)
        cached = sum(r.get("cache_read_input_tokens", 0) for r in recent)
        inp = cached + sum(r.get("input_tokens", 0) + r.get("cache_creation_input_tokens", 0) for r in recent)
        hit = 100.0 * cached / inp if inp else 0
        warn = b.get("session_weighted_tokens_warn", 750000)
        sub = sum(r.get("subagent_weighted_tokens", 0) for r in recent)
        table.append(("Weighted tokens / session (avg last %d)" % len(recent), "{:,.0f}".format(avg),
                      "{:,}".format(warn), "cache hit %.0f%%, subagents %.0f%%" % (
                          hit, 100.0 * sub / max(1, sum(wt(r) for r in recent)))))
        if wt(last) > warn:
            alerts.append("Last session cost {:,} weighted tokens (budget {:,}).".format(wt(last), warn))
            ideas += [
                "Delegate exploration to `bulk-reader` / Explore subagents; keep the main context for decisions.",
                "Use docs/INDEX.md + targeted reads; enable codegraph for code navigation.",
                "Start a fresh session per task (/clear) instead of one long session.",
            ]
        if inp and hit < 50:
            ideas.append("Low prompt-cache hit rate: keep CLAUDE.md stable, avoid editing it mid-session, batch tool calls.")
    if hist:
        last_ts = datetime.datetime.fromisoformat(hist[-1]["ts"])
        if (datetime.datetime.now(datetime.timezone.utc) - last_ts).days > 14:
            ideas.append("No delivery metrics for 14+ days: run `python3 scripts/metrics.py test`.")
    return alerts, list(dict.fromkeys(ideas)), table


def cmd_report(a, f):
    alerts, ideas, table = analyse(f, load(HISTORY), load(TOKENS))
    out = ["# Metrics report (generated)", "",
           "> Generated by `python3 scripts/metrics.py report` at %s. Lines starting `- ALERT` are surfaced "
           "at session start." % now(), "", "## Status", ""]
    if table:
        out += ["| Metric | Last | Budget | Context |", "|---|---|---|---|"]
        out += ["| %s | %s | %s | %s |" % r for r in table]
    else:
        out.append("No data yet. Run `python3 scripts/metrics.py test`.")
    out += ["", "## Alerts", ""] + (["- ALERT " + x for x in alerts] or ["- none"])
    out += ["", "## Suggested improvements", ""] + (["- " + x for x in ideas] or ["- none"])
    os.makedirs(MDIR, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print("\n".join(out[out.index("## Alerts"):]))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("test")
    t.add_argument("--affected", action="store_true")
    t.add_argument("--verbose", action="store_true")
    d = sub.add_parser("deploy")
    d.add_argument("--env", default="default")
    d.add_argument("--seconds", type=float)
    d.add_argument("--status", choices=["ok", "fail"], default="ok")
    sub.add_parser("report")
    ap.add_argument("--no-dashboard", action="store_true", help="skip regenerating dashboard/")
    a = ap.parse_args()
    f = factory()
    code = {"test": cmd_test, "deploy": cmd_deploy, "report": cmd_report}[a.cmd](a, f)
    if not a.no_dashboard:
        refresh_dashboard()
    return code


def refresh_dashboard():
    """Every recorded build refreshes dashboard/ so it never lags the metrics."""
    try:
        import dashboard
        dashboard.build()
    except Exception as exc:  # noqa: BLE001 - the dashboard must never fail a test/deploy run
        print("dashboard not refreshed: %s" % exc, file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
