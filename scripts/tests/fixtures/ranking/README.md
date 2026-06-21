# Ranking fixtures

Synthetic corpora for `rank_paths` unit and integration tests. Each test
constructs a temporary git repo from the fixture so commit recency, file
content, and path layout can be controlled deterministically.

Dimensions exercised:

- **A1 git-recency**: same content, different commit ages.
- **A2 symbol-match**: definition site vs incidental mention.
- **A3 path-relevance**: tests/fixtures/vendor/dist demoted unless cued.
- **A4 query expansion**: stopword pruning, bigram retention.
- **A5 click-through**: prior cache built from `file_read_after_helper` events.
