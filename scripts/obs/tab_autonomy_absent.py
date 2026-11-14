"""Autonomy tab when the autonomy pack is not installed (ADR 0011): a one-line card with the command to add it.
Stands in for scripts/obs/tab_autonomy.py (a pack file); dashboard.py picks it when that file is absent."""
import html

HINT = "Autonomy pack not installed: python3 scripts/pack.py add autonomy"


def collect(root, base):
    return {"pack": False}


def line(d):
    return HINT


def render(d):
    return '<div class="stack"><div class="card"><h2>Autonomy</h2><p class="muted">%s</p></div></div>' % html.escape(HINT)
