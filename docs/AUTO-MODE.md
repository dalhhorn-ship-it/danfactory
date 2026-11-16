# Auto mode, and how the dev modes compare

> Plain-words explainer for the landing page and for new users. Rules live in docs/policies/mission.md (mission), docs/policies/runner.md (fixer runner) and docs/policies/prd-approval.md (supervised). Status: mission autopilot is new and early (see Honest limits).

## Auto mode in one minute
You describe what you want. The agent answers with one short **mission brief**: the request, the plan of attack, what is in and out of scope, and the limits. You reply "go". From then on it builds until the work is done or a limit is reached, and you read a report in the morning.

1. **Brief.** Request, plan, scope in and out, at most 5 features, limits. Then it stops and waits.
2. **Your go.** One clear yes. Your words are saved with the mission.
3. **PRDs.** The product-manager agent writes one per feature. Inside the scope they count as approved by the mission.
4. **Scout.** For a feature that is new to the project, a scout compares 3 to 5 open-source projects first and recommends: use a library, borrow the approach, or build.
5. **Design.** The architect splits the work into slices and says which files each slice owns.
6. **Tests first.** Acceptance tests are written and admitted before any code (at standard rigor, L2, or higher).
7. **Parallel build.** Up to 3 developers work at once, each on its own copy. Merges go in one at a time, each through the merge gate.
8. **Morning report.** What was built, the assumptions made, what was set aside and why, cost, time and gate results.

## Guardrails
- **Limits:** 15 USD, 10 hours, 40 restarts, 5 features by default. The agent cannot raise them.
- **Never to main:** nothing is pushed or merged to main or staging during the mission's time window. You promote the mission branch yourself.
- **Controls locked:** mission work cannot edit the factory's own hooks, settings, gate scripts or limits.
- **No questions at night:** unclear points become written assumptions; blocked or out-of-scope items are set aside, and the rest continues.
- **You can stop it** at any time: `python3 scripts/mission.py stop <name>`.

## Compare the dev modes

| | Supervised (default) | Mission autopilot | Fixer runner |
|---|---|---|---|
| You approve | Every PRD | One brief ("go") | Each PRD first; you start every run |
| Who writes PRDs | PM agent | PM agent | PM agent (before the run) |
| Asks questions mid-build | Yes | No: assumes or sets aside | No: sets aside after 3 tries |
| Open-source scout | Yes, for unfamiliar features | Yes, without asking | – |
| Parallel agents | Developers, up to 3 (max 4) | Developers, up to 3 (max 4) | Fixers, 1 by default (max 4) |
| Acceptance tests before code | Yes, at L2 or higher | Yes, at L2 or higher (enforced) | Works from failing tests |
| Merge gate | Before merge, and in CI | On every merge | On every fix |
| Sandbox | – | – (use a throwaway cloud session) | Yes, no network |
| Budget limits | – | 15 USD, 10 h, 40 restarts, 5 features | 2 USD per run, 5 USD per day |
| Work lands on | Your branch | `mission/<name>` | `staging` |
| Agent pushes to main | Only when you ask | Never | Never |
| Morning report | – | Yes | Status and dashboard tab |
| Best for | Features you want to shape | Several features while you are away | Failing tests, unattended |
| Setup | None | None | Autonomy pack, switched on, sandbox tools |

## Honest limits
- The budget limit is an estimate from a price table; the restart limit is the hard stop (TD-024).
- Mission autopilot has not yet run a real overnight cloud session (TD-025).
- Mission developers are not sandboxed. Run missions in a throwaway cloud session with limited credentials.
- The guards read tool calls and commands; a write made from inside a script is not seen. The merge gate and your review of the mission branch are the backstop.
