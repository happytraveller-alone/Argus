#!/usr/bin/env sh
set -eu

if [ "${1:-}" = "serve" ] || { [ "${1:-}" = "agentflow" ] && [ "${2:-}" = "serve" ]; }; then
  echo "Argus AgentFlow runner refuses web-server mode in P1" >&2
  exit 64
fi

case " ${*:-} " in
  *" ssh "*|*" ec2 "*|*" ecs "*)
    echo "Argus AgentFlow runner allows only local/container execution targets in P1" >&2
    exit 64
    ;;
esac

mkdir -p "${AGENTFLOW_RUNS_DIR:-/work/agentflow-runs}" "${ARGUS_AGENTFLOW_OUTPUT_DIR:-/work/outputs}" "${HOME:-/tmp/argus-agentflow-home}"
exec "$@"
