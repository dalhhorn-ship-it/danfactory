#!/usr/bin/env python3
"""SessionEnd: sum token usage from the session transcript into metrics/tokens.jsonl."""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, read_event  # noqa: E402

FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def summarize(transcript_path):
    per_msg = {}
    models = {}
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


def main():
    ev = read_event()
    tp = ev.get("transcript_path")
    if not tp or not os.path.isfile(tp):
        return
    totals, by_model, turns = summarize(tp)
    if not turns:
        return
    row = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "kind": "session",
        "session_id": ev.get("session_id"),
        "reason": ev.get("reason"),
        "assistant_messages": turns,
        "total_tokens": sum(totals.values()),
        **totals,
        "by_model": by_model,
    }
    os.makedirs(os.path.join(ROOT, "metrics"), exist_ok=True)
    with open(os.path.join(ROOT, "metrics", "tokens.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
