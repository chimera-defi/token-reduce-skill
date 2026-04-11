#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || { cd "$SCRIPT_DIR/.." && pwd; })"
OUT_DIR="$ROOT/artifacts/token-reduction"
DATE_STAMP="$(date +%Y-%m-%d)"
SCOPE="repo"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scope)
      SCOPE="${2:-repo}"
      shift 2
      ;;
    --output)
      OUTPUT="${2:?missing output path}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$OUT_DIR"
OUTPUT="${OUTPUT:-$OUT_DIR/adoption-${SCOPE}-${DATE_STAMP}.json}"
SUMMARY_MD="${OUTPUT%.json}.md"
REVIEW_JSON="${OUTPUT%.json}-review.json"
REVIEW_MD="${OUTPUT%.json}-review.md"

uv run "$SCRIPT_DIR/measure_token_reduction.py" \
  --scope "$SCOPE" \
  --repo-root "$ROOT" \
  --output "$OUTPUT"

uv run python - "$OUTPUT" "$SUMMARY_MD" <<'PY'
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
data = json.loads(src.read_text())
ad = data["adoption"]
comp = data["compliance"]
summary = f"""# Token Reduction Adoption Summary

- Scope: `{data['scope']}`
- Measured at: `{data['measured_at']}`
- Repo: `{data['repo_root']}`
- Session count: `{data['session_count']}`
- Claude sessions: `{data['sources']['claude_sessions']}`
- Codex sessions: `{data['sources']['codex_sessions']}`

## Adoption

- `qmd_search_sessions`: {ad['qmd_search_sessions']}
- `token_reduce_search_sessions`: {ad['token_reduce_search_sessions']}
- `scoped_rg_sessions`: {ad['scoped_rg_sessions']}
- `targeted_read_sessions`: {ad['targeted_read_sessions']}
- `subagent_sessions`: {ad['subagent_sessions']}
- `token_reduce_mentions`: {ad['token_reduce_mentions']}
- `caveman_mentions`: {ad.get('caveman_mentions', 0)}
- `caveman_command_sessions`: {ad.get('caveman_command_sessions', 0)}
- `axi_tool_sessions`: {ad.get('axi_tool_sessions', 0)}
- `gh_axi_sessions`: {ad.get('gh_axi_sessions', 0)}
- `chrome_devtools_axi_sessions`: {ad.get('chrome_devtools_axi_sessions', 0)}
- `structural_helper_sessions`: {ad.get('structural_helper_sessions', 0)}
- `qmd_search_pct`: {ad['qmd_search_pct']}
- `token_reduce_search_pct`: {ad['token_reduce_search_pct']}
- `scoped_rg_pct`: {ad['scoped_rg_pct']}
- `caveman_mention_pct`: {ad.get('caveman_mention_pct', 0.0)}
- `caveman_command_pct`: {ad.get('caveman_command_pct', 0.0)}
- `axi_tool_sessions_pct`: {ad.get('axi_tool_sessions_pct', 0.0)}
- `gh_axi_sessions_pct`: {ad.get('gh_axi_sessions_pct', 0.0)}
- `chrome_devtools_axi_sessions_pct`: {ad.get('chrome_devtools_axi_sessions_pct', 0.0)}
- `structural_helper_sessions_pct`: {ad.get('structural_helper_sessions_pct', 0.0)}

## Compliance

- `discovery_compliance_pct`: {comp['discovery_compliance_pct']}
- `broad_scan_violations`: {comp['broad_scan_violations']}
- `sessions_with_broad_scan_violation`: {comp['sessions_with_broad_scan_violation']}
- `sessions_with_compliant_first_discovery`: {comp['sessions_with_compliant_first_discovery']}
"""
dst.write_text(summary)
print(summary)
PY

uv run "$SCRIPT_DIR/review_token_reduction.py" \
  --scope "$SCOPE" \
  --repo-root "$ROOT" \
  --output-json "$REVIEW_JSON" \
  --output-md "$REVIEW_MD" >/dev/null

echo
echo "Wrote:"
echo "  $OUTPUT"
echo "  $SUMMARY_MD"
echo "  $REVIEW_JSON"
echo "  $REVIEW_MD"
