#!/usr/bin/env python3
"""SessionEnd: record token usage (main session + its subagents) into metrics/tokens.jsonl.

`weighted_tokens` is the cost-relevant number: input-token equivalents using the usual Claude
price ratios (input 1, output 5, cache write 1.25, cache read 0.1). Raw totals are dominated by
cheap cache reads, so budgets and the dashboard use the weighted figure.
Skipped in the un-bootstrapped template itself (project.name empty) so template maintenance
sessions don't pollute new projects' metrics.
"""
import datetime
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, read_event, template_mode  # noqa: E402

FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
WEIGHTS = {"input_tokens": 1.0, "output_tokens": 5.0, "cache_creation_input_tokens": 1.25,
           "cache_read_input_tokens": 0.1}


def weighted(usage):
    return round(sum(WEIGHTS[f] * usage.get(f, 0) for f in FIELDS))


def summarize(transcript_path):
    per_msg, models = {}, {}
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            msg = rec.get("message") or {}
            usage = msg.get("usage")
            if rec.get("type") != "assistant" or not usage:
                continue
            key = msg.get("id") or rec.get("uuid")
            per_msg[key] = usage  # streamed chunks repeat the id; keep the last
            models[key] = msg.get("model", "unknown")
    totals = {f: 0 for f in FIELDS}
    by_model = {}
    for key, usage in per_msg.items():
        m = by_model.setdefault(models[key], {f: 0 for f in FIELDS})
        for f in FIELDS:
            v = int(usage.get(f) or 0)
            totals[f] += v
            m[f] += v
    return totals, by_model, len(per_msg)


def count_compactions(transcript_path):
    n = 0
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            if "compact" not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("subtype") == "compact_boundary" or rec.get("isCompactSummary"):
                n += 1
    return n


def subagent_transcripts(transcript_path):
    base = os.path.splitext(transcript_path)[0]  # <dir>/<session_id>.jsonl -> <dir>/<session_id>/subagents/
    return sorted(glob.glob(os.path.join(base, "subagents", "*.jsonl")))


def merge(into, extra):
    for f in FIELDS:
        into[f] = into.get(f, 0) + extra.get(f, 0)


def main():
    ev = read_event()
    tp = ev.get("transcript_path")
    if not tp or not os.path.isfile(tp):
        return
    if template_mode():
        return  # the template repo itself, not a project
    totals, by_model, turns = summarize(tp)
    sub_totals = {f: 0 for f in FIELDS}
    subs = subagent_transcripts(tp)
    for sp in subs:
        t, bm, _ = summarize(sp)
        merge(sub_totals, t)
        for model, usage in bm.items():
            merge(by_model.setdefault(model, {f: 0 for f in FIELDS}), usage)
    if not turns and not subs:
        return
    all_totals = dict(totals)
    merge(all_totals, sub_totals)
    row = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "kind": "session",
        "session_id": ev.get("session_id"),
        "reason": ev.get("reason"),
        "assistant_messages": turns,
        "subagents": len(subs),
        "compactions": count_compactions(tp),
        "total_tokens": sum(all_totals.values()),
        "weighted_tokens": weighted(all_totals),
        "main_weighted_tokens": weighted(totals),
        "subagent_weighted_tokens": weighted(sub_totals),
        **all_totals,
        "by_model": by_model,
    }
    os.makedirs(os.path.join(ROOT, "metrics"), exist_ok=True)
    with open(os.path.join(ROOT, "metrics", "tokens.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
