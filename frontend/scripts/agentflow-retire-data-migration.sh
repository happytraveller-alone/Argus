#!/bin/bash
set -e
echo "=== Agentflow Retirement Data Migration ==="

echo "Step 1: Remove agent_tasks key from rust-task-state.json"
docker exec argus-backend-1 sh -c '
  F=/app/uploads/zip_files/rust-task-state.json
  if [ -f "$F" ]; then
    # Create a new JSON by removing the agent_tasks section
    # This uses sed to match and remove the entire agent_tasks object
    sed -i "/\"agent_tasks\":/,/^  },$/d" "$F"
    # Clean up any trailing commas before closing braces
    sed -i "s/,\([[:space:]]*\)}/\1}/g" "$F"
    echo "  ✓ agent_tasks key removed"
  else
    echo "  ℹ file absent; nothing to do"
  fi
'

echo "Step 2: Drop project_management_metrics.agent_tasks column"
docker exec argus-db-1 psql -U postgres -d Argus -c "
  ALTER TABLE project_management_metrics DROP COLUMN IF EXISTS agent_tasks;
" && echo "  ✓ Column dropped"

echo "Step 3: Remove agentflow output directories"
docker exec argus-backend-1 sh -c 'rm -rf /app/uploads/zip_files/agentflow' && echo "  ✓ Directories removed"

echo "=== Migration Complete ==="
