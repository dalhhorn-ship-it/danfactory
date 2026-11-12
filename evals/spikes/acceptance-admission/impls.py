"""Spike yardsticks: two independent correct readings of docs/specs/truncate.md and seeded bugs (mutants) of A."""
IMPL_A = '''
def truncate(text, width, suffix="..."):
    if width < len(suffix):
        raise ValueError("width smaller than suffix")
    if len(text) <= width:
        return text
    room = width - len(suffix)
    kept = text[:room]
    if " " in kept and text[room] != " ":
        kept = kept[:kept.rfind(" ")]
    kept = kept.rstrip(" ,;:.")
    return kept + suffix
'''
# B: different structure; treats any whitespace as a boundary and does not strip after a hard cut
# (both are details the PRD does not specify).
IMPL_B = '''
import re
def truncate(text, width, suffix="..."):
    if width < len(suffix):
        raise ValueError(width)
    if len(text) <= width:
        return text
    room = width - len(suffix)
    head, nxt = text[:room], text[room:room + 1]
    if nxt.isspace() or nxt == "":
        cut = head
    else:
        m = list(re.finditer(r"\\s", head))
        if not m:
            return head + suffix          # hard cut: exactly width
        cut = head[:m[-1].start()]
    return cut.rstrip(" ,;:.") + suffix
'''
MUTANTS = {  # id: (criterion, old, new) applied to IMPL_A
    "M1-equal-len-truncated": (1, "len(text) <= width", "len(text) < width"),
    "M2-suffix-not-counted": (2, "room = width - len(suffix)", "room = width"),
    "M3-no-word-boundary": (3, 'if " " in kept and text[room] != " ":', "if False:"),
    "M4-no-hard-cut-guard": (4, 'if " " in kept and text[room] != " ":', 'if text[room] != " ":'),
    "M5-no-strip": (5, 'kept = kept.rstrip(" ,;:.")', "pass"),
    "M6-strip-spaces-only": (5, 'kept.rstrip(" ,;:.")', 'kept.rstrip(" ")'),
    "M7-no-valueerror": (6, 'raise ValueError("width smaller than suffix")', "pass"),
    "M8-valueerror-off-by-one": (6, "width < len(suffix)", "width <= len(suffix)"),
    "M9-suffix-ignored": (7, "return kept + suffix", 'return kept + "..."'),
    "M10-suffix-on-short-text": (1, "        return text\n", "        return text + suffix if text else text\n"),
    "M11-drops-complete-last-word": (3, 'if " " in kept and text[room] != " ":', 'if " " in kept:'),
    "M12-empty-suffix-defaulted": (7, "    if width < len(suffix):", '    suffix = suffix or "..."\n    if width < len(suffix):'),
}
