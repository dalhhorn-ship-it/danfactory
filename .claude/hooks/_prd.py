"""PRD write guard rules, shared by guard_prd_write.py (hook) and scripts/gate.py (check `prd`).
Pure functions, stdlib only. Policy: docs/policies/prd-approval.md (Enforcement)."""
import datetime
import os
import re

EXEMPTION_FILE = ".factory/prd-exemption"
KINDS = ("bugfix", "chore", "waiver", "spike")
EXEMPT_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(%s):\s*(\S.*?)\s*$" % "|".join(KINDS))
# A waiver is the user's decision, not the agent's: the line must quote the user's words from the chat,
# `waiver: "<user words>" - <reason>` (hyphen, en or em dash). Unquoted waivers are ignored.
WAIVER_RE = re.compile(r'^["“]([^"”]{3,})["”]\s*(?:—|–|--?)\s*\S')
WEAK_WAIVER_WORDS = ("just do it", "quick job", "quick fix", "go ahead", "do it", "whatever", "fine", "ok", "okay")
PRE_BUILD_PHASES = ("brainstorm", "operating-model")

# Always allowed: they can't change what the product does. Everything else (including .claude/ hooks and
# settings, CLAUDE.md and all code) is product or config and needs approved work.
FREE_PREFIXES = ("docs/", "issues/", "tests/acceptance/", "metrics/", ".factory/")
FREE_FILES = ("factory.json",)  # written by choose-path / phase changes before any PRD can exist


# While a mission's approval is what opens writes, the factory's own controls stay closed: a mission cannot change the
# gate, the runner, the hooks or its own caps. Mirrors scripts/runner_core.py RUNNER_PROTECTED (which cannot be imported
# cheaply from a hook) plus the mission machinery; docs/missions/<slug>.md needs no entry here, _mission.validate freezes
# its header from the first commit (only `status` may change, which `mission.py stop` does).
MISSION_PROTECTED = ("factory.json", ".claude/**", ".github/**", "scripts/gate*.py", "scripts/mission*.py", "scripts/slices.py",
                     "scripts/acceptance*.py", "scripts/runner*.py", "scripts/sandbox.py", "scripts/check.sh",
                     ".factory/prd-exemption", ".factory/mission-state.json")
MISSION_BLOCK = ("mission work cannot change the factory's own controls (%s): park the item and tell the user "
                 "(docs/policies/mission.md)")


def mission_protected(rel):
    import fnmatch
    for pat in MISSION_PROTECTED:
        if pat.endswith("/**"):
            if rel == pat[:-3] or rel.startswith(pat[:-2]):
                return True
        elif fnmatch.fnmatchcase(rel, pat):
            return True
    return False


def rel_path(path, root, cwd=None):
    """Repo-relative posix path, or '' when the path is outside the repo (not ours to guard)."""
    if not path:
        return ""
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(cwd or root, path)
    rel = os.path.relpath(os.path.normpath(path), os.path.normpath(root)).replace(os.sep, "/")
    return "" if rel == ".." or rel.startswith("../") else rel


def is_product_path(rel):
    """True when a repo-relative path needs approved work behind it."""
    if not rel:
        return False
    if rel.startswith(FREE_PREFIXES) or rel in FREE_FILES:
        return False
    if "/" not in rel and rel.lower().endswith(".md") and rel != "CLAUDE.md":
        return False  # README, CHANGELOG and the like; CLAUDE.md steers the agent, so it needs approval
    return True


def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def waiver_quoted(reason):
    """True when a waiver reason quotes the user's words (and not just a stock phrase) before the reason."""
    m = WAIVER_RE.match(reason)
    return bool(m) and m.group(1).strip().strip(".!").lower() not in WEAK_WAIVER_WORDS


def exemptions(root, today=None):
    """[{date, kind, reason, active, ignored}] from .factory/prd-exemption; malformed lines are ignored. Active = dated
    today and honoured; `ignored` marks today's waivers without the user's quoted words (they grant nothing)."""
    today = today or datetime.date.today().isoformat()
    out = []
    for ln in read(root, EXEMPTION_FILE).splitlines():
        m = EXEMPT_LINE_RE.match(ln.strip())
        if m:
            ignored = m.group(2) == "waiver" and not waiver_quoted(m.group(3))
            out.append({"date": m.group(1), "kind": m.group(2), "reason": m.group(3),
                        "active": m.group(1) == today and not ignored, "ignored": ignored and m.group(1) == today})
    return out


def active_exemptions(root, today=None):
    return [x for x in exemptions(root, today) if x["active"]]


_MISSION = []


def _mission_mod():
    """The sibling _mission.py, loaded by path (callers may have removed the hooks dir from sys.path); None when absent."""
    if not _MISSION:
        mod = None
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_mission.py")
        if os.path.isfile(path):
            import importlib.util
            spec = importlib.util.spec_from_file_location("_mission", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        _MISSION.append(mod)
    return _MISSION[0]


def prd_mission(root, slug):
    """Mission slug named by `by mission <m>` on the PRD's Status line ('' for a user approval or no such PRD)."""
    if not re.fullmatch(r"[\w.-]+", slug or ""):
        return ""
    m = re.search(r"(?m)^>\s*Status:.*$", read(root, "docs/specs/%s.md" % slug))
    if not m or "by mission" not in m.group(0):
        return ""
    mod = _mission_mod()
    return mod.mission_of(m.group(0)) if mod else ""


def prd_status(root, slug, at=None):
    """Lower-case Status word of docs/specs/<slug>.md ('' when missing or not a PRD). A PRD approved `by mission <m>`
    reads 'unapproved' unless _mission.approval says yes (at=None: live now; a datetime: valid at that commit time)."""
    if not re.fullmatch(r"[\w.-]+", slug or ""):
        return ""
    text = read(root, "docs/specs/%s.md" % slug)
    m = re.search(r"(?m)^>\s*Status:\s*([\w-]+)", text) if re.search(r"(?m)^#\s+PRD:", text) else None
    word = m.group(1).lower() if m else ""
    if word == "approved" and "by mission" in text[m.start():].split("\n", 1)[0]:
        mod = _mission_mod()
        mission = prd_mission(root, slug)
        if not (mod and mission and mod.approval(root, mission, slug, at)[0]):
            return "unapproved"
    return word


def backlog_items(root):
    """[{id, state, slugs}] from docs/BACKLOG.md checkbox lines; slugs = docs/specs/<slug>.md links on the line."""
    items = []
    for ln in read(root, "docs/BACKLOG.md").splitlines():
        m = re.match(r"^\s*-\s*\[([ x~])\]\s*(?:([A-Z][A-Z0-9]*-\d+)\b)?", ln)
        if m:
            items.append({"id": m.group(2) or "", "state": m.group(1),
                          "slugs": re.findall(r"docs/specs/([\w.-]+)\.md", ln)})
    return items


def in_progress_approved(root):
    """Slugs of approved PRDs linked from `[~]` backlog items."""
    return [s for it in backlog_items(root) if it["state"] == "~" for s in it["slugs"] if prd_status(root, s) == "approved"]


def approving_slug(root, ref, at=None):
    """Slug of the approved PRD that `ref` (backlog id, PRD slug or ISS-n) leads to, or ''."""
    ref = ref.strip().strip(",;")
    if not ref:
        return ""
    if prd_status(root, ref, at) == "approved":
        return ref
    for it in backlog_items(root):
        if it["id"] == ref:
            for s in it["slugs"]:
                if prd_status(root, s, at) == "approved":
                    return s
    m = re.fullmatch(r"ISS-0*(\d+)", ref)
    if m:
        n = int(m.group(1))
        for sub in ("open", "fixed"):
            try:
                names = os.listdir(os.path.join(root, "issues", sub))
            except OSError:
                continue
            for name in names:
                fm = re.match(r"^ISS-(\d+)-", name)
                if fm and int(fm.group(1)) == n:
                    hm = re.search(r"(?m)^>.*?PRD:\s*([\w.-]+)", read(root, "issues/%s/%s" % (sub, name)))
                    if hm and prd_status(root, hm.group(1), at) == "approved":
                        return hm.group(1)
    return ""


def item_approved(root, ref, at=None):
    """True when `ref` (backlog id, PRD slug or ISS-n) leads to an approved PRD (`at`: commit time for mission approvals)."""
    return bool(approving_slug(root, ref, at))


def decide(root, rel, phase, template, today=None):
    """(allowed, reason, via): via is 'free', 'prd:<slug>' or 'exemption:<kind>'; reason says what is missing when blocked."""
    ex = active_exemptions(root, today)
    if mission_protected(rel) and not ex:
        slugs = in_progress_approved(root)
        if slugs and all(prd_mission(root, s) for s in slugs):  # only a mission's approval would open this write
            return False, MISSION_BLOCK % rel, "mission-protected"
    if not is_product_path(rel):
        return True, "", "free"
    spike = next((x for x in ex if x["kind"] == "spike"), None)
    if not template and phase in PRE_BUILD_PHASES:
        if spike:
            return True, "", "exemption:spike"
        return False, ("phase is '%s', not 'build': product code can't be written yet (finish the brainstorm / operating-model "
                       "steps, or claim a `spike` exemption if the user asked for a throwaway prototype)" % phase), ""
    slugs = in_progress_approved(root)
    if slugs:
        return True, "", "prd:" + slugs[0]
    if ex:
        return True, "", "exemption:" + ex[0]["kind"]
    why = "no in-progress backlog item (`[~]`) is linked to a PRD with `Status: approved`, and there is no exemption dated today"
    if any(x["ignored"] for x in exemptions(root, today)):
        why += (" (a `waiver` line is ignored: it must quote the user's words, "
                '`waiver: "<user words>" - <reason>`; "just do it" is not a waiver)')
    return False, why, ""
