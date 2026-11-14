# Policy: template maintenance

> How a checkout is recognised as the template itself, and how learnings flow back from projects into it.

## Template mode

A checkout whose git `origin` is `template.source_repo` in factory.json (`dalhhorn-ship-it/danfactory`) is the template itself. There the session-start hook says "TEMPLATE repo" instead of suggesting brainstorm, the dashboard shows "Template maintenance" (open tech debt, then open Unplanned backlog items) instead of phase and progress, and `python3 scripts/metrics.py test` runs `.factory/tests` (`commands.test` stays empty so projects are unaffected). Any other origin, no remote or no git means project mode. Detection reads local git config only (helper `template_mode()` in .claude/hooks/_common.py). If you rename or move the template repo, update `template.source_repo`. A plain `git clone` of the template keeps its origin and so counts as the template until you change the remote.

## Feeding learnings back

`retro` tags learnings that apply to every project with `[upstream]`. From the project, run `python3 scripts/upstream_learnings.py --template ../danfactory`: it appends unsent entries to the template's LEARNINGS.md, marks them `[upstreamed]`, and lists which shared docs (tree, routing, paths) differ, for you to port. Then open a PR in the template and bump the tree version. New projects then start from the improved tree.
