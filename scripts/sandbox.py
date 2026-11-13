#!/usr/bin/env python3
"""Shared sandbox and headless-claude runner (ADR 0006 evals, ADR 0009 fixer runner). Stdlib only, no model call here
unless run_claude() is called. Extracted from scripts/evals.py without a change of behaviour.

  scrubbed_env(src, home, tmp)   allow-listed environment, throwaway HOME and TMPDIR
  sandbox_problem()              None when Claude Code's Bash sandbox can run, else why not
  claude_cmd / run_claude        headless `claude -p` with stream-json output, acceptEdits and an explicit tool list
  parse_events / usage_cost      read the stream-json transcript: events, tokens, cumulative cost
  git(args, cwd)                 git with a fixed identity and no global config (never reads or writes ~/.gitconfig)
Policy: docs/policies/evals.md (isolation), docs/policies/runner.md.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

# Environment variables the sandboxed agent may see. Everything else (CLOUDFLARE_*, GITHUB_*, GH_*, AWS_*, cloud and
# SSH variables, CLAUDE_CODE_* of this session) is dropped. The first group is what claude needs to reach the API.
ENV_ALLOW = ("PATH", "LANG", "LC_ALL", "TERM", "TZ",
             "ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
             "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
             "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")
# Claude Code's Bash sandbox (bubblewrap + socat on Linux, Seatbelt on macOS) for eval runs (TD-010): no network
# for the agent's commands (empty allow list; claude itself still reaches the API), no read of the login
# directory, and no hole to run outside it. failIfUnavailable makes a missing sandbox a hard stop instead of a
# silent fallback. CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1 (set in scrubbed_env) strips the model credential from
# the commands' environment. EVALS_SANDBOX=off opts out (the run is then not isolated).
SANDBOX = {"sandbox": {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                       "autoAllowBashIfSandboxed": True, "network": {"allowedDomains": []},
                       "filesystem": {"denyRead": ["~/.claude", "~/.claude.json"]}}}
TOOLS = "Bash,Read,Write,Edit,MultiEdit,Glob,Grep,Skill,Task,Agent,TodoWrite"
READ_TOOLS = "Read,Glob,Grep"  # reviewer: reads, cannot edit or run commands
# Reviewer: only read tools exist for it (--tools restricts the built-in set; --allowedTools alone only pre-approves), and
# permission mode dontAsk denies anything not pre-approved. The deny list is belt and braces.
DENY_TOOLS = "Bash Edit Write MultiEdit NotebookEdit Task Agent WebFetch WebSearch Skill"
GIT_ID = ["-c", "user.name=eval", "-c", "user.email=eval@example.invalid", "-c", "commit.gpgsign=false"]


def git(args, cwd, **kw):
    return subprocess.run(["git", *GIT_ID, *args], cwd=cwd, capture_output=True, text=True, check=kw.get("check", True),
                          env={"PATH": os.environ.get("PATH", ""), "HOME": cwd, "GIT_CONFIG_GLOBAL": os.devnull,
                               "GIT_CONFIG_SYSTEM": os.devnull})


def scrubbed_env(src, home, tmp):
    """Allow-listed variables only, HOME and TMPDIR pointing at throwaway dirs. EVALS_HOME=real keeps the real HOME
    (needed where claude logs in via ~/.claude; the agent can then read that login, see docs/policies/evals.md)."""
    env = {k: src[k] for k in ENV_ALLOW if k in src}
    env.update(HOME=src.get("HOME", home) if src.get("EVALS_HOME") == "real" else home, TMPDIR=tmp,
               GIT_TERMINAL_PROMPT="0", CODEGRAPH_TELEMETRY="0",
               PYTHONDONTWRITEBYTECODE="1")  # hooks run by the agent must not leave .pyc caches (pilot 2: false fixer-touched-protected)
    if src.get("EVALS_SANDBOX") != "off":
        env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] = "1"
    return env


def sandbox_problem(src=None, which=shutil.which, platform=sys.platform):
    """None when the Bash sandbox can run (or is opted out), else why not. Checked before any money is spent."""
    if (os.environ if src is None else src).get("EVALS_SANDBOX") == "off":
        return None
    if platform.startswith("linux"):
        missing = [t for t in ("bwrap", "socat") if not which(t)]
        if missing:
            return ("the Bash sandbox needs %s on PATH (apt-get install -y bubblewrap socat); "
                    "or set EVALS_SANDBOX=off to run without network isolation" % " and ".join(missing))
    return None


def claude_cmd(model, max_turns, sandbox=True, tools=TOOLS, max_budget=None, reviewer=False):
    cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose", "--include-hook-events",
           "--model", model, "--max-turns", str(max_turns), "--permission-mode", "dontAsk" if reviewer else "acceptEdits",
           "--allowedTools", tools, "--no-session-persistence"] + (["--settings", json.dumps(SANDBOX)] if sandbox else [])
    if reviewer:
        cmd += ["--tools", tools, "--disallowedTools", DENY_TOOLS]
    if max_budget is not None:  # claude stops itself at this spend (ADR 0009 hardening)
        cmd += ["--max-budget-usd", "%.4f" % max(float(max_budget), 0.01)]
    return cmd


def run_claude(prompt, model, max_turns, cwd, env, timeout, tools=TOOLS, max_budget=None, reviewer=False):
    """Real model call. The prompt goes on stdin (--allowedTools is variadic and would swallow a positional)."""
    try:
        p = subprocess.run(claude_cmd(model, max_turns, os.environ.get("EVALS_SANDBOX") != "off", tools, max_budget, reviewer), input=prompt,
                           cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False)
        return p.stdout, p.returncode
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return out, 124


def parse_events(text):
    ev = []
    for line in (text or "").splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            ev.append(obj)
    return ev


def usage_cost(events):
    """({tokens_in, tokens_cache, tokens_out}, cost_usd, turns, has_result) from the `result` events of a transcript.
    Cost is cumulative, so the maximum is taken; tokens and turns are summed (a background subagent adds results)."""
    res = [e for e in events if e.get("type") == "result"]
    u = {k: sum((e.get("usage") or {}).get(k, 0) or 0 for e in res) for k in
         ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}
    tok = {"tokens_in": u["input_tokens"], "tokens_cache": u["cache_creation_input_tokens"] + u["cache_read_input_tokens"],
           "tokens_out": u["output_tokens"]}
    cost = round(max([float(e.get("total_cost_usd") or 0) for e in res] or [0]), 5)
    return tok, cost, sum(e.get("num_turns", 0) or 0 for e in res), bool(res)


# ---- sandbox for code that lives in a worktree (ADR 0009 hardening) ----
# Fixer-written code (product code, tests, the acceptance command, build and lint commands) runs on the runner's side of the
# fence too: the runner evaluates it with an allow-listed environment without model credentials and inside bubblewrap with no
# network, a throwaway HOME and TMPDIR, the main project directory and the real home hidden, and the scripts and gate inputs
# mounted read-only. No bwrap (or not Linux): refuse, like evals. EVALS_SANDBOX=off opts out (scrubbed env only).
RO_TREE = ("scripts", "tests/acceptance", "factory.json", ".claude", ".github", "metrics/acceptance-baseline.json")
NO_CREDS = ("PATH", "LANG", "LC_ALL", "TERM", "TZ")


class SandboxUnavailable(Exception):
    pass


def tree_sandbox_problem(src=None, which=shutil.which, platform=sys.platform):
    if (os.environ if src is None else src).get("EVALS_SANDBOX") == "off":
        return None
    if not platform.startswith("linux"):
        return "evaluating fixer code needs bubblewrap (Linux); set EVALS_SANDBOX=off to run it without isolation"
    if not which("bwrap"):
        return "evaluating fixer code needs bwrap on PATH (apt-get install -y bubblewrap); or set EVALS_SANDBOX=off to run it without isolation"
    return None


def eval_env(src, home, tmp):
    """Environment for code under test: PATH, locale and nothing else (no model credentials, no proxies: it has no network)."""
    env = {k: src[k] for k in NO_CREDS if k in src}
    env.update(HOME=home, TMPDIR=tmp, GIT_TERMINAL_PROMPT="0", PYTHONDONTWRITEBYTECODE="1")
    return env


class TreeSandbox:
    """Runs commands for one worktree: argv() wraps a command in bwrap, env is the scrubbed environment, close() removes the
    throwaway HOME and TMPDIR. gate_wrap() is the hook gate.WRAP expects."""

    def __init__(self, tree, extra_rw=(), src=None, timeout=1800):
        src = os.environ if src is None else src
        problem = tree_sandbox_problem(src)
        if problem:
            raise SandboxUnavailable(problem)
        self.off = src.get("EVALS_SANDBOX") == "off"
        self.tree, self.timeout = os.path.realpath(tree), timeout
        self.extra_rw = [os.path.realpath(d) for d in extra_rw]
        self.tmp = tempfile.mkdtemp(prefix="tree-sandbox-")
        self.home, self.scratch = os.path.join(self.tmp, "home"), os.path.join(self.tmp, "tmp")
        os.makedirs(self.home)
        os.makedirs(self.scratch)
        self.env = eval_env(src, self.home, self.scratch)
        self.env["DANFACTORY_TREE_SANDBOX"] = "1"  # tests that need a nested sandbox or a writable repo skip themselves (pilot 2)
        self.common = self.hide = None
        p = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=self.tree, capture_output=True, text=True,
                           env={"PATH": src.get("PATH", ""), "HOME": self.tmp, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull})
        if p.returncode == 0 and p.stdout.strip():
            self.common = os.path.realpath(p.stdout.strip())
            top = os.path.dirname(self.common)
            if os.path.basename(self.common) == ".git" and self.tree.startswith(top + os.sep):
                self.hide = top  # the main project directory (its .env, other worktrees): hidden, only .git comes back read-only
        self.hidden_homes = [h for h in {os.path.realpath(src.get("HOME") or "/root"), "/root"}
                             if h != "/" and not os.path.realpath(sys.executable).startswith(h + os.sep)]

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def argv(self, cmd, shell=False, extra_rw=()):
        inner = ["sh", "-c", cmd] if shell else list(cmd)
        pre = ["timeout", "-k", "10", str(self.timeout)] if shutil.which("timeout") else []
        if self.off:
            return pre + inner
        a = ["bwrap", "--die-with-parent", "--new-session", "--unshare-all", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
             "--tmpfs", "/tmp"]
        for d in sorted(self.hidden_homes) + ([self.hide] if self.hide else []):
            a += ["--tmpfs", d]
        a += ["--bind", self.tree, self.tree]
        for rel in RO_TREE + (".git",):
            path = os.path.join(self.tree, rel)
            if os.path.exists(path):
                a += ["--ro-bind", path, path]
        if self.common:
            a += ["--ro-bind", self.common, self.common]
        for d in [self.home, self.scratch] + self.extra_rw + [os.path.realpath(x) for x in extra_rw]:
            a += ["--bind", d, d]
        return pre + a + ["--chdir", self.tree] + inner

    def acceptance_env(self):
        """Environment for scripts/acceptance.py itself (runner-trusted code): it wraps the tests it starts in its own sandbox."""
        return dict(self.env, ACCEPTANCE_SANDBOX="1", **({"EVALS_SANDBOX": "off"} if self.off else {}))

    def gate_wrap(self, cmd, root, shell):
        """(cmd, shell, env) for gate.sh(): git runs as is, the acceptance runner sandboxes its tests itself, the rest runs wrapped."""
        if not shell and cmd and cmd[0] == "git":
            return cmd, shell, None
        if not shell and list(cmd[:2]) == ["python3", "scripts/acceptance.py"]:
            return cmd, shell, self.acceptance_env()
        return self.argv(cmd, shell), False, self.env


# ---- metrics/runner.jsonl: one durable row per fixer attempt, park, stop or second reading (ADR 0009) ----
RUNNER_ROWS = os.path.join("metrics", "runner.jsonl")


def append_row(path, row):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
