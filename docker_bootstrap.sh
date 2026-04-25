#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${ROOT_DIR}/docker_bootstrap.log"
DRY_RUN=0

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

timestamp() {
  date '+%Y-%m-%d %H:%M:%S'
}

log() {
  printf '[%s] %s\n' "$(timestamp)" "$*"
}

run() {
  log "+ $*"
  "$@"
}

ensure_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log "ERROR: required command not found: $cmd"
    exit 1
  fi
}

mkdir -p "${ROOT_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

log "docker_bootstrap start"

ensure_command docker
ensure_command cargo
ensure_command python3

run docker info >/dev/null
run docker compose version >/dev/null
run cargo --version
run python3 --version

SHARED_CONFIG="${ROOT_DIR}/backend/agents/shared/config.json"
if [[ ! -f "${SHARED_CONFIG}" ]]; then
  log "ERROR: missing shared config: ${SHARED_CONFIG}"
  exit 1
fi

log "projecting shared config into Hermes role directories"
ROOT_DIR_ENV="${ROOT_DIR}" python3 - <<'PY'
import json
import os
import re
from pathlib import Path

root = Path(os.environ["ROOT_DIR_ENV"])
shared = root / "backend" / "agents" / "shared" / "config.json"

with shared.open("r", encoding="utf-8") as fh:
    config = json.load(fh)

structured_config = config.get("config") if isinstance(config.get("config"), dict) else None
structured_env = config.get("env") if isinstance(config.get("env"), dict) else None

if structured_config is not None:
    config_payload = structured_config.copy()
else:
    model = str(config.get("HERMES_MODEL") or "").strip()
    provider = str(config.get("HERMES_PROVIDER") or "").strip()
    base_url = str(config.get("base_url") or "").strip()
    config_payload = {}
    model_payload = {}
    if model:
        model_payload["default"] = model
    if provider:
        model_payload["provider"] = provider
    if base_url:
        model_payload["base_url"] = base_url
    if model_payload:
        config_payload["model"] = model_payload

env_payload = structured_env.copy() if structured_env is not None else {}
if "HERMES_MODEL" not in env_payload:
    model_default = str((config_payload.get("model") or {}).get("default") or "").strip()
    if model_default:
        env_payload["HERMES_MODEL"] = model_default
if "HERMES_PROVIDER" not in env_payload:
    model_provider = str((config_payload.get("model") or {}).get("provider") or "").strip()
    if model_provider:
        env_payload["HERMES_PROVIDER"] = model_provider
for key in (
    "HERMES_MODEL",
    "HERMES_PROVIDER",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_TOKEN",
):
    if key not in env_payload and key in config:
        env_payload[key] = config.get(key, "")

required_missing = []
model_cfg = config_payload.get("model") if isinstance(config_payload.get("model"), dict) else {}
if not str(model_cfg.get("default") or "").strip():
    required_missing.append("config.model.default")
if not str(model_cfg.get("provider") or "").strip():
    required_missing.append("config.model.provider")
if not str(model_cfg.get("base_url") or "").strip():
    required_missing.append("config.model.base_url")

provider = str(model_cfg.get("provider") or "").strip().lower()
if provider == "anthropic":
    anth_key = str(env_payload.get("ANTHROPIC_API_KEY") or env_payload.get("ANTHROPIC_TOKEN") or "").strip()
    if not anth_key:
        required_missing.append("env.ANTHROPIC_API_KEY or env.ANTHROPIC_TOKEN")
elif provider == "openai":
    if not str(env_payload.get("OPENAI_API_KEY") or "").strip():
        required_missing.append("env.OPENAI_API_KEY")
elif provider == "custom":
    if not str(env_payload.get("OPENAI_API_KEY") or "").strip():
        required_missing.append("env.OPENAI_API_KEY")
elif provider == "openrouter":
    if not str(env_payload.get("OPENROUTER_API_KEY") or "").strip():
        required_missing.append("env.OPENROUTER_API_KEY")

if required_missing:
    print("ERROR: backend/agents/shared/config.json is missing required fields:")
    for item in required_missing:
        print(f"  - {item}")
    print("")
    print("Please copy backend/agents/shared/config.example.json to")
    print("backend/agents/shared/config.json and fill in your deployment values.")
    raise SystemExit(1)

if provider == "anthropic":
    base_url = str(model_cfg.get("base_url") or "").strip()
    if base_url.endswith("/v1"):
        model_cfg["base_url"] = base_url[:-3]

roles = ("recon", "analysis", "verification", "report")


def update_env_file(path: Path) -> None:
    existing = []
    if path.exists():
        existing = path.read_text(encoding="utf-8").splitlines()

    updates = {}
    for key, raw_value in env_payload.items():
        value = str(raw_value).strip()
        if value:
            updates[key] = value

    seen = set()
    new_lines = []
    for line in existing:
        stripped = line.strip()
        replaced = False
        for key, value in updates.items():
            if stripped.startswith(f"{key}="):
                new_lines.append(f"{key}={value}")
                seen.add(key)
                replaced = True
                break
        if not replaced:
            new_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={value}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def existing_cwd(path: Path) -> str:
    if not path.exists():
        return "/scan"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^\s*cwd:\s*(\S+)\s*$", text)
    return match.group(1) if match else "/scan"


def write_config_yaml(path: Path) -> None:
    payload = json.loads(json.dumps(config_payload))
    if not isinstance(payload, dict):
        payload = {}
    terminal_cfg = payload.get("terminal")
    if not isinstance(terminal_cfg, dict):
        terminal_cfg = {}
        payload["terminal"] = terminal_cfg
    terminal_cfg.setdefault("cwd", existing_cwd(path))
    lines = json.dumps(payload, indent=2, ensure_ascii=False).splitlines()
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


for role in roles:
    role_root = root / "backend" / "agents" / role
    update_env_file(role_root / "data" / ".env")
    write_config_yaml(role_root / "data" / "config.yaml")
    role_model = str((config_payload.get("model") or {}).get("default") or "").strip()
    role_provider = str((config_payload.get("model") or {}).get("provider") or "").strip()
    role_base_url = str((config_payload.get("model") or {}).get("base_url") or "").strip()
    print(
        f"[projected] role={role} model={role_model or '-'} provider={role_provider or '-'} base_url={role_base_url or '-'}"
    )
PY

if [[ "${DRY_RUN}" == "1" ]]; then
  log "dry-run mode: skipping docker compose up --build"
  exit 0
fi

log "running docker compose up --build"
run docker compose up --build
