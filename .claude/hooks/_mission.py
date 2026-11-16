"""Mission rules (ADR 0012, docs/policies/mission.md), shared by the PRD guard, the `prd` gate check, the Stop hook,
branch safety, the report and scripts/mission.py. Pure functions, stdlib only. With no docs/missions/ every
function is a no-op or returns None, so a project without a mission behaves exactly as before."""
import datetime
import json
import os
import re
import subprocess
import tempfile

MISSIONS_DIR = "docs/missions"
STATE_FILE = ".factory/mission-state.json"
DEFAULTS = {"features": 5, "usd": 15.0, "hours": 10.0, "continuations": 40}
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
START, END = "<!-- mission:start -->", "<!-- mission:end -->"
REQUIRED = ("slug", "status", "go", "date", "started_at", "branch", "milestone", "scope_in", "scope_out")
STATUSES = ("active", "stopped", "done")
KEY_RE = re.compile(r"^([a-z_]+):\s*(.*?)\s*$")
ITEM_RE = re.compile(r"^\s*-\s*\[([ ~x!\-])\]\s*(?:([A-Z][A-Z0-9]*-\d+)\b)?\s*(.*)$")


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _write_atomic(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _dt(text):
    try:
        d = datetime.datetime.fromisoformat((text or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def _num(text, default, kind=float):
    try:
        return kind(text)
    except (TypeError, ValueError):
        return default


def parse_header(text):
    """{key: raw value} from the lines between the mission markers ({} when there are none)."""
    a, b = text.find(START), text.find(END)
    if a < 0 or b < a:
        return {}
    out = {}
    for ln in text[a + len(START):b].splitlines():
        m = KEY_RE.match(ln.strip())
        if m:
            out.setdefault(m.group(1), m.group(2))
    return out


def _build(raw, path, text):
    caps = {k: DEFAULTS[k] for k in ("usd", "hours", "continuations")}
    for k, v in re.findall(r"(usd|hours|continuations)\s*=\s*([\d.]+)", raw.get("caps", "")):
        caps[k] = _num(v, caps[k], int if k == "continuations" else float)
    h = re.search(r"(?m)^#\s+(?:Mission:\s*)?(.+?)\s*$", text)
    m = {"slug": raw.get("slug", ""), "title": h.group(1) if h else "", "status": raw.get("status", "").lower(),
         "go": raw.get("go", ""), "date": raw.get("date", ""), "started_at": _dt(raw.get("started_at")),
         "branch": raw.get("branch", ""), "milestone": raw.get("milestone", ""),
         "features": _num(raw.get("features"), DEFAULTS["features"], int), "caps": caps,
         "scope_in": raw.get("scope_in", ""), "scope_out": raw.get("scope_out", ""), "path": path}
    m["missing"] = [k for k in REQUIRED if not raw.get(k)]
    return m


def load(root, slug):
    """The mission in docs/missions/<slug>.md as a dict, or None (no such file, bad slug, no header block)."""
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug) or slug.endswith("-report"):
        return None
    path = os.path.join(root, MISSIONS_DIR, slug + ".md")
    text = _read(path)
    raw = parse_header(text)
    return _build(raw, path, text) if raw else None


def all_missions(root):
    try:
        names = sorted(os.listdir(os.path.join(root, MISSIONS_DIR)))
    except OSError:
        return []
    out = [load(root, n[:-3]) for n in names if n.endswith(".md")]
    return [m for m in out if m]


def active(root):
    """The earliest-started mission with status active, or None."""
    live = [m for m in all_missions(root) if m["status"] == "active"]
    far = datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)
    return min(live, key=lambda m: (m["started_at"] or far, m["slug"])) if live else None


def go_valid(quote):
    """True when the go is quoted (straight or curly quotes) and the quoted words contain the word "go"."""
    m = re.fullmatch(r'\s*["“](.+?)["”]\s*', quote or "", re.S)
    return bool(m) and bool(re.search(r"\bgo\b", m.group(1), re.I))


def expires_at(m):
    return m["started_at"] + datetime.timedelta(hours=m["caps"]["hours"])


def _git(root, *args):
    try:
        p = subprocess.run(["git"] + list(args), cwd=root, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def _first_commit_header(root, rel):
    shas = (_git(root, "log", "--diff-filter=A", "--format=%H", "--", rel) or "").split()
    if not shas:
        return None
    return parse_header(_git(root, "show", "%s:%s" % (shas[-1], rel)) or "")


def validate(root, m):
    """'' when the mission is valid, else the reason. Valid = complete header, a real quoted go, consistent dates, and
    committed with every key except `status` unchanged since its first commit."""
    if not m:
        return "no such mission"
    if m["missing"]:
        return "header incomplete: missing " + ", ".join(m["missing"])
    if not SLUG_RE.fullmatch(m["slug"]) or m["slug"].endswith("-report") or m["slug"] + ".md" != os.path.basename(m["path"]):
        return "slug does not match the file name or the slug rules"
    if m["status"] not in STATUSES:
        return "status must be one of " + "|".join(STATUSES)
    if not go_valid(m["go"]):
        return 'go must quote the user\'s words and contain the word "go"'
    if m["started_at"] is None:
        return "started_at is not a UTC ISO time"
    if m["started_at"] > _now():
        return "started_at is in the future"
    if m["date"] != m["started_at"].astimezone(datetime.timezone.utc).date().isoformat():
        return "date is not the date of started_at"
    rel = "%s/%s.md" % (MISSIONS_DIR, m["slug"])
    first = _first_commit_header(root, rel)
    if first is None:
        return "the mission file is not committed yet"
    now = parse_header(_read(m["path"]))
    for k in sorted((set(first) | set(now)) - {"status"}):
        if first.get(k) != now.get(k):
            return "`%s` changed since the first commit (a new scope or cap needs a new mission and a new go)" % k
    return ""


def load_state(root, slug):
    fresh = {"slug": slug, "continuations": 0, "sessions": {}, "ended": None}
    try:
        st = json.loads(_read(os.path.join(root, STATE_FILE)))
    except ValueError:
        return fresh
    if not isinstance(st, dict) or st.get("slug") != slug:
        return fresh
    out = dict(fresh, **{k: st[k] for k in fresh if k in st})
    if not isinstance(out["sessions"], dict):
        out["sessions"] = {}
    out["continuations"] = _num(out["continuations"], 0, int)
    return out


def save_state(root, state):
    _write_atomic(os.path.join(root, STATE_FILE), json.dumps(state, indent=1, sort_keys=True) + "\n")


def spent(state):
    """Estimated USD over all sessions recorded in the state."""
    return sum(_num(v, 0.0) for v in (state.get("sessions") or {}).values())


def cap_hit(m, state, now=None):
    """'' or the first cap that stops the mission: stopped (status not active), wall-clock, budget, continuations."""
    now = now or _now()
    if m["status"] != "active":
        return "stopped"
    if m["started_at"] is not None and now >= expires_at(m):
        return "wall-clock"
    if spent(state) >= m["caps"]["usd"]:
        return "budget"
    if state.get("continuations", 0) >= m["caps"]["continuations"]:
        return "continuations"
    return "stopped" if state.get("ended") else ""


def _milestone_lines(root, milestone):
    """Backlog lines under `## Milestone: <milestone>...` up to the next `## ` heading."""
    out, inside = [], False
    key = re.escape(milestone.strip())
    for ln in _read(os.path.join(root, "docs", "BACKLOG.md")).splitlines():
        if ln.startswith("## "):
            inside = bool(key) and bool(re.match(r"##\s+Milestone:\s*%s(?![\w-])" % key, ln))
        elif inside:
            out.append(ln)
    return out


def items(root, m):
    """[{id, title, state, slugs}] for the checkbox items under the mission's milestone."""
    res = []
    for ln in _milestone_lines(root, m["milestone"]):
        mm = ITEM_RE.match(ln)
        if mm:
            res.append({"id": mm.group(2) or "", "title": mm.group(3).strip(), "state": mm.group(1),
                        "slugs": re.findall(r"docs/specs/([\w.-]+)\.md", ln), "line": ln})
    return res


def next_item(root, m):
    """First `[~]` item, else the first `[ ]`; a PLAN step for an empty milestone; None when all are closed."""
    its = items(root, m)
    if not its:
        return {"id": "PLAN", "title": "PM adds up to %d items for this mission to the milestone %s, within scope"
                % (m["features"], m["milestone"]), "state": " ", "slugs": []}
    for st in ("~", " "):
        for it in its:
            if it["state"] == st:
                return it
    return None


def _scoped_slugs(root, m):
    seen = []
    for it in items(root, m):
        for s in it["slugs"]:
            if s.startswith(m["slug"] + "-") and s not in seen:
                seen.append(s)
    return seen


def in_scope(root, m, spec):
    """Mechanical scope: slug prefixed `<mission>-`, linked from an item under the milestone, among the first
    `features` such slugs in file order."""
    return spec in _scoped_slugs(root, m)[:m["features"]]


def mission_of(status_line):
    mm = re.search(r"\bby mission\s+([a-z0-9][a-z0-9-]*)", status_line or "")
    return mm.group(1) if mm else ""


def parked(root, m):
    """[{ref, why}]: the milestone's `[!]` items and mission specs that are not in scope."""
    res = []
    for it in items(root, m):
        if it["state"] == "!":
            note = re.search(r"parked:\s*(.+?)\s*$", it["line"])
            res.append({"ref": it["id"] or it["title"][:40], "why": note.group(1) if note else "blocked"})
    scoped = _scoped_slugs(root, m)
    try:
        names = sorted(os.listdir(os.path.join(root, "docs", "specs")))
    except OSError:
        names = []
    for n in names:
        if not n.endswith(".md") or n.startswith("_"):
            continue
        slug = n[:-3]
        sm = re.search(r"(?m)^>\s*Status:.*$", _read(os.path.join(root, "docs", "specs", n)))
        if sm and mission_of(sm.group(0)) == m["slug"] and not in_scope(root, m, slug):
            if slug in scoped:
                why = "over the feature cap"
            elif slug.startswith(m["slug"] + "-"):
                why = "not linked from milestone %s" % m["milestone"]
            else:
                why = "slug lacks the prefix %s-" % m["slug"]
            res.append({"ref": slug, "why": "out of scope: " + why})
    return res


def approval(root, mission_slug, spec, at=None):
    """(ok, why): may mission `mission_slug` approve the spec? `at=None` = live now; a datetime = historical (gate)."""
    m = load(root, mission_slug)
    if m is None:
        return False, "no mission file docs/missions/%s.md" % mission_slug
    bad = validate(root, m)
    if bad:
        return False, "mission %s is not valid: %s" % (mission_slug, bad)
    if at is None:
        hit = cap_hit(m, load_state(root, m["slug"]))
        if hit:
            return False, "mission %s is not live (%s)" % (mission_slug, hit)
    else:
        if at.tzinfo is None:
            at = at.replace(tzinfo=datetime.timezone.utc)
        if not m["started_at"] <= at <= expires_at(m):
            return False, "commit time is outside the mission window"
    if not in_scope(root, m, spec):
        return False, "%s is out of scope for mission %s" % (spec, mission_slug)
    return True, ""


def set_status(root, slug, status):
    """Rewrite the `status:` line in the mission header (the only key allowed to change)."""
    path = os.path.join(root, MISSIONS_DIR, slug + ".md")
    text = _read(path)
    a, b = text.find(START), text.find(END)
    if a < 0 or b < a:
        raise ValueError("no mission header in " + path)
    head = re.sub(r"(?m)^status:.*$", "status: " + status, text[a:b], count=1)
    _write_atomic(path, text[:a] + head + text[b:])
