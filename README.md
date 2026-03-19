# token-reduce-skill

Low-token repo discovery skill for Claude Code and Codex.

This repo contains the extracted runtime package for `token-reduce`: a small set of search helpers and guardrail hooks that push agents toward low-context discovery instead of broad recursive scans.

## What it does

- starts ambiguous repo discovery with a path-first helper
- uses QMD BM25 when available
- falls back to scoped `rg` when QMD is missing or unhelpful
- blocks broad Bash scans like `find .`, `ls -R`, `grep -R`
- blocks broad `Glob` patterns
- provides a one-snippet follow-up path when file paths alone are not enough

Core runtime files:

- `scripts/token-reduce-search.sh`
- `scripts/token-reduce-paths.sh`
- `scripts/token-reduce-snippet.sh`
- `scripts/advise-token-reduction.py`
- `scripts/enforce-glob-scope.py`
- `scripts/remind-token-reduce.py`

## Why it reduces token usage

The reduction comes from three concrete changes in behavior:

1. Replace broad repo inventory with path-only retrieval first.
2. Retrieve one ranked snippet only when needed.
3. Deny broad Bash and Glob exploration before it bloats context.

In the larger source repo where this skill was developed and measured, the main benchmark deltas were:

- concise responses: about `89%` fewer tokens
- QMD BM25 search vs naive multi-file reads: about `99%` fewer tokens
- targeted reads vs full reads: about `33%` fewer tokens

Those numbers came from the original development repo, not this tiny extracted repo. The extracted repo is mainly for installation and reuse; the mechanism is the same runtime that produced those savings there.

## Install

### Codex

Clone into your Codex skills directory:

```bash
git clone https://github.com/chimera-defi/token-reduce-skill.git "$CODEX_HOME/skills/token-reduce"
```

### Claude

Clone into your workspace and point your workspace instructions/hooks at the runtime files:

```bash
git clone https://github.com/chimera-defi/token-reduce-skill.git tools/token-reduce-skill
```

Typical entrypoints:

- `./tools/token-reduce-skill/scripts/token-reduce-paths.sh`
- `./tools/token-reduce-skill/scripts/token-reduce-snippet.sh`
- `./tools/token-reduce-skill/scripts/advise-token-reduction.py`
- `./tools/token-reduce-skill/scripts/enforce-glob-scope.py`
- `./tools/token-reduce-skill/scripts/remind-token-reduce.py`

## Validate

```bash
python3 /root/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
./scripts/token-reduce-paths.sh "hook broad exploratory bash scans"
./scripts/token-reduce-snippet.sh "token reduction"
```

## Files

- `SKILL.md`: canonical skill instructions
- `agents/openai.yaml`: UI metadata
- `references/token-reduction-guide.md`: benchmark summary and integration notes
- `scripts/`: runtime helpers and hooks
