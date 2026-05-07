#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'USAGE'
usage: ./scripts/kimi-delegate-manage.sh <command>

commands:
  setup             Install local skill links and command wrapper
  workspace-install Install skill + doc block across workspace repos
  workspace-audit   Audit workspace adoption
  telemetry         Summarize recent telemetry
USAGE
}

cmd="${1:-}"
if [[ $# -gt 0 ]]; then
  shift
fi

case "$cmd" in
  setup)
    exec "$SCRIPT_DIR/setup.sh" "$@"
    ;;
  workspace-install)
    exec "$SCRIPT_DIR/install_workspace_skill.py" "$@"
    ;;
  workspace-audit)
    exec "$SCRIPT_DIR/audit_workspace_skills.py" "$@"
    ;;
  telemetry)
    exec "$SCRIPT_DIR/kimi_delegate_telemetry.py" summary "$@"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
