# Claude Review Handoff

Use this prompt in Claude for an independent verification pass.

```text
Please perform an independent review of token-reduce after a README consolidation and tier/dependency policy update.

Goals:
1) Verify README is consistent, non-contradictory, and reflects current implementation.
2) Verify no regression in token savings / quality / failure overhead.
3) Verify Claude + Codex setup paths still work.
4) Report any mismatches between docs and code with exact file paths.

Run exactly:
set -euo pipefail
cd /absolute/path/to/token-reduce-skill

./scripts/token-reduce-manage.sh test-adaptive
./scripts/token-reduce-manage.sh release-gate
./scripts/token-reduce-manage.sh validate
./scripts/token-reduce-manage.sh doctor

Then inspect:
- README.md
- llms.txt
- scripts/setup.sh
- scripts/activate-token-reduce-stack.sh
- scripts/token-reduce-manage.sh
- scripts/token-reduce-dependency-health.py
- scripts/token-reduce-orchestrate.sh
- references/tier-value-profile.md
- references/feature-matrix.md

Report back:
1) pass/fail status for each command
2) release-gate metrics and whether net gain is real
3) any doc drift or outdated claims
4) any host compatibility concerns (Claude/Codex)
5) prioritized fixes (if any)
```
