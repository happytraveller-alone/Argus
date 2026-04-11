#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
OUTPUT_DIR="$ROOT_DIR/compliance/sbom"
mkdir -p "$OUTPUT_DIR"

echo "[SBOM] generating into $OUTPUT_DIR"

if command -v cyclonedx-py >/dev/null 2>&1; then
  if cyclonedx-py environment \
    --spec-version 1.5 \
    --output-file "$OUTPUT_DIR/backend.cdx.json" \
    --output-format JSON; then
    echo "[SBOM] CycloneDX generated"
  else
    echo "[SBOM] cyclonedx-py command failed, keeping template backend.cdx.json"
  fi
else
  echo "[SBOM] cyclonedx-py not found, keeping template backend.cdx.json"
fi

if command -v python3 >/dev/null 2>&1; then
  ROOT_DIR_ENV="$ROOT_DIR" python3 - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["ROOT_DIR_ENV"])
out = root / "compliance" / "sbom" / "backend.spdx.json"
if out.exists():
    data = json.loads(out.read_text(encoding="utf-8"))
else:
    data = {
        "spdxVersion": "SPDX-2.3",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "AuditTool-backend-sbom",
        "dataLicense": "CC0-1.0",
        "documentNamespace": "https://audittool.local/sbom/backend/spdx",
        "creationInfo": {"created": "1970-01-01T00:00:00Z", "creators": ["Tool: sbom-script"]},
        "packages": [],
    }

# lightweight stamp update only; full SPDX generation can be replaced by dedicated tool.
from datetime import datetime, timezone
created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
data.setdefault("creationInfo", {})["created"] = created
out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print("[SBOM] SPDX file stamped")
PY
fi

echo "[SBOM] done"
