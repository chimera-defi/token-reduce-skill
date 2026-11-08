---
name: token-reduce
license: MIT
description: "Find where code lives in an unfamiliar repo with one ranked path list before reading files."
triggers:
  - token-reduce
  - find where code lives
---

# token-reduce

When you don't know which file holds something, ask for a short ranked list first, then read only those files.

```bash
token-reduce-paths session send timers     # up to 20 paths, best first
token-reduce-snippet send_message          # top paths + up to 40 file:line hits
```

- Run it from inside the repo. A file whose path matches more of your words ranks first; files whose content matches fill the remaining slots.
- From `$HOME` or `~/workspace` it does a bounded, private-safe search that skips secrets, agent memory and holdouts. `cd` into a repo for a real answer.
- `No results found.` means nothing matched. Try different words or a symbol name.
- In Claude Code the built-in Grep and Glob tools are fine for a known name. This helper is for vague, multi-word lookups.
- Repo-relative form: `./scripts/token-reduce-paths.sh <words>`.
