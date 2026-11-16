"""Mission hardening helpers for slice Q (MISSION-8, 9, 12; docs/specs/mission-hardening.md). Stdlib only, Python 3.8+.

Standalone on purpose: it uses only the public `_mission` API passed in or imported lazily. Errors are the caller's
to catch (every caller fails open)."""
import datetime
import json
import os
import subprocess

STATE_FILE = os.path.join(".factory", "mission-state.json")
MAX_WAITS = 6  # consecutive "developers still working" blocks before the hook treats it as plain work again


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _ts(text):
    try:
        d = datetime.datetime.strptime(str(text)[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    return d.replace(tzinfo=datetime.timezone.utc)


def worktree_branches(root):
    """[(path, branch)] for every git worktree (porcelain); detached or bare entries have branch ''."""
    p = subprocess.run(["git", "-C", root, "worktree", "list", "--porcelain"],
                       capture_output=True, text=True, timeout=10, check=False)
    out, cur = [], None
    for ln in (p.stdout if p.returncode == 0 else "").splitlines() + [""]:
        if ln.startswith("worktree "):
            cur = [ln[9:], ""]
        elif ln.startswith("branch ") and cur:
            b = ln[7:]
            cur[1] = b[11:] if b.startswith("refs/heads/") else b
        elif not ln.strip() and cur:
            out.append(tuple(cur))
            cur = None
    return out


def slices_out(root, mission_branch):
    """Held signal (MISSION-8): branches of git worktrees other than this checkout that are not the mission
    branch. Slices are out when this is non-empty. Honest limit: any extra worktree counts, finished or not."""
    me = os.path.realpath(root)
    return [b for path, b in worktree_branches(root)
            if os.path.realpath(path) != me and b and b != mission_branch]


def read_waits(root):
    """`waits` from the raw state file (`_mission.load_state` only keeps its own keys)."""
    try:
        with open(os.path.join(root, STATE_FILE), encoding="utf-8") as fh:
            return int(json.load(fh).get("waits") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def held_items(its, out):
    """The open items when every one is `[~]` and slices are out; [] otherwise (a `[ ]` item means: work as today)."""
    open_ = [i for i in its if i["state"] in ("~", " ")]
    if out and open_ and all(i["state"] == "~" for i in open_):
        return open_
    return []


def second_reading_usd(root, started, end=None):
    """USD of second-reading rows in metrics/runner.jsonl with started <= ts < end (end None: no upper bound)."""
    total = 0.0
    try:
        fh = open(os.path.join(root, "metrics", "runner.jsonl"), encoding="utf-8")
    except OSError:
        return 0.0
    with fh:
        for ln in fh:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(r, dict) or r.get("kind") != "second-reading":
                continue
            t = _ts(r.get("ts"))
            if t is None or t < started or (end is not None and t >= end):
                continue
            try:
                total += float(r.get("cost_usd") or 0)
            except (TypeError, ValueError):
                pass
    return total


def window(root, mm=None):
    """(mission, end) when branch safety applies: an active mission, or a done/stopped one still inside its time
    window (started_at + hours cap). The latest end wins. None otherwise (MISSION-9)."""
    if mm is None:
        import _mission as mm
    now, best = _now(), None
    for m in mm.all_missions(root):
        if not m.get("started_at"):
            continue
        end = mm.expires_at(m)
        if m["status"] == "active" or (m["status"] in ("done", "stopped") and now < end):
            if best is None or end > best[1]:
                best = (m, end)
    return best


def staging_branch(root):
    try:
        with open(os.path.join(root, "factory.json"), encoding="utf-8") as fh:
            return ((json.load(fh).get("autonomy") or {}).get("staging_branch")) or "staging"
    except (OSError, ValueError, AttributeError):
        return "staging"
