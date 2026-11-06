#!/usr/bin/env bash
# Bounded wait until a deployment is live; with --record, logs push-to-live time (ok) or the timeout (fail).
# Used by the deploy-watcher subagent in the background, so the main agent never waits.
#
#   bash scripts/wait-for-url.sh --url https://app.example.workers.dev/version \
#        [--expect <text, e.g. short git sha>] [--timeout 360] [--since <epoch of push>] [--record prod]
#
# Exit 0: live (and expected text seen). Exit 1: timed out. Exit 2: usage error.
# Polls with backoff (5s -> 30s cap). Prints one line at the end, nothing per attempt.
set -uo pipefail
URL="" EXPECT="" TIMEOUT=360 SINCE="" RECORD=""
while [ $# -gt 0 ]; do
  case "$1" in
    --url) URL="$2"; shift 2 ;;
    --expect) EXPECT="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --since) SINCE="$2"; shift 2 ;;
    --record) RECORD="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[ -n "$URL" ] || { echo "usage: wait-for-url.sh --url URL [--expect TEXT] [--timeout S] [--since EPOCH] [--record ENV]" >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
start=$(date +%s); delay=5; attempts=0; last=""
while :; do
  attempts=$((attempts + 1))
  body="$(curl -fsS --max-time 10 "$URL" 2>&1)"; rc=$?
  if [ $rc -eq 0 ] && { [ -z "$EXPECT" ] || printf '%s' "$body" | grep -qF -- "$EXPECT"; }; then
    now=$(date +%s); secs=$((now - ${SINCE:-$start}))
    echo "LIVE $URL after ${secs}s${SINCE:+ since push} ($attempts checks)${EXPECT:+, saw '$EXPECT'}"
    if [ -n "$RECORD" ]; then
      python3 "$ROOT/scripts/metrics.py" deploy --env "$RECORD" --seconds "$secs" --status ok >/dev/null
    fi
    exit 0
  fi
  [ $rc -ne 0 ] && last="unreachable: ${body:0:120}" || last="reachable but '$EXPECT' not served yet"
  elapsed=$(( $(date +%s) - start ))
  if [ $elapsed -ge "$TIMEOUT" ]; then
    echo "TIMEOUT after ${elapsed}s ($attempts checks) — $last"
    if [ -n "$RECORD" ]; then  # count it, so the deploy failure rate is real
      python3 "$ROOT/scripts/metrics.py" deploy --env "$RECORD" --seconds "$elapsed" --status fail >/dev/null
    fi
    exit 1
  fi
  remaining=$((TIMEOUT - elapsed))
  sleep $(( delay < remaining ? delay : remaining ))
  delay=$(( delay * 2 > 30 ? 30 : delay * 2 ))
done
