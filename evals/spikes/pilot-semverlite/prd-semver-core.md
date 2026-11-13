# PRD: semver core (parse, compare, bump)

> Status: approved · 2026-11-13 · by user in chat ("build ... pilot 2"; pilot project, spec from semver.org 2.0.0) · Owner: product-manager · Backlog: M1 → SV-1

## Problem
Release tooling needs to read, order and bump version strings exactly as Semantic Versioning 2.0.0 (semver.org) defines them. Ad-hoc string comparison gets "1.10.0" vs "1.9.0" and pre-releases wrong.

## Goal and success measure
A small, dependency-free Python package `semverlite` that follows the spec. Success: every acceptance criterion has an admitted test, all pass, and the code was written by the fixer runner without a human editing it.

## Scope
`semverlite.parse(text) -> Version`, `Version` comparison operators and `str()`, `semverlite.bump(version, part) -> Version`.

## Non-goals
Version ranges, npm/pep440 syntax, a CLI.

## Acceptance criteria
1. Given "1.2.3", when parsed, then major 1, minor 2, patch 3, with an empty prerelease and build.
2. Given "1.0.0-alpha.1+exp.sha.5114f85", when parsed, then prerelease is ("alpha", "1") and build is ("exp", "sha", "5114f85").
3. Given a numeric identifier with a leading zero in the core or prerelease ("01.2.3", "1.2.3-01"), when parsed, then ValueError is raised; "1.2.3-0a" is valid.
4. Given "", "1.2", "1.2.3.4", "v1.2.3", "1.2.3-", "1.2.3+", "1.2.3-a..b" or "-1.2.3", when parsed, then ValueError is raised.
5. Given two versions, when compared, then major, minor and patch are compared numerically in that order ("1.10.0" > "1.9.0", "2.0.0" > "1.99.99").
6. Given a version with a prerelease and the same version without, when compared, then the prerelease is lower ("1.0.0-alpha" < "1.0.0").
7. Given the spec's example chain, when compared, then 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0.
8. Given two versions that differ only in build metadata, when compared, then they are equal in precedence ("1.0.0+a" == "1.0.0+b" under ordering).
9. Given any valid version string, when parsed and turned back with str(), then the original string is returned.
10. Given bump with part "major", "minor" or "patch", when applied, then that part increases by one, lower parts reset to 0, and prerelease and build are dropped; "1.2.3-rc.1" bumped "patch" gives "1.2.4". Any other part raises ValueError.

## Risks and assumptions
Criterion 8 conflicts with Python's `==` if equality also compares build; equality here means ordering-equal (neither < nor >). The test-writer must ask, not guess, if it reads it otherwise.

## Effort and sequencing
S. One milestone.
