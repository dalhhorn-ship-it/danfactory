# 0001 — Start from the danfactory template

> Status: accepted · Date: 2026-11-06

## Context
Projects start with Claude Code and vary widely (apps, spreadsheets, docs, scripts). One process for all wastes effort on small things and under-protects big ones.

## Decision
Use the danfactory flow: brainstorm → decision tree → operating model → build, with token-economy hooks, generated docs index, delivery metrics, on-demand security audit, and git-based Cloudflare deploys.

## Consequences
Each project has GOAL.md and OPERATING-MODEL.md before building. Learnings flow back to the template via `[upstream]` entries.
