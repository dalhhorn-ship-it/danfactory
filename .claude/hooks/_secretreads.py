"""Secret-file (.env*, .dev.vars*) checks for guard_bash_policy.py: name-based and recursive/glob content reads.
Split out of the guard (SIZE-3); the guard imports `check_secrets`, `DOTGLOB` and `GIT_VALUE_GLOBALS` from here."""
import fnmatch
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, block  # noqa: E402

GIT_VALUE_GLOBALS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
SECRET = re.compile(r"^\.(?:env|dev\.vars)(?:\.[^/]*|[*?\[].*)?$")
SECRET_OK = re.compile(r"\.(?:example|sample|template)$")
READERS = {"cat", "grep", "egrep", "fgrep", "head", "tail", "less", "more", "sed", "awk", "cp", "mv", "base64",
           "xxd", "od", "strings", "tee", "rg", "bash", "sh", "zsh", "source", "nl", "tac", "sort", "uniq", "cut",
           "paste", "curl", "diff", "cmp", "wc"}
WALK_LIMIT = 20000
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}
GLOB_CHARS = re.compile(r"[*?\[]")

DOTGLOB = [False]  # the command text mentions `dotglob`: `*` then matches dotfiles


def git_subcommand(args):
    i = 0
    while i < len(args):
        if args[i] in GIT_VALUE_GLOBALS:
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            return args[i]
    return None


def is_secret_name(name):
    return bool(SECRET.match(name)) and not SECRET_OK.search(name)


def secret_files(path):
    """Real secret files at or under `path` (relative paths resolve against the repo); the walk is capped."""
    path = os.path.realpath(os.path.join(ROOT, os.path.expanduser(path or ".")))
    if os.path.isfile(path):
        return [path] if is_secret_name(os.path.basename(path)) else []
    found, count = [], 0
    for base, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            count += 1
            if is_secret_name(f):
                found.append(os.path.join(base, f))
        if count > WALK_LIMIT or len(found) > 50:
            break
    return found


def opt_values(args, long_names, short=""):
    """Values of `--name=v`/`--name v` options (and `-X v`/`-Xv` for the letters in `short`)."""
    vals = []
    for i, a in enumerate(args):
        for n in long_names:
            if a == n and i + 1 < len(args):
                vals.append(args[i + 1])
            elif a.startswith(n + "="):
                vals.append(a.split("=", 1)[1])
        if short and re.match(r"^-[%s]" % short, a):
            vals.append(a[2:] if len(a) > 2 else (args[i + 1] if i + 1 < len(args) else ""))
    return vals


def positional(args, value_opts):
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            out.extend(args[i + 1:])
            break
        if a in value_opts:
            i += 2
            continue
        if not a.startswith("-"):
            out.append(a)
        i += 1
    return out


def block_recursive(why, hit):
    block("Content read blocked: %s would read the secret file `%s` (.env*/.dev.vars* must not be read by the "
          "agent). Exclude them (`grep -r --exclude='.env*' --exclude='.dev.vars*'`, `rg -g '!.env*'`, "
          "`find ... ! -name '.env*'`) or name only the files you need." % (why, os.path.relpath(hit, ROOT)))


def grep_check(prog, args):
    git_grep = prog == "git"
    if git_grep:
        if "grep" not in args:
            return
        args = args[args.index("grep") + 1:]
        recursive = "--untracked" in args or "--no-index" in args
    else:
        recursive = (prog == "rgrep" or "--recursive" in args or "--dereference-recursive" in args
                     or "--directories=recurse" in args
                     or any(re.match(r"^-[A-Za-z]*[rR]", a) for a in args))
    if not recursive:
        return
    value_opts = {"-e", "-f", "-m", "-A", "-B", "-C", "--include", "--exclude", "--exclude-dir", "--exclude-from",
                  "-d", "--directories", "--label", "--color", "--context"}
    pos = positional(args, value_opts)
    has_pattern = any(a in ("-e", "-f") or a.startswith(("--regexp", "--file")) for a in args)
    paths = pos if has_pattern else pos[1:]
    excludes = opt_values(args, ["--exclude"])
    includes = opt_values(args, ["--include"])
    for p in paths or ["."]:
        for f in secret_files(p):
            n = os.path.basename(f)
            if any(fnmatch.fnmatch(n, e) for e in excludes):
                continue
            if includes and not any(fnmatch.fnmatch(n, i) for i in includes):
                continue
            block_recursive("`%s` over `%s`" % ("git grep" if git_grep else prog + " -r", p), f)


def rg_check(args):
    """ripgrep skips hidden and git-ignored files (.env is both) unless told otherwise."""
    wide = any(a in ("--hidden", "--no-ignore", "--no-ignore-vcs", "--no-ignore-dot", "-.") or re.match(r"^-u+$", a)
               or re.match(r"^-[A-Za-z]*u", a) and not a.startswith("--") for a in args)
    if not wide:
        return
    neg = [g[1:] for g in opt_values(args, ["--glob", "--iglob"], "g") if g.startswith("!")]
    pos = positional(args, {"-e", "-f", "-g", "--glob", "--iglob", "-t", "-T", "--type", "-m", "-A", "-B", "-C",
                            "--max-depth", "-d", "--type-not", "-j", "--threads", "--color"})
    has_pattern = any(a in ("-e", "-f") for a in args)
    for p in (pos if has_pattern else pos[1:]) or ["."]:
        for f in secret_files(p):
            n = os.path.basename(f)
            if not any(fnmatch.fnmatch(n, g.split("/")[-1]) for g in neg):
                block_recursive("`rg` with hidden/ignored files enabled over `%s`" % p, f)


def find_check(args):
    roots = []
    for a in args:
        if a.startswith("-") or a in ("!", "(", ")"):
            break
        roots.append(a)
    execs = [i for i, a in enumerate(args) if a in ("-exec", "-execdir", "-ok", "-okdir")]
    if not any(i + 1 < len(args) and os.path.basename(args[i + 1]) in READERS for i in execs):
        return
    pos_names, neg_names = [], []
    for i, a in enumerate(args):
        if a in ("-name", "-iname", "-path", "-ipath") and i + 1 < len(args):
            negated = i > 0 and args[i - 1] in ("!", "-not")
            (neg_names if negated else pos_names).append(args[i + 1].split("/")[-1])
    for r in roots or ["."]:
        for f in secret_files(r):
            n = os.path.basename(f)
            if any(fnmatch.fnmatch(n, p) for p in neg_names):
                continue
            if pos_names and not any(fnmatch.fnmatch(n, p) for p in pos_names):
                continue
            block_recursive("`find %s -exec <reader>`" % r, f)


def glob_check(args):
    """`cat .*`, `cat *` under dotglob: expand like bash (a leading dot must be explicit) against real files."""
    dotglob = DOTGLOB[0] or "dotglob" in " ".join(args)
    for a in args:
        if a.startswith("-") or not GLOB_CHARS.search(a):
            continue
        d, pat = os.path.split(a)
        if GLOB_CHARS.search(d):
            continue
        try:
            names = os.listdir(os.path.join(ROOT, os.path.expanduser(d or ".")))
        except OSError:
            continue
        for n in names:
            if is_secret_name(n) and fnmatch.fnmatch(n, pat) and (pat.startswith(".") or dotglob):
                block_recursive("the glob `%s`" % a, os.path.join(ROOT, d, n))


def check_content_reads(prog, tokens, args):
    """Recursive/glob content reads that reach a real secret file; the name-based check cannot see these."""
    if prog in ("grep", "egrep", "fgrep", "rgrep") or (prog == "git" and git_subcommand(args) == "grep"):
        grep_check(prog, args)
    elif prog == "rg":
        rg_check(args)
    elif prog == "find":
        find_check(args)
    elif prog in READERS:
        glob_check(args)


def check_secrets(prog, tokens, args):
    """Block reading/writing .env* and .dev.vars* via Bash (listing/testing/ignore-checks are allowed)."""
    if prog in ("ls", "test", "[", "[["):
        return
    if prog == "git" and git_subcommand(args) in ("check-ignore", "status"):
        return
    check_content_reads(prog, tokens, args)
    for i, t in enumerate(tokens):
        prev = tokens[i - 1] if i else ""
        if t.startswith(("--exclude=", "--exclude-dir=")) or prev in ("--exclude", "--exclude-dir"):
            continue  # an exclusion pattern names the file in order to skip it
        if prog == "find" and prev in ("-name", "-iname", "-path", "-ipath") and i > 1 and tokens[i - 2] in ("!", "-not"):
            continue
        for cand in (t, t.split("=", 1)[-1]):
            cand = re.sub(r"^(?:\d*[<>]+|@)", "", cand)
            name = os.path.basename(cand.rstrip("/"))
            if SECRET.match(name) and not SECRET_OK.search(name):
                block("Bash access to secret files (`%s`) is blocked: .env*/.dev.vars* must not be read, "
                      "copied or sourced by the agent. Use `.env.example` for templates; ask the user to "
                      "handle real secrets." % name)
