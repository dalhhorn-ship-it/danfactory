"""Find file writes in a Bash command, for the PRD write guard (GRD-2, closes the shell half of TD-016).
Pure functions, stdlib only. Reuses the segment splitter of guard_bash_policy.py. Heuristic by design: it sees
redirects, tee, sed/perl -i, cp/mv/install/ln, truncate, dd of=, and literal-path writes in inline interpreter code.
It cannot see what a generated program writes; the merge gate (check `prd`) covers that at commit time."""
import os
import re

from guard_bash_policy import HEREDOC, INTERPRETERS, PIPE_TO_SHELL, SHELLS, split_segments

MAX_DEPTH = 6
WRAPPERS = {"sudo", "env", "nohup", "time", "command", "exec", "nice", "stdbuf", "timeout", "then", "do", "else", "if", "!", "{"}
ASSIGN = re.compile(r"^[A-Za-z_]\w*=")
# Tool output, caches and VCS internals: shell redirects into these are not product changes.
NOISE_PREFIXES = (".git/", "node_modules/", ".venv/", "__pycache__/", ".wrangler/", ".pytest_cache/", ".claude/worktrees/",
                  ".cache/", "coverage/")
NOISE_SUFFIXES = (".log", ".tmp", ".pyc", ".pid")

_Q = r"""(['"])((?:(?!\1).)+)\1"""
_MODE = r"""\s*,\s*(?:mode\s*=\s*)?['"][^'"]*[wax+][^'"]*['"]"""
INLINE_WRITES = (
    re.compile(r"\bopen\(\s*" + _Q + _MODE),                                    # python/ruby/php open(p, 'w')
    re.compile(r"\bPath\(\s*" + _Q + r"\s*\)\s*\.\s*write_(?:text|bytes)\b"),   # pathlib
    re.compile(r"\b(?:writeFile|writeFileSync|appendFile|appendFileSync|createWriteStream)\(\s*" + _Q),  # node
    re.compile(r"\bFile\.(?:write|open)\(\s*" + _Q + _MODE.replace(r"\s*,", r"\s*,?", 1) + r"?"),   # ruby File.write
    re.compile(r"\bfile_put_contents\(\s*" + _Q),                               # php
)
CODE_FLAGS = {"-c", "-e", "-E", "-r", "--eval"}
ARITH = re.compile(r"\$?\(\([^()]*\)\)|\[\[[^\]]*\]\]")  # arithmetic and [[ a > b ]] compare, not redirects


def tokens(seg):
    """[(kind, text)]: kind 'op' for unquoted > >> <, else 'w'. Quoted > stays a word. Raises ValueError on bad quoting."""
    out, buf, has, q, i, n = [], [], False, None, 0, len(seg)

    def flush():
        nonlocal buf, has
        if has:
            out.append(("w", "".join(buf)))
        buf, has = [], False

    while i < n:
        c = seg[i]
        if q:
            if c == q:
                q = None
            elif c == "\\" and q == '"' and i + 1 < n and seg[i + 1] in '"\\$`':
                i += 1
                buf.append(seg[i])
            else:
                buf.append(c)
        elif c in "'\"":
            q, has = c, True
        elif c == "\\" and i + 1 < n:
            i += 1
            buf.append(seg[i])
            has = True
        elif c in " \t\r\n":
            flush()
        elif c in "<>":
            # a bare fd number glued to the operator (`2>`) belongs to it
            if has and "".join(buf).isdigit():
                buf, has = [], False
            flush()
            j = i
            while j < n and seg[j] in "<>":
                j += 1
            out.append(("op", seg[i:j]))
            i = j
            continue
        else:
            buf.append(c)
            has = True
        i += 1
    if q:
        raise ValueError("unbalanced quote")
    flush()
    return out


def _positional(args, value_opts=()):
    """Non-option arguments; options in value_opts consume the next word. `--` ends options."""
    out, skip, rest = [], False, False
    for a in args:
        if skip:
            skip = False
        elif rest or not a.startswith("-") or a == "-":
            out.append(a)
        elif a == "--":
            rest = True
        elif a in value_opts:
            skip = True
    return out


def _dest_writes(prog, args):
    tdir = None
    for i, a in enumerate(args):
        if a in ("-t", "--target-directory") and i + 1 < len(args):
            tdir = args[i + 1]
        elif a.startswith("--target-directory="):
            tdir = a.split("=", 1)[1]
        elif re.fullmatch(r"-[A-Za-z]*t", a) and i + 1 < len(args):
            tdir = args[i + 1]
    pos = _positional(args, ("-t", "--target-directory", "-S", "--suffix", "-m", "--mode", "-o", "-g", "--owner", "--group"))
    if tdir is not None:
        out = [tdir]
    elif prog in ("cp", "mv", "install", "ln") and len(pos) >= 2:
        out = [pos[-1]]
    elif prog in ("ln",) and len(pos) == 1:
        out = [os.path.basename(pos[0])]
    else:
        out = []
    if prog == "mv" and len(pos) >= 2:
        out += pos[:-1]  # moving a product file away changes the product too
    return out


def _inline(code):
    return [m.group(2) for rx in INLINE_WRITES for m in rx.finditer(code)]


def _sed_perl(prog, args):
    inplace = any(re.fullmatch(r"-[A-Za-z]*i[^ ]*", a) or a.startswith("--in-place") for a in args if a.startswith("-") and a != "--")
    if prog == "perl":
        inplace = any(re.fullmatch(r"-[A-Za-z]*i[^ ]*", a) for a in args if a.startswith("-") and not a.startswith("--"))
    if not inplace:
        return []
    has_script = any(a in ("-e", "-f", "--expression", "--file") or a.startswith(("--expression=", "--file=")) or
                     (prog == "perl" and re.fullmatch(r"-[A-Za-z]*e", a)) for a in args)
    pos = _positional(args, ("-e", "-f", "--expression", "--file", "-E", "-l", "-0", "-I"))
    return pos if has_script else pos[1:]


def writes_in_segment(toks, depth, seen_out):
    """Add literal write targets of one command to seen_out; recurse into `sh -c`, eval and heredoc bodies via analyse."""
    words = []
    i = 0
    while i < len(toks):
        kind, t = toks[i]
        if kind == "op":
            tgt = toks[i + 1][1] if i + 1 < len(toks) and toks[i + 1][0] == "w" else ""
            if t.startswith(">") and tgt:
                seen_out.append(tgt)
            if tgt:
                i += 1  # the word after an operator is a target/source, not an argument
        else:
            words.append(t)
        i += 1
    while words and (ASSIGN.match(words[0]) or os.path.basename(words[0]) in WRAPPERS):
        w = words.pop(0)
        if os.path.basename(w) in ("env", "sudo", "nice", "timeout", "stdbuf"):
            while words and (words[0].startswith("-") or ASSIGN.match(words[0]) or words[0].isdigit()):
                words.pop(0)
    if not words:
        return
    prog, args = os.path.basename(words[0]), words[1:]
    if prog in SHELLS:
        for j, a in enumerate(args):
            if a.startswith("-") and not a.startswith("--") and "c" in a and j + 1 < len(args):
                seen_out.extend(analyse(args[j + 1], depth + 1))
    elif prog in ("cd", "pushd") and args:
        seen_out.append(("cd", args[0]))
    elif prog == "eval":
        seen_out.extend(analyse(" ".join(args), depth + 1))
    elif prog == "tee":
        seen_out.extend(_positional(args))
    elif prog in ("sed", "perl"):
        seen_out.extend(_sed_perl(prog, args))
    elif prog in ("cp", "mv", "install", "ln"):
        seen_out.extend(_dest_writes(prog, args))
    elif prog == "truncate":
        seen_out.extend(_positional(args, ("-s", "--size", "-r", "--reference")))
    elif prog == "dd":
        seen_out.extend(a[3:] for a in args if a.startswith("of="))
    if INTERPRETERS.match(prog) or prog in ("php",):
        for j, a in enumerate(args):
            if a in CODE_FLAGS and j + 1 < len(args):
                seen_out.extend(_inline(args[j + 1]))
            elif re.fullmatch(r"-[A-Za-z]*[ce]", a) and j + 1 < len(args):  # perl -pe, -ne
                seen_out.extend(_inline(args[j + 1]))


def analyse(cmd, depth=0):
    """Literal paths a command writes to (as written, not yet resolved). Raises ValueError on unparseable quoting."""
    if depth > MAX_DEPTH:
        return []
    out, bodies = [], []

    def drop(m):
        opener, _, rest = m.group(0).partition("\n")
        body = rest.rsplit("\n", 1)[0] if "\n" in rest else ""
        first = cmd[cmd.rfind("\n", 0, m.start()) + 1:m.start()].split()
        prog = os.path.basename(first[0]) if first else ""
        if prog in SHELLS or PIPE_TO_SHELL.search(opener):
            out.extend(analyse(body, depth + 1))
        elif INTERPRETERS.match(prog):
            out.extend(_inline(body))
        return opener

    cmd = ARITH.sub(" ", HEREDOC.sub(drop, cmd))
    for seg in split_segments(cmd):
        out_seg = []
        writes_in_segment(tokens(seg), depth, out_seg)
        out.extend(out_seg)
    return out


def written_paths(cmd, root, cwd=None):
    """[(repo-relative path)] for literal write targets inside the repo, excluding tool noise (.git/, logs, caches)."""
    import _prd
    out, here = [], cwd or root
    for raw in analyse(cmd):
        if isinstance(raw, tuple):  # `cd dir`: later relative paths resolve from there
            if "$" not in raw[1]:
                here = os.path.join(here, os.path.expanduser(raw[1]))
            continue
        if not raw or "$" in raw or "`" in raw or raw.startswith(("/dev/", "-", "[", "...")):  # `<placeholder> --flag` is prose
            continue
        rel = _prd.rel_path(raw, root, here)
        if rel and not rel.startswith(NOISE_PREFIXES) and not rel.endswith(NOISE_SUFFIXES) and rel != ".git":
            out.append(rel)
    return out


def product_writes(cmd, root, cwd=None):
    import _prd
    return [r for r in written_paths(cmd, root, cwd) if _prd.is_product_path(r)]
