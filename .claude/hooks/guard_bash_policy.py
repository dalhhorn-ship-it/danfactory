#!/usr/bin/env python3
"""PreToolUse (Bash): enforce deploy, git-hook and secret-file policy on the command text itself.

settings.json deny rules match command prefixes only, so `bunx wrangler deploy`, `npm run deploy`
or `git push origin main --no-verify` slip through. This hook tokenises the command (shlex), splits
compound commands, follows `bash -c`/`eval`/command substitution and package.json scripts, and
inspects programs, not quoted text. Rollback stays allowed.

It also scans the text handed to `python -c`/`node -e`/`perl -e`..., and the content of a local script
file the command executes, for a deploy command, and blocks recursive content reads (`grep -r`, `find
-exec cat`, `rg --hidden`, `cat .*`/`cat *` under dotglob) that would reach a real .env*/.dev.vars* file.

Residual risk, accepted: a program the agent generates and then runs can still build a deploy command
or read a secret in ways no text scan sees. The real protection is credential scoping (ADR 0003,
docs/policies/security.md). Stdlib only, Python 3.8+.
"""
import fnmatch
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, block, read_event  # noqa: E402

MAX_DEPTH = 8
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
SKIP_WORDS = {"then", "do", "else", "elif", "if", "while", "until", "!", "{", "time", "command", "exec",
              "builtin", "nohup", "sudo", "doas", "nice", "ionice", "stdbuf", "setsid", "xargs", "timeout"}
LIFECYCLE = {"test", "start", "stop", "restart"}
RUN_ALIASES = {"run", "run-script", "rum", "urn"}
EXEC_ALIASES = {"exec", "dlx", "x"}
PM_VALUE_FLAGS = {"--prefix", "--workspace", "-w", "--filter", "-F", "--cwd", "--dir", "-C", "--cache"}
WRANGLER_VALUE_FLAGS = {"-c", "--config", "-e", "--env", "--cwd"}
GIT_VALUE_GLOBALS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
COMMIT_VALUE_LETTERS = set("mFCctu")
WRANGLER = re.compile(r"^(?:@cloudflare/)?wrangler(?:@[^/]*)?$")
ASSIGN = re.compile(r"^([A-Za-z_]\w*)=")
PIPE_TO_SHELL = re.compile(r"\|\s*(?:\S*/)?(?:ba|z|da|k)?sh\b")  # `... | sh`: the text before the pipe is executed
QUOTED = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1.*?^\s*\2\s*$", re.S | re.M)
SINGLE_QUOTED = re.compile(r"'[^']*'")
SUBST = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
SECRET = re.compile(r"^\.(?:env|dev\.vars)(?:\.[^/]*|[*?\[].*)?$")
SECRET_OK = re.compile(r"\.(?:example|sample|template)$")
DEPLOY_HINT = re.compile(r"\bwrangler\b")

DEPLOY_TEXT = re.compile(r"\bwrangler\W+(?:(?:pages|versions)\W+)?(?:deploy|publish)\b")
INTERPRETERS = re.compile(r"^(?:python[\d.]*|node|nodejs|deno|bun|ruby|perl|php|tsx|ts-node)$")
CODE_FLAGS = {"-c", "-e", "-E", "-p", "--eval", "--print"}
READERS = {"cat", "grep", "egrep", "fgrep", "head", "tail", "less", "more", "sed", "awk", "cp", "mv", "base64",
           "xxd", "od", "strings", "tee", "rg", "bash", "sh", "zsh", "source", "nl", "tac", "sort", "uniq", "cut",
           "paste", "curl", "diff", "cmp", "wc"}
SCAN_LIMIT = 512 * 1024
WALK_LIMIT = 20000
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}
GLOB_CHARS = re.compile(r"[*?\[]")

DOTGLOB = [False]  # the command text mentions `dotglob`: `*` then matches dotfiles

CTX = []  # package.json script names being followed, for messages


def package_scripts():
    try:
        with open(os.path.join(ROOT, "package.json"), encoding="utf-8") as fh:
            return json.load(fh).get("scripts", {}) or {}
    except (OSError, ValueError, AttributeError):
        return {}


def deploy_block(form):
    via = " (via package.json script `%s`)" % CTX[-1] if CTX else ""
    block("Direct `wrangler deploy` is not allowed%s: matched `%s`. Production deploys go through git "
          "(push/merge to the production branch). See the `ship` skill. Rollback: `npx wrangler rollback`. "
          "`--dry-run` is allowed." % (via, form))


def hooks_block(why):
    block("Skipping git hooks is not allowed unless the user explicitly asks (%s); "
          "fix the failing check instead." % why)


def split_segments(cmd):
    """Split on ; & | newline ( ) ` outside quotes. Raises ValueError on unbalanced quotes."""
    cmd = cmd.replace("\\\n", " ")
    segs, buf, q, i, n = [], [], None, 0, len(cmd)
    while i < n:
        c = cmd[i]
        if q:
            buf.append(c)
            if c == "\\" and q == '"' and i + 1 < n:
                buf.append(cmd[i + 1])
                i += 2
                continue
            if c == q:
                q = None
        elif c == "\\":
            buf.append(c)
            if i + 1 < n:
                buf.append(cmd[i + 1])
            i += 2
            continue
        elif c in "'\"":
            q = c
            buf.append(c)
        elif c in ";&|\n()`":
            segs.append("".join(buf))
            buf = []
        elif c == "#" and (not buf or buf[-1] in " \t"):
            while i < n and cmd[i] != "\n":
                i += 1
            continue
        else:
            buf.append(c)
        i += 1
    if q:
        raise ValueError("unbalanced quote")
    segs.append("".join(buf))
    return [s for s in segs if s.strip()]


def analyze(cmd, depth=0, seen=frozenset(), secrets=True):
    if depth > MAX_DEPTH:
        return
    bodies = []

    def drop(m):
        first_line = cmd[cmd.rfind("\n", 0, m.start()) + 1:m.start()]
        words = first_line.split()
        opener = m.group(0).split("\n", 1)[0]  # the rest of the heredoc line: `cat <<EOF | bash`
        if (words and os.path.basename(words[0]) in SHELLS) or PIPE_TO_SHELL.search(opener):  # heredoc fed to a shell is code
            bodies.append("\n".join(m.group(0).split("\n")[1:-1]))
        return ""

    cmd = HEREDOC.sub(drop, cmd)
    for body in bodies:
        analyze(body, depth + 1, seen, secrets)
    segs = split_segments(cmd)
    if PIPE_TO_SHELL.search(QUOTED.sub("''", cmd)):  # SEC-003: echo "npx wrangler deploy" | sh runs the echoed text
        for seg in segs:
            toks = shlex.split(seg)
            if toks and os.path.basename(toks[0]) in ("echo", "printf"):
                analyze(" ".join(t for t in toks[1:] if not t.startswith("-")), depth + 1, seen, secrets)
    if secrets and re.search(r"\bxargs\b", QUOTED.sub("''", cmd)):  # find ... | xargs cat: same as find -exec cat
        toks = [shlex.split(s) for s in segs]
        for t in toks:
            if t and os.path.basename(t[0]) == "find" and "-exec" not in t:
                for u in toks:
                    if u and os.path.basename(u[0]) == "xargs":
                        rest = [a for a in u[1:] if not a.startswith("-") and not a.isdigit()]
                        if rest:
                            find_check(t + ["-exec", rest[0], "{}", "+"])
    for seg in segs:
        for m in SUBST.finditer(SINGLE_QUOTED.sub("''", seg)):
            analyze(m.group(1) or m.group(2) or "", depth + 1, seen, secrets)
        inspect(shlex.split(seg), depth, seen, secrets, set(), True)


def inspect(tokens, depth, seen, secrets, envs, top):
    tokens = list(tokens)
    while tokens and ASSIGN.match(tokens[0]):
        envs.add(ASSIGN.match(tokens.pop(0)).group(1))
    if not tokens or depth > MAX_DEPTH:
        return
    prog, args = os.path.basename(tokens[0]), tokens[1:]
    if top and secrets:
        check_secrets(prog, tokens, args)
    if prog in SKIP_WORDS or prog == "env":
        rest = args
        while rest and (rest[0].startswith("-") or ASSIGN.match(rest[0]) or re.match(r"^\d+$", rest[0])):
            if ASSIGN.match(rest[0]):
                envs.add(ASSIGN.match(rest[0]).group(1))
            rest = rest[1:]
        return inspect(rest, depth + 1, seen, secrets, envs, False)
    if prog in SHELLS:
        run_script_file(prog, tokens, args, depth, seen)
        for i, a in enumerate(args):
            if a.startswith("-") and not a.startswith("--") and "c" in a and i + 1 < len(args):
                return analyze(args[i + 1], depth + 1, seen, secrets)
            if a == "<<<" and i + 1 < len(args):
                return analyze(args[i + 1], depth + 1, seen, secrets)
        return
    if prog == "eval":
        return analyze(" ".join(args), depth + 1, seen, secrets)
    if INTERPRETERS.match(prog):
        scan_inline_code(args)
    run_script_file(prog, tokens, args, depth, seen)
    if prog in ("npx", "bunx", "pnpx"):
        return run_wrapper(args, depth, seen, secrets, envs, {"-p", "--package"})
    if prog in ("npm", "pnpm", "yarn", "bun"):
        return package_manager(prog, args, depth, seen, secrets, envs)
    if prog == "node" and args and WRANGLER.match(re.sub(r"\.m?js$", "", os.path.basename(args[0]))):
        return wrangler(args[1:])
    if WRANGLER.match(prog):
        return wrangler(args)
    if prog == "git":
        return git(args, envs)


def has_deploy_text(text):
    """A deploy command (not a dry run) in free text, one line at a time; `#` comment lines are skipped."""
    for line in text.splitlines():
        m = DEPLOY_TEXT.search(line)
        if m and not line.lstrip().startswith("#") and "--dry-run" not in line:
            return m.group(0)
    return None


def scan_inline_code(args):
    """`python -c CODE`, `node -e CODE`: the argument is a program, so look for a deploy command in it."""
    for i, a in enumerate(args):
        is_flag = a in CODE_FLAGS or (re.match(r"^-[A-Za-z]+$", a) and a[-1] in "ce")
        if is_flag and i + 1 < len(args):
            hit = has_deploy_text(args[i + 1])
            if hit:
                deploy_block(hit + " (inside an inline program)")


def local_file(token):
    """Absolute path of a regular, small file under the repo that `token` names, else None."""
    if not token or token.startswith("-") or "$" in token:
        return None
    root = os.path.realpath(ROOT)
    path = os.path.realpath(os.path.join(root, os.path.expanduser(token)))
    if path.startswith(root + os.sep) and os.path.isfile(path) and os.path.getsize(path) <= SCAN_LIMIT:
        return path
    return None


def run_script_file(prog, tokens, args, depth, seen):
    """Best effort: a local script the command executes (`./x.sh`, `bash x.sh`, `python x.py`, `source x`) is
    scanned for a deploy command. Shell scripts are also analysed, so `npm run deploy` inside is caught."""
    if "/" in tokens[0] and not INTERPRETERS.match(prog) and prog not in SHELLS:
        target = tokens[0]
    elif prog in SHELLS or INTERPRETERS.match(prog) or prog in ("source", "."):
        if prog in SHELLS and any(re.match(r"^-[A-Za-z]*c", a) for a in args):
            return  # `bash -c`: handled as inline code
        target = next((a for a in args if not a.startswith("-")), None)
    else:
        return
    path = local_file(target)
    if not path or path in seen:
        return
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return
    hit = has_deploy_text(text)
    if hit:
        block("Direct `wrangler deploy` is not allowed: the script `%s` that this command runs contains `%s`. "
              "Production deploys go through git (see the `ship` skill); remove the deploy from the script."
              % (os.path.relpath(path, ROOT), hit))
    first = text.split("\n", 1)[0]
    if path.endswith((".sh", ".bash")) or (first.startswith("#!") and "sh" in first):
        try:
            analyze(text, depth + 1, seen | {path}, False)
        except ValueError:
            pass


def run_wrapper(args, depth, seen, secrets, envs, value_flags):
    """npx/bunx/dlx/exec: skip the wrapper's own flags (and `--`), inspect the program that runs."""
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-c", "--call") and i + 1 < len(args):
            return analyze(args[i + 1], depth + 1, seen, secrets)
        if a == "--":
            i += 1
            break
        if not a.startswith("-"):
            break
        i += 2 if (a in value_flags) else 1
    return inspect(args[i:], depth + 1, seen, secrets, envs, False)


def wrangler(args):
    pos, i = [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            break
        if a in WRANGLER_VALUE_FLAGS:
            i += 2
            continue
        if not a.startswith("-"):
            pos.append(a)
        i += 1
    dry = any(a == "--dry-run" or (a.startswith("--dry-run=") and a.split("=", 1)[1].lower() not in ("false", "0"))
              for a in args)
    words = ("deploy", "publish")
    form = None
    if pos and pos[0] in words:
        form = pos[0]
    elif len(pos) > 1 and pos[0] in ("pages", "versions") and pos[1] in words:
        form = pos[0] + " " + pos[1]
    if form and not dry:  # dry runs build locally, upload nothing; applies to this invocation only
        deploy_block("wrangler " + form)


def package_manager(prog, args, depth, seen, secrets, envs):
    pos, i = [], 0  # (index, token) of positionals before `--`
    while i < len(args):
        a = args[i]
        if a == "--":
            break
        if a in PM_VALUE_FLAGS:
            i += 2
            continue
        if not a.startswith("-"):
            pos.append((i, a))
        i += 1
    if not pos:
        return
    idx, cmd = pos[0]
    if cmd in EXEC_ALIASES:
        return run_wrapper(args[idx + 1:], depth, seen, secrets, envs, {"-p", "--package"})
    if cmd in RUN_ALIASES:
        if len(pos) < 2:
            return
        name = pos[1][1]
    elif prog == "npm" and cmd not in LIFECYCLE:
        return
    else:
        name = cmd
    scripts = package_scripts()
    for n in ("pre" + name, name, "post" + name):
        text = scripts.get(n)
        if isinstance(text, str) and n not in seen:
            CTX.append(name)
            try:
                analyze(text, depth + 1, seen | {n}, False)
            finally:
                CTX.pop()


def is_cfg_hookspath(v):
    return v.lower().startswith("core.hookspath")


def git(args, envs):
    i, hookspath, sub, rest = 0, False, None, []
    while i < len(args):
        a = args[i]
        if a in GIT_VALUE_GLOBALS:
            if a in ("-c", "--config-env") and i + 1 < len(args) and is_cfg_hookspath(args[i + 1]):
                hookspath = True
            i += 2
            continue
        if a.startswith("-c") and not a.startswith("--") and is_cfg_hookspath(a[2:]):
            hookspath = True
        if a.lower().startswith("--config-env=") and is_cfg_hookspath(a.split("=", 1)[1]):
            hookspath = True
        if not a.startswith("-"):
            sub, rest = a, args[i + 1:]
            break
        i += 1
    if sub not in ("push", "commit"):
        return
    if hookspath:
        hooks_block("`-c core.hooksPath=` replaces the hooks directory")
    if sub == "push":
        if envs & {"CI", "GITHUB_ACTIONS"}:
            hooks_block("a `CI=`/`GITHUB_ACTIONS=` prefix makes the pre-push hook skip")
        for a in rest:
            if a == "--":
                break
            if a.startswith("--no-v") and "--no-verify".startswith(a):
                hooks_block("--no-verify")
        return
    skip = False
    for a in rest:
        if skip:
            skip = False
            continue
        if a == "--":
            break
        if a.startswith("--"):
            if a.startswith("--no-v") and "--no-verify".startswith(a):
                hooks_block("--no-verify")
            skip = a in ("--message", "--file", "--author", "--date", "--reuse-message", "--reedit-message",
                         "--template", "--cleanup", "--fixup", "--squash")
        elif a.startswith("-") and len(a) > 1:
            for ch in a[1:]:  # combined short flags: -nm, -an. -n is --no-verify for commit only
                if ch == "n":
                    hooks_block("-n is --no-verify for `git commit`")
                if ch in COMMIT_VALUE_LETTERS:
                    skip = a.endswith(ch)
                    break


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


def main():
    ev = read_event()
    if ev.get("tool_name") != "Bash":
        return
    cmd = (ev.get("tool_input") or {}).get("command", "")
    DOTGLOB[0] = "dotglob" in cmd
    try:
        analyze(cmd)
    except ValueError:  # unparseable: fail closed for deploy-like text, open otherwise
        if DEPLOY_HINT.search(cmd) and re.search(r"\b(deploy|publish)\b", cmd) and "--dry-run" not in cmd:
            block("Could not parse this command and it looks like `wrangler deploy`; deploys go through git "
                  "(`ship` skill). Fix the quoting if this was not a deploy.")


if __name__ == "__main__":
    main()
