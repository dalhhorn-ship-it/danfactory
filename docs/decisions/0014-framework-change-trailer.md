# 0014 — Framework paths and the Framework-Change trailer

> Status: accepted · Date: 2026-11-20

## Context
FISH-5 (docs/specs/teach-agents-to-fish.md): shared conventions (auth, error format) belong in code only humans change, but humans must be able to change it through the gate. The only protected path was `tests/acceptance/**`, whose trailer `Acceptance-Change: <slug>` ties to an approved PRD and the test manifest.

## Options
1. Put framework folders in `gate.protected`. Then only `Acceptance-Change` passes them, which means a PRD slug the manifest knows: wrong meaning, and it would let test-writer's trailer unlock framework code.
2. A new list `gate.framework` and a second trailer `Framework-Change: <reason>`, each valid only for its own list.
3. No gate rule, guidance only. Agents could silently bend conventions.

## Decision
Option 2 (user decision, 2026-11-20). `gate.framework` is a list of globs (default empty, same rules as `protected`). A commit in range touching one needs a non-empty `Framework-Change` in its last trailer block, else `protected-path` fails with a detail naming the list. The two trailers never satisfy each other's paths. The fixer runner reverts framework paths like protected ones and never writes the trailer. Code: `framework_hit` and `framework_bad` in `scripts/gate_checks.py`, called by `c_protected`.

## Consequences
Trailers stay self-asserted (TD-012): the gate makes a framework change visible and deliberate, a human can still write one. Agents are told to stop and ask the user instead. Projects opt in by listing their framework folder.
