# PRD: truncate

> Status: approved · 2026-11-12 · by user in chat

## Problem
Titles from textkit users overflow fixed-width UI fields. They need a safe way to shorten text.

## Scope
A new public function `textkit.truncate(text, width, suffix="...")` that shortens `text` to fit `width` characters.

## Acceptance criteria
1. Given text whose length is at most `width`, when truncated, then it is returned unchanged (no suffix added).
2. Given text longer than `width`, when truncated, then the result ends with `suffix` and its total length, suffix included, is at most `width`.
3. Given text longer than `width` that has a space within the kept part, when truncated, then the cut happens at the last word boundary that fits, so no word is split.
4. Given text longer than `width` with no space in the kept part (one long word), when truncated, then the word is cut hard so the result is exactly `width` characters long.
5. Given a cut that leaves trailing spaces or the punctuation `,;:.` before the suffix, when truncated, then those characters are removed before the suffix is added.
6. Given `width` smaller than `len(suffix)`, when truncated, then `ValueError` is raised.
7. Given a custom suffix (including the empty string), when truncated, then that suffix is used instead of "...".
