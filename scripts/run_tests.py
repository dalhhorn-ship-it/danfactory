#!/usr/bin/env python3
"""Run the template's unittest suite in parallel worker processes (stdlib only).

Same tests as `python3 -m unittest discover -s .factory/tests`, same exit code; output is quiet unless a
task fails. Each task is one test class (or one known-slow test on its own) run in its own process, so
tests never share interpreter state. `--serial` runs the plain unittest discover. `--summary FILE`
appends a per-task timing table (markdown) for the CI step summary. `-j N` sets workers (default: CPUs).
"""
import argparse, os, shutil, subprocess, sys, tempfile, time, unittest
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, ".factory", "tests")
# Tests worth starting first (and alone): the longest ones, so the wall time is that of the slowest one.
SLOW_FIRST = ("Adopt.test_scan_then_apply", "test_cost_is_not_double_counted", "test_fixtures_build_and_graders",
              "test_round_robin_gives_even_coverage")
# Classes whose assertions depend on thread timing (parallel fixers racing on sleeps): run alone, after the pool is
# idle, so CPU load from other test processes cannot reorder them. Still run, still in full.
TIMING_SENSITIVE = ("test_runner.Parallel",)


def ids(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from ids(t)
        elif type(t).__name__ == "ModuleSkipped":  # whole module skipped itself (SkipTest at import)
            continue
        elif type(t).__name__ == "_FailedTest":  # a module that did not import
            yield "FAILED-IMPORT:" + t._testMethodName
        else:
            yield t.id()


def plan(only=()):
    sys.path.insert(0, TESTS)
    classes, solo = {}, []
    for i in ids(unittest.defaultTestLoader.discover(TESTS)):
        if only and not i.startswith(tuple(only)):
            continue
        if i.startswith("FAILED-IMPORT:"):  # import failure: a worker reports it with the real traceback
            solo.append(i.split(":", 1)[1])
        elif any(s in i for s in SLOW_FIRST):
            solo.append(i)
        else:
            classes.setdefault(i.rsplit(".", 1)[0], []).append(i)
    quiet = [v for k, v in sorted(classes.items()) if k.startswith(TIMING_SENSITIVE)]
    pool = [[i] for i in solo] + sorted((v for k, v in classes.items() if not k.startswith(TIMING_SENSITIVE)),
                                        key=len, reverse=True)
    return pool, quiet


def run(task):
    t0 = time.time()
    # every task gets its own TMPDIR, removed afterwards: tests (and the code and subprocesses they start) leave nothing in /tmp
    tmp = tempfile.mkdtemp(prefix="rt-")
    try:
        return _run(task, tmp, t0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(task, tmp, t0):
    p = subprocess.run([sys.executable, "-W", "ignore::ResourceWarning", "-m", "unittest", "-q", *task],
                       cwd=ROOT, capture_output=True, text=True,
                       env={**{k: v for k, v in os.environ.items() if k != "TEST_SUMMARY"}, "RUN_TESTS_NESTED": "1", "TMPDIR": tmp,
                            "GIT_CONFIG_GLOBAL": os.devnull,  # hermetic: no signing or identity from ~/.gitconfig
                            "PYTHONPATH": TESTS + os.pathsep + os.environ.get("PYTHONPATH", "")})
    return task, p.returncode, time.time() - t0, p.stdout + p.stderr


def main():
    ap = argparse.ArgumentParser()
    # a run started from inside a test (the adopted-project check) gets 2 workers so the two do not starve each other
    ap.add_argument("-j", type=int, default=2 if os.environ.get("RUN_TESTS_NESTED") else os.cpu_count() or 2)
    ap.add_argument("--serial", action="store_true")
    ap.add_argument("--summary")
    ap.add_argument("only", nargs="*", help="only tests whose id starts with one of these (module or module.Class)")
    a = ap.parse_args()
    os.chdir(ROOT)
    if a.serial:
        return subprocess.call([sys.executable, "-W", "ignore::ResourceWarning", "-m", "unittest", "discover",
                                "-s", TESTS, "-q"])
    t0 = time.time()
    pool, quiet = plan(a.only)
    tasks = pool + quiet
    with ThreadPoolExecutor(max_workers=max(1, a.j)) as ex:
        results = list(ex.map(run, pool))
    results += [run(t) for t in quiet]
    bad = [r for r in results if r[1]]
    for task, _, _, out in bad:
        print(f"--- FAILED: {task[0].rsplit('.', 1)[0]} ---\n{out}", file=sys.stderr)
    total = sum(len(t) for t in tasks)
    wall = time.time() - t0
    if a.summary:
        with open(a.summary, "a") as fh:
            fh.write(f"### Tests: {total} in {len(tasks)} sets, wall {wall:.0f}s, "
                     f"{'FAILED' if bad else 'ok'}\n\n| set | tests | seconds | result |\n|---|---|---|---|\n")
            for task, rc, dt, _ in sorted(results, key=lambda r: -r[2]):
                name = task[0] if len(task) == 1 else task[0].rsplit(".", 1)[0]
                fh.write(f"| {name} | {len(task)} | {dt:.1f} | {'FAIL' if rc else 'ok'} |\n")
    print(f"tests: {total} in {len(tasks)} sets, {wall:.0f}s, "
          + (f"FAILED sets: {len(bad)}" if bad else f"{total} passed"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
