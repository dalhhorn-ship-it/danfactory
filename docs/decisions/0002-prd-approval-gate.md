# 0002 — PRD approval gate before any build

> Status: accepted · Date: 2026-11-06

## Context
Feature work was sometimes started straight from a chat request (e.g. the dashboard Roadmap tab), without a written problem, scope or acceptance criteria the user had signed off. That risks building the wrong thing and leaves verifiers (`jenny`, `task-completion-validator`) nothing agreed to check against.

## Options
1. Keep specs optional for small items — fast, but scope drifts silently.
2. Require a PRD from `product-manager` for every feature/behaviour change, approved by the user in chat — one extra round-trip, but scope is explicit and reviewable.

## Decision
Option 2, requested by the user. Policy in docs/policies/prd-approval.md; template in docs/specs/_TEMPLATE.md; gate stated in CLAUDE.md and enforced in the `developer` agent. Narrow exemptions: bug fixes restoring specified behaviour, behaviour-free chores, explicit spikes, explicit per-item waivers.

## Consequences
Every feature costs one review turn before code. Approved PRDs become the acceptance source for verifiers. Measure at retro: PRD revisions per feature and rework after approval.
