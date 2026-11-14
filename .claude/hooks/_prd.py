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


def prd_status(root, slug):
    """Lower-case Status word of docs/specs/<slug>.md ('' when missing or not a PRD)."""
    if not re.fullmatch(r"[\w.-]+", slug or ""):
        return ""
    text = read(root, "docs/specs/%s.md" % slug)
    m = re.search(r"(?m)^>\s*Status:\s*([\w-]+)", text) if re.search(r"(?m)^#\s+PRD:", text) else None
    return m.group(1).lower() if m else ""


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


def item_approved(root, ref):
    """True when `ref` (backlog id, PRD slug or ISS-n) leads to an approved PRD."""
    ref = ref.strip().strip(",;")
    if not ref:
        return False
    if prd_status(root, ref) == "approved":
        return True
    for it in backlog_items(root):
        if it["id"] == ref and any(prd_status(root, s) == "approved" for s in it["slugs"]):
            return True
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
                    if hm and prd_status(root, hm.group(1)) == "approved":
                        return True
    return False


def decide(root, rel, phase, template, today=None):
    """(allowed, reason, via): via is 'free', 'prd:<slug>' or 'exemption:<kind>'; reason says what is missing when blocked."""
    if not is_product_path(rel):
        return True, "", "free"
    ex = active_exemptions(root, today)
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
