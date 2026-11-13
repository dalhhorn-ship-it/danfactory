"""semverlite: Semantic Versioning 2.0.0 (built by the fixer runner)."""
import re

_NUM = r"(0|[1-9][0-9]*)"
_PRE = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_BUILD = r"[0-9A-Za-z-]+"
_RE = re.compile(
    rf"\A{_NUM}\.{_NUM}\.{_NUM}"
    rf"(?:-({_PRE}(?:\.{_PRE})*))?"
    rf"(?:\+({_BUILD}(?:\.{_BUILD})*))?\Z"
)


class Version:
    def __init__(self, major, minor, patch, prerelease=(), build=()):
        self.major, self.minor, self.patch = major, minor, patch
        self.prerelease = tuple(prerelease)
        self.build = tuple(build)

    def _key(self):
        pre = tuple((0, int(i), "") if i.isdigit() else (1, 0, i)
                    for i in self.prerelease)
        # a version without prerelease ranks above any with one
        return (self.major, self.minor, self.patch,
                (1,) if not pre else (0, pre))

    def __eq__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self):
        return hash(self._key())

    def __lt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() < other._key()

    def __le__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() <= other._key()

    def __gt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() > other._key()

    def __ge__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() >= other._key()

    def __str__(self):
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            s += "-" + ".".join(self.prerelease)
        if self.build:
            s += "+" + ".".join(self.build)
        return s

    def __repr__(self):
        return f"Version({str(self)!r})"


def parse(text):
    m = _RE.match(text) if isinstance(text, str) else None
    if not m:
        raise ValueError(f"invalid semantic version: {text!r}")
    major, minor, patch, pre, build = m.groups()
    return Version(int(major), int(minor), int(patch),
                   pre.split(".") if pre else (),
                   build.split(".") if build else ())


def bump(version, part):
    if part == "major":
        return Version(version.major + 1, 0, 0)
    if part == "minor":
        return Version(version.major, version.minor + 1, 0)
    if part == "patch":
        return Version(version.major, version.minor, version.patch + 1)
    raise ValueError(f"invalid part: {part!r}")
