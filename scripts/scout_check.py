#!/usr/bin/env python3
"""Check an open-source scout note (docs/research/<slug>-scout.md). Usage: scout_check.py <note>.

Exit 1 with a plain reason when: no single `Recommendation: adopt|borrow|build`; adopt/borrow without a licence
line for the pick, or with a copyleft/unknown licence and no `Needs user: yes`; more than 5 candidates; over 60 lines;
`Scouted: no` with adopt/borrow. Policy: docs/operating-model/AGENT-ROUTING.md (Scout open source). Stdlib only.
"""
import re
import sys

MAX_LINES, MAX_CANDIDATES = 60, 5
MIN_CANDIDATES = 3
# Allow-list: permissive licences the pick may carry without asking. Anything else (copyleft, source-available such as
# BUSL or SSPL, commercial, unknown, n/a) needs `Needs user: yes`.
ALLOW = re.compile(r"^(MIT|MIT-0|Apache-2\.0|BSD-[23]-Clause|0BSD|ISC|MPL-2\.0|Unlicense|CC0-1\.0|Zlib|PSF-2\.0|Python-2\.0|BSL-1\.0)$", re.I)


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
    if n < MIN_CANDIDATES:
        out.append("%d candidates: %s needs at least %d compared" % (n, rec, MIN_CANDIDATES))
    tail = text[re.search(r"(?mi)^\s*Recommendation:", text).start():]
    lic = re.search(r"(?mi)^\s*Licen[cs]e:\s*(.*?)\s*$", tail)
    if not lic or not lic.group(1) or lic.group(1).startswith("<"):
        out.append("recommendation %s has no licence line for the pick (`Licence: <SPDX id>`)" % rec)
    elif not ALLOW.match(lic.group(1).strip()):
        nu = re.search(r"(?mi)^\s*Needs user:\s*(.*?)\s*$", tail)
        if not nu or nu.group(1).lower() != "yes":
            out.append("licence '%s' is not on the permissive list (copyleft, source-available, commercial, unknown "
                       "or not an SPDX id): set `Needs user: yes`" % lic.group(1))
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
