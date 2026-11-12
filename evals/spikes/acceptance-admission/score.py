"""Run the pilot's acceptance suite against each implementation; print JSON results."""
import json, os, re, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
from impls import IMPL_A, IMPL_B, MUTANTS
PILOT = sys.argv[1]

def run(src):
    d = tempfile.mkdtemp()
    shutil.copytree(os.path.join(PILOT, "textkit"), os.path.join(d, "textkit"))
    shutil.copytree(os.path.join(PILOT, "tests"), os.path.join(d, "tests"))
    with open(os.path.join(d, "textkit", "core.py"), "a") as f: f.write("\n" + src)
    with open(os.path.join(d, "textkit", "__init__.py"), "w") as f: f.write("from .core import slugify, truncate  # noqa: F401\n")
    p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests/acceptance", "-t", ".", "-v"],
                       cwd=d, capture_output=True, text=True, timeout=60)
    shutil.rmtree(d)
    bad = sorted(set(re.findall(r"^(?:FAIL|ERROR): (test_\w+)", p.stderr, re.M)))
    total = len(re.findall(r"^test_\w+ \(.*\) \.\.\. ", p.stderr, re.M))
    return {"total": total, "failing": bad}

out = {"A": run(IMPL_A), "B": run(IMPL_B), "mutants": {}}
for mid, (crit, old, new) in MUTANTS.items():
    assert IMPL_A.count(old) == 1, mid
    r = run(IMPL_A.replace(old, new))
    out["mutants"][mid] = {"criterion": crit, "killed": bool(r["failing"]), "by": r["failing"][:4]}
k = sum(m["killed"] for m in out["mutants"].values())
out["kill_rate"] = "%d/%d" % (k, len(MUTANTS))
print(json.dumps(out, indent=1))
