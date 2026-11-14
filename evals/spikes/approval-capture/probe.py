#!/usr/bin/env python3
"""TRUST-2 spike probe: log what each hook event receives. Never blocks, never prints."""
import json, os, sys, time
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe.jsonl")
def short(v, n=400):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s[:n]
try:
    raw = sys.stdin.read()
    d = json.loads(raw) if raw.strip() else {}
    row = {"ts": time.strftime("%H:%M:%S"), "event": d.get("hook_event_name"), "keys": sorted(d.keys()),
           "permission_mode": d.get("permission_mode"), "tool_name": d.get("tool_name")}
    for k in ("prompt", "tool_input", "tool_response", "message", "source"):
        if k in d:
            row[k] = short(d[k])
    tp = d.get("transcript_path")
    if tp and os.path.isfile(tp) and d.get("hook_event_name") == "UserPromptSubmit":
        last = None
        with open(tp, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if r.get("type") == "user" and r.get("turnOrigin"):
                    last = r
        if last:
            c = last.get("message", {}).get("content")
            txt = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict))
            row["transcript_last_user"] = {"turnOrigin": last.get("turnOrigin"), "promptSource": last.get("promptSource"),
                                           "same_as_prompt": txt.strip()[:200] == str(d.get("prompt", "")).strip()[:200]}
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
except Exception as ex:  # a probe must never break the session
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"error": repr(ex)}) + "\n")
    except Exception:
        pass
sys.exit(0)
