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
               GIT_TERMINAL_PROMPT="0", CODEGRAPH_TELEMETRY="0")
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


def claude_cmd(model, max_turns, sandbox=True, tools=TOOLS):
    return ["claude", "-p", "--output-format", "stream-json", "--verbose", "--include-hook-events",
            "--model", model, "--max-turns", str(max_turns), "--permission-mode", "acceptEdits",
            "--allowedTools", tools, "--no-session-persistence"] + (["--settings", json.dumps(SANDBOX)] if sandbox else [])


def run_claude(prompt, model, max_turns, cwd, env, timeout, tools=TOOLS):
    """Real model call. The prompt goes on stdin (--allowedTools is variadic and would swallow a positional)."""
    try:
        p = subprocess.run(claude_cmd(model, max_turns, os.environ.get("EVALS_SANDBOX") != "off", tools), input=prompt,
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


# ---- metrics/runner.jsonl: one durable row per fixer attempt, park, stop or second reading (ADR 0009) ----
RUNNER_ROWS = os.path.join("metrics", "runner.jsonl")


def append_row(path, row):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
