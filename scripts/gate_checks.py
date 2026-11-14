"""Gate checks that read the diff: `security` (secret and supply-chain scan of added lines), `prd` and `size`.
Split from scripts/gate.py (SIZE-3); gate re-exports these names, so `gate.c_size`, `gate.scan` etc. still work.

The helpers that run commands (git, changes, commits, matches) are looked up in `gate` at call time, never copied:
`gate.WRAP` (the sandbox wrapper) and in-process patches of gate globals must stay in effect for these checks."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(root, *args):
    import gate
    return gate.git(root, *args)


def changes(root, base):
    import gate
    return gate.changes(root, base)


def commits(root, base, *paths):
    import gate
    return gate.commits(root, base, *paths)


def matches(path, pats):
    import gate
    return gate.matches(path, pats)


_B = r"(?<![A-Za-z0-9])"  # \b fails next to "_" (GITHUB_TOKEN_AKIA...), so use explicit alnum look-arounds
_E = r"(?![A-Za-z0-9])"
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"),
    re.compile(_B + r"AKIA[0-9A-Z]{16}" + _E),
    re.compile(_B + r"gh[pousr]_[A-Za-z0-9]{36,}" + _E),
    re.compile(_B + r"github_pat_[A-Za-z0-9_]{50,}" + _E),
    re.compile(_B + r"glpat-[A-Za-z0-9_-]{20,}"),
    re.compile(_B + r"sk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(_B + r"sk-proj-[A-Za-z0-9_-]{20,}"),
    re.compile(_B + r"sk-[A-Za-z0-9]{32,}" + _E),
    re.compile(_B + r"[sr]k_live_[A-Za-z0-9]{16,}"),
    re.compile(_B + r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(_B + r"AIza[0-9A-Za-z_-]{35}" + _E),
]
# keyword = value assignments: the value is judged by secret_value() (length, character mix, placeholders)
ASSIGN = re.compile(r"(?i)(?P<k>[\w.-]*(?:api[_-]?key|secret|token|password|passwd))[\"']?\s*(?::=|[:=])\s*"
                    r"(?:\"(?P<dq>[^\"]*)\"|'(?P<sq>[^']*)'|(?P<raw>[^\s\"',;#]+))")
PLACEHOLDER = re.compile(r"(?i)example|placeholder|your|xxx|changeme|change-me|dummy|sample|redacted|\*\*\*|todo|fake|<|\$|\{|\}|^(?:process\.env|os\.environ|env\.|secrets\.|vars\.)")
VALUE_CHARS = re.compile(r"[A-Za-z0-9+/_.=!@#%^&*~:-]+")
RAW_OK = (".env", ".yml", ".yaml", ".ini", ".cfg", ".conf", ".toml", ".properties", ".sh")  # unquoted values count only here


def secret_value(keyword, value, quoted):
    """True if `value` assigned to a secret-looking `keyword` looks like a literal credential."""
    need = 24 if re.search(r"(?i)key|token", keyword) else 8
    if len(value) < need or not VALUE_CHARS.fullmatch(value) or PLACEHOLDER.search(value):
        return False
    if re.fullmatch(r"[a-z0-9_-]+(?:\.[a-z0-9_-]+)+", value):  # dotted lowercase words: i18n keys, module paths
        return False
    if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", value):  # attribute chain: config.db.password
        return False
    classes = sum(bool(re.search(c, value)) for c in ("[a-z]", "[A-Z]", "[0-9]"))
    return classes >= 2 and (quoted or bool(re.search(r"[0-9]", value)))


def secret_in(path, text):
    if any(p.search(text) for p in SECRET_PATTERNS):
        return True
    base = os.path.basename(path)
    raw_ok = base.startswith((".env", ".dev.vars")) or base.endswith(RAW_OK)
    for m in ASSIGN.finditer(text):
        v = m.group("dq") if m.group("dq") is not None else m.group("sq")
        if v is None and raw_ok and m.start() == len(text) - len(text.lstrip()) + (len("export ") if text.lstrip().startswith("export ") else 0):
            v = m.group("raw")
            if secret_value(m.group("k"), v, False):
                return True
        elif v is not None and secret_value(m.group("k"), v, True):
            return True
    return False


_SH = r"(?:sudo(?:\s+-\S+)*\s+)?(?:ba|z|da|k)?sh\b"
PIPE_SHELL = re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*" + _SH
                        + r"|\b" + _SH + r"(?:\s+-\w+)*\s+<\(\s*(?:curl|wget)\b"
                        + r"|\b" + _SH + r"(?:\s+-\w+)*\s+-c\s+[\"']?(?:\$\(|`)\s*(?:curl|wget)\b"
                        + r"|\beval\s+[\"']?(?:\$\(|`)\s*(?:curl|wget)\b")
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
PINNED = re.compile(r"@[0-9a-f]{40}$")
ENV_OK = (".example", ".sample", ".template")


def _unquote(name):
    """Undo git's C-style quoting of a diff header path (only present for names with quotes, tabs, newlines)."""
    if len(name) >= 2 and name[0] == name[-1] == '"':
        try:
            return name[1:-1].encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8", "replace")
        except (UnicodeError, ValueError):
            return name[1:-1]
    return name


def added_lines(diff):
    """[(path, lineno, text)] for the added lines of a `git diff --unified=0` output.
    A `+++ ` line is a file header only before the first hunk of a `diff --git` block; inside a hunk it is content."""
    path, n, res, header = None, 0, [], False
    for ln in diff.splitlines():
        if ln.startswith("diff --git "):
            path, header = None, True
        elif header and ln.startswith("+++ "):
            name = _unquote(ln[4:].rstrip("\t"))
            path = name[2:] if name.startswith("b/") else None
        elif ln.startswith("@@"):
            header = False
            m = re.search(r"\+(\d+)", ln)
            n = int(m.group(1)) if m else 0
        elif not header and ln.startswith("+") and path:
            res.append((path, n, ln[1:]))
            n += 1
    return res


def scan(lines, ignore):
    """(codes, findings) for added lines; findings are 'code path:line' strings (never the secret itself)."""
    found = []
    for path, n, text in lines:
        if matches(path, ignore):
            continue
        if secret_in(path, text):
            found.append(("secret-in-diff", "%s:%d" % (path, n)))
        if path.endswith((".yml", ".yaml")) and not text.lstrip().startswith("#"):
            m = USES.match(text)
            if m and not m.group(1).startswith(("./", "docker://")) and not PINNED.search(m.group(1)):
                found.append(("unpinned-action", "%s:%d" % (path, n)))
        if not path.endswith((".md", ".txt")) and PIPE_SHELL.search(text):
            found.append(("pipe-to-shell", "%s:%d" % (path, n)))
    return found


def c_security(ctx):
    root, base = ctx["root"], ctx["base"]
    if not base:
        return "skip", [], "no base to diff against"
    ignore = ctx["gate"].get("security_ignore") or []
    found = scan(added_lines(git(root, "diff", "--unified=0", "--no-color", "--no-renames", base) or ""), ignore)
    for st, p in changes(root, base):
        name = os.path.basename(p)
        if st in ("A", "?") and not matches(p, ignore) and (name == ".env" or name.startswith(".env.") or name.startswith(".dev.vars")) \
                and not name.endswith(ENV_OK):
            found.append(("env-file-added", p))
    if not found:
        return "pass", [], "no findings in added lines"
    codes = sorted({c for c, _ in found})
    return "fail", codes, "; ".join("%s %s" % f for f in found[:6]) + (" ..." if len(found) > 6 else "")


def _prd_rules(root):
    """The shared PRD rules (.claude/hooks/_prd.py, also used by the write guard hook), or None when the file is absent."""
    for base in (ROOT, root):
        hooks = os.path.join(base, ".claude", "hooks")
        if not os.path.isfile(os.path.join(hooks, "_prd.py")):
            continue
        sys.path.insert(0, hooks)
        try:
            import _prd
            return _prd
        finally:
            sys.path.remove(hooks)
    return None


def c_prd(ctx):
    """`prd` plus a standing `prd-waiver-active` warning while a user waiver is in force (GRD-2)."""
    status, codes, detail = _c_prd(ctx)
    rules = _prd_rules(ctx["root"]) if ctx["gate"].get("prd", "required") != "off" else None
    waivers = [x for x in rules.exemptions(ctx["root"]) if x["active"] and x["kind"] == "waiver"] if rules else []
    if not waivers:
        return status, codes, detail
    note = " [WAIVER ACTIVE until end of day: %s]" % "; ".join(x["reason"][:80] for x in waivers)
    return ("fail" if status == "fail" else "warn"), codes + ["prd-waiver-active"], detail + note


def _c_prd(ctx):
    """Product-code commits in range need `Refs:` to an item with an approved PRD (or an ISS-n of one), or `PRD-Exempt:`."""
    mode = ctx["gate"].get("prd", "required")
    if mode == "off":
        return "skip", [], "gate.prd is off"
    root, rules = ctx["root"], _prd_rules(ctx["root"])
    if rules is None:
        return "skip", [], ".claude/hooks/_prd.py is missing (copy it from the template to enable this check)"
    ex = rules.exemptions(root)
    note = ""
    if ex:
        act = [x["kind"] for x in ex if x["active"]]
        note = " [exemptions in .factory/prd-exemption: %d active%s, %d expired]" % (
            len(act), " (" + ", ".join(act) + ")" if act else "", len(ex) - len(act))
    if not ctx["base"]:
        return "skip", [], "no base to diff against" + note
    bad, used, product = [], 0, 0
    for c in commits(root, ctx["base"]):
        files = [f for f in (git(root, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z", c["sha"]) or "").split("\0") if f]
        if not any(rules.is_product_path(f) for f in files):
            continue
        product += 1
        tr = c["trailers"]
        if any(v.strip() for v in tr.get("prd-exempt", [])):
            used += 1
            continue
        refs = [r for v in tr.get("refs", []) for r in re.split(r"[,\s]+", v) if r]
        if not any(rules.item_approved(root, r) for r in refs):
            bad.append(c["sha"][:7])
    if not bad:
        return "pass", [], "%d product-code commit(s) in range, all covered (%d by PRD-Exempt)%s" % (product, used, note)
    msg = "%d product-code commit(s) without Refs to an approved PRD or PRD-Exempt: %s%s" % (
        len(bad), ", ".join(bad[:6]) + (" ..." if len(bad) > 6 else ""), note)
    if mode == "required":
        return "fail", ["no-approved-prd"], msg
    return "warn", ["no-approved-prd"], msg + " (advisory)"


def c_size(ctx):
    """Warn (never fail): a product file over file_lines_max that the change range grew, or 30-day code growth over budget."""
    try:
        from obs import size
    except ImportError:
        return "skip", [], "scripts/obs/size.py is missing (copy it from the template to enable this check)"
    root = ctx["root"]
    b = size.budgets(ctx["factory"])
    if not ctx["base"]:
        return "skip", [], "no base to diff against"
    added = {}
    for line in (git(root, "diff", "--numstat", "--no-renames", ctx["base"]) or "").splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[0].isdigit():
            added[parts[2]] = int(parts[0])
    for st, p in changes(root, ctx["base"]):
        if st == "?":
            try:
                with open(os.path.join(root, p), "rb") as fh:
                    added[p] = size._lines(fh.read())
            except OSError:
                pass
    codes, notes = [], []
    for p, n in sorted(added.items()):
        if n <= 0 or not size.is_product(p):
            continue
        try:
            with open(os.path.join(root, p), "rb") as fh:
                total = size._lines(fh.read())
        except OSError:
            continue
        if total > b["file_lines_max"]:
            notes.append("%s +%d lines, now %d (max %d): split it or move it to an optional pack" % (p, n, total, b["file_lines_max"]))
    if notes:
        codes.append("file-over-size")
    if size.has_git(root):
        now = size._count(size.current_files(root))
        g = (size.growth(root, now).get("30") or {}).get("areas", {}).get("code")
        if g and g["pct"] is not None and g["pct"] > b["code_growth_30d_pct_warn"]:
            codes.append("size-growth")
            notes.append("product code grew %.0f%% in %d days (warn at %s%% per 30 days)" % (g["pct"], size.growth(root, now)["30"]["days"], b["code_growth_30d_pct_warn"]))
    if not codes:
        return "pass", [], "no product file over %d lines grew; code growth within budget" % b["file_lines_max"]
    return "warn", codes, "; ".join(notes[:6]) + (" ..." if len(notes) > 6 else "")
