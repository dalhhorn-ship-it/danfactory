"""textkit core helpers."""
import re


def slugify(text):
    """Lower-case `text` and join its words with single dashes."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
