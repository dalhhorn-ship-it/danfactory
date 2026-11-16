#!/usr/bin/env python3
"""Stop hook: keep an active mission going until its work is done or a cap is hit (ADR 0012, MISSION-2).

No active mission, or `state.ended` already set: exit 0, no output, no writes. HEAD not on the mission branch: allow the stop
with a systemMessage saying so (no writes).
Otherwise: re-sum this session's spend from the transcript, check the caps (stopped, wall-clock, budget,
continuations, in that order), then the remaining work. A cap or an empty work list ends the mission (state,
report) and allows the stop; anything else blocks the stop with the next item. `stop_hook_active` is ignored on
purpose: the continuation counter is what ends the loop. Any internal error allows the stop (the safe direction).
Stdlib only, Python 3.8+. The slice-A module `_mission` and the slice-C `mission_report` are imported lazily.
"""
import datetime
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ROOT, read_event  # noqa: E402

# USD per million input tokens; `weighted_tokens` is already in input-token equivalents. Unknown models: highest.
PRICE = {"opus": 5.0, "sonnet": 3.0, "haiku": 1.0}


def price(model):
    name = str(model).lower()
    for key, usd in PRICE.items():
        if key in name:
            return usd
    return max(PRICE.values())


def session_usd(transcript):
    """Estimated USD for a transcript plus its subagents; None when it can't be read."""
    import record_tokens as rt
    total = 0.0
    for path in [transcript] + rt.subagent_transcripts(transcript):
        _, by_model, _ = rt.summarize(path)
        total += sum(rt.weighted(use) * price(model) / 1e6 for model, use in by_model.items())
    return total


def head_branch(root):
    p = subprocess.run(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"],
                       capture_output=True, text=True, timeout=10, check=False)
    return p.stdout.strip() if p.returncode == 0 else ""


def hours_used(m):
    return (datetime.datetime.now(datetime.timezone.utc) - m["started_at"]).total_seconds() / 3600


def finish(mm, root, m, state, reason):
    """End the mission: state first (so a failing report can't re-open it), then the report."""
    state["ended"] = {"reason": reason, "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    mm.save_state(root, state)
    done = reason == "done"
    note = "Mission %s %s." % (m["slug"], "is done" if done else "stopped: %s cap" % reason
                               if reason not in ("stopped",) else "was stopped by the user")
    try:
        sys.path.insert(0, os.path.join(root, "scripts"))
        import mission_report
        path = mission_report.write(root, m["slug"], reason)
        note += " Report: %s." % path
    except Exception:  # noqa: BLE001 - slice C missing or failing: still end the mission cleanly
        try:
            mm.set_status(root, m["slug"], "done" if done else "stopped")
        except Exception:  # noqa: BLE001
            pass
        note += " Run `python3 scripts/mission.py report %s` for the morning report." % m["slug"]
    print(json.dumps({"systemMessage": note}))


def run():
    try:
        import _mission as mm
    except Exception:  # noqa: BLE001 - slice A not there: nothing to do
        return
    ev = read_event()
    root = ROOT
    m = mm.active(root)
    if not m:
        return
    head = head_branch(root)
    if head != m.get("branch"):
        print(json.dumps({"systemMessage": "mission %s is active on %s, you are on %s: not continuing"
                          % (m["slug"], m.get("branch") or "?", head or "unknown")}))
        return
    bad = mm.validate(root, m)
    if bad:  # caps and go come from the first commit; an invalid mission is treated as stopped
        print(json.dumps({"systemMessage": "Mission %s is not valid (%s): treated as stopped, not continuing."
                          % (m["slug"] or "?", bad)}))
        return
    state = mm.load_state(root, m["slug"])
    if state.get("ended"):
        return
    tp, sid = ev.get("transcript_path"), ev.get("session_id") or "unknown"
    if tp:
        try:
            state.setdefault("sessions", {})[sid] = round(session_usd(tp), 4)
        except Exception:  # noqa: BLE001 - spend unknown: the continuation cap still binds
            pass
    reason = mm.cap_hit(m, state)
    if reason:
        return finish(mm, root, m, state, reason)
    item = mm.next_item(root, m)
    if item is None:
        return finish(mm, root, m, state, "done")
    state["continuations"] = int(state.get("continuations") or 0) + 1
    mm.save_state(root, state)
    caps = m["caps"]
    print(json.dumps({"decision": "block", "reason": (
        "Mission %s (%d/%d, $%.2f/%g, %.1f/%gh). Next: %s %s. Don't ask the user: write assumptions in the PRD "
        "and the Decision log, park blocked items [!] with a note, commit after each item." % (
            m["slug"], state["continuations"], caps["continuations"], sum(state["sessions"].values()),
            caps["usd"], hours_used(m), caps["hours"], item["id"], item.get("title", "")))}))


def main():
    try:
        run()
    except Exception:  # noqa: BLE001 - stopping is the safe direction
        pass


if __name__ == "__main__":
    main()
