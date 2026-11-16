#!/usr/bin/env python3
"""Check an open-source scout note (docs/research/<slug>-scout.md). Usage: scout_check.py <note>.

Exit 1 with a plain reason when: no single `Recommendation: adopt|borrow|build`; adopt/borrow without a licence
line for the pick, or with a copyleft/unknown licence and no `Needs user: yes`; more than 5 candidates; over 60 lines;
`Scouted: no` with adopt/borrow. Policy: docs/operating-model/AGENT-ROUTING.md (Scout open source). Stdlib only.
"""
import re
import sys

MAX_LINES, MAX_CANDIDATES = 60, 5
DENY = re.compile(r"gpl|sspl|unknown|none|unlicensed|proprietary|paid", re.I)  # copyleft, unknown or paid: ask the user


def problems(text):
    lines = text.splitlines()
    out = []
    if len(lines) > MAX_LINES:
        out.append("note has %d lines, the cap is %d" % (len(lines), MAX_LINES))
    recs = re.findall(r"(?mi)^\s*Recommendation:\s*(.*?)\s*$", text)
    if len(recs) != 1 or recs[0].lower() not in ("adopt", "borrow", "build"):
        out.append("need exactly one line `Recommendation: adopt|borrow|build` (found %s)" % (recs or "none"))
        return out
    rec = recs[0].lower()
    m = re.search(r"(?mis)^##\s*Candidates\b(.*?)(?=^##\s[^#]|\Z)", text)
    n = len(re.findall(r"(?m)^###\s", m.group(1))) if m else 0
    if n > MAX_CANDIDATES:
        out.append("%d candidates, the cap is %d" % (n, MAX_CANDIDATES))
    if rec == "build":
        return out
    scouted = re.search(r"(?mi)^\s*Scouted:\s*(.*?)\s*$", text)
    if scouted and scouted.group(1).lower().startswith("no"):
        out.append("`Scouted: no` cannot recommend %s; recommend build" % rec)
    tail = text[text.lower().rfind("recommendation:"):]
    lic = re.search(r"(?mi)^\s*Licen[cs]e:\s*(.*?)\s*$", tail)
    if not lic or not lic.group(1) or lic.group(1).startswith("<"):
        out.append("recommendation %s has no licence line for the pick (`Licence: <SPDX id>`)" % rec)
    elif DENY.search(lic.group(1)):
        nu = re.search(r"(?mi)^\s*Needs user:\s*(\w+)", tail)
        if not nu or nu.group(1).lower() != "yes":
            out.append("licence '%s' is copyleft, unknown or paid: set `Needs user: yes`" % lic.group(1))
    return out


def main(argv):
    if len(argv) != 2:
        print("usage: scout_check.py <note>", file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as e:
        print("cannot read %s: %s" % (argv[1], e), file=sys.stderr)
        return 2
    probs = problems(text)
    for p in probs:
        print("scout_check: %s" % p, file=sys.stderr)
    if not probs:
        print("scout note ok")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
