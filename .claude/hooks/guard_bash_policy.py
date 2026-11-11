#!/usr/bin/env python3
"""PreToolUse (Bash): enforce deploy, git-hook and secret-file policy on the command text itself.

settings.json deny rules match command prefixes only, so `bunx wrangler deploy`, `npm run deploy`
or `git push origin main --no-verify` slip through. This hook tokenises the command (shlex), splits
compound commands, follows `bash -c`/`eval`/command substitution and package.json scripts, and
inspects programs, not quoted text. Rollback stays allowed.

It is ADVISORY: a determined caller can still hide a deploy (python -c, generated scripts). The real
protection is credential scoping (docs/policies/security.md). Stdlib only, Python 3.8+.
"""
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
        for i, a in enumerate(args):
            if a.startswith("-") and not a.startswith("--") and "c" in a and i + 1 < len(args):
                return analyze(args[i + 1], depth + 1, seen, secrets)
            if a == "<<<" and i + 1 < len(args):
                return analyze(args[i + 1], depth + 1, seen, secrets)
        return
    if prog == "eval":
        return analyze(" ".join(args), depth + 1, seen, secrets)
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


def check_secrets(prog, tokens, args):
    """Block reading/writing .env* and .dev.vars* via Bash (listing/testing/ignore-checks are allowed)."""
    if prog in ("ls", "test", "[", "[["):
        return
    if prog == "git" and git_subcommand(args) in ("check-ignore", "status"):
        return
    for t in tokens:
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
    try:
        analyze(cmd)
    except ValueError:  # unparseable: fail closed for deploy-like text, open otherwise
        if DEPLOY_HINT.search(cmd) and re.search(r"\b(deploy|publish)\b", cmd) and "--dry-run" not in cmd:
            block("Could not parse this command and it looks like `wrangler deploy`; deploys go through git "
                  "(`ship` skill). Fix the quoting if this was not a deploy.")


if __name__ == "__main__":
    main()
