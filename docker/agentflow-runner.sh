#!/usr/bin/env sh
set -eu

pipeline_path="${1:-/app/backend/agentflow/pipelines/intelligent_audit.py}"
shift || true

agentflow validate "$pipeline_path" >/work/outputs/pipeline.validate.json
agentflow run "$pipeline_path" --output json "$@" | tee /work/outputs/agentflow.run.json
