# Claude Guidance

If the path is unknown, start with `./scripts/token-reduce-paths.sh topic words`, then use scoped `rg` and targeted reads on the candidates it returns.

Before merging a change, run `bash tests/test_e2e.sh`. Deploying to the live host is a manual step; see `README.md`.
