#!/usr/bin/env sh
set -eu

exec python /usr/local/bin/argus-agentflow-runner-adapter "$@"
