#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_SRC="$ROOT_DIR/argus-reset-rebuild-start.sh"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

fail() {
  echo "[test] ERROR: $*" >&2
  exit 1
}

assert_contains() {
  local file="$1" pattern="$2"
  grep -Fq -- "$pattern" "$file" || fail "Expected $file to contain: $pattern"
}

assert_not_contains() {
  local file="$1" pattern="$2"
  if grep -Fq -- "$pattern" "$file"; then
    fail "Expected $file not to contain: $pattern"
  fi
}

new_fixture() {
  local name="$1"
  local dir="$TMP_ROOT/$name"
  mkdir -p "$dir/docker/env/backend"
  cp "$SCRIPT_SRC" "$dir/argus-reset-rebuild-start.sh"
  chmod +x "$dir/argus-reset-rebuild-start.sh"
  cat > "$dir/docker-compose.yml" <<'COMPOSE'
services:
  agentflow-runner:
    build:
      context: .
  opengrep-runner:
    build:
      context: .
  backend:
    build:
      context: .
    env_file:
      - path: ./docker/env/backend/.env
        required: false
    ports:
      - "${Argus_BACKEND_PORT:-18000}:8000"
  frontend:
    build:
      context: ./frontend
    ports:
      - "${Argus_FRONTEND_PORT:-13000}:5173"
  db:
    image: postgres:18-alpine
  redis:
    image: redis:8-alpine
  adminer:
    image: adminer:latest
volumes:
  agentflow_runner_work:
    name: ${AGENTFLOW_RUNNER_WORK_VOLUME:-Argus_agentflow_runner_work}
  postgres_data:
  backend_uploads:
  backend_runtime_data:
  scan_workspace:
    name: ${SCAN_WORKSPACE_VOLUME:-Argus_scan_workspace}
  redis_data:
  frontend_node_modules:
  frontend_pnpm_store:
COMPOSE
  printf '%s' "$dir"
}

write_valid_config() {
  local dir="$1"
  cat > "$dir/.argus-intelligent-audit.env" <<'ENV'
SECRET_KEY=local_test_secret_0123456789abcdef
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=11520
LLM_PROVIDER=openai
LLM_API_KEY=SECRET_SENTINEL_SHOULD_NOT_PRINT
LLM_MODEL=gpt-5
LLM_BASE_URL=https://api.openai.com/v1
LLM_TIMEOUT=150
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=4096
AGENT_ENABLED=true
AGENT_MAX_ITERATIONS=5
AGENT_TIMEOUT=1800
ENABLE_PARALLEL_ANALYSIS=true
ENABLE_PARALLEL_VERIFICATION=true
ANALYSIS_MAX_WORKERS=5
VERIFICATION_MAX_WORKERS=3
ENV
}

# Help documents safety controls and compose-correct port variables.
help_dir="$(new_fixture help)"
help_out="$help_dir/help.out"
( cd "$help_dir" && ./argus-reset-rebuild-start.sh --help ) >"$help_out" 2>&1
assert_contains "$help_out" "ARGUS_RESET_VOLUMES=delete"
assert_contains "$help_out" "ARGUS_BUILDX_PRUNE=true"
assert_contains "$help_out" "ARGUS_INTELLIGENT_AUDIT_ENV"
assert_contains "$help_out" "Argus_BACKEND_PORT"
assert_contains "$help_out" "Argus_FRONTEND_PORT"
assert_contains "$help_out" "overwrites docker/env/backend/.env"

# Missing config exits before Docker cleanup and creates a template/example.
missing_dir="$(new_fixture missing)"
missing_out="$missing_dir/missing.out"
set +e
( cd "$missing_dir" && ARGUS_STUB_DOCKER=true ./argus-reset-rebuild-start.sh ) >"$missing_out" 2>&1
missing_rc=$?
set -e
[[ "$missing_rc" -ne 0 ]] || fail "Missing config should fail"
[[ -f "$missing_dir/.argus-intelligent-audit.env.example" ]] || fail "Missing config should create template/example"
assert_not_contains "$missing_out" "docker compose"
assert_not_contains "$missing_out" "docker image rm"
assert_not_contains "$missing_out" "docker buildx prune"

# Placeholder config exits before Docker cleanup.
placeholder_dir="$(new_fixture placeholder)"
cat > "$placeholder_dir/.argus-intelligent-audit.env" <<'ENV'
SECRET_KEY=local_test_secret_0123456789abcdef
LLM_PROVIDER=openai
LLM_API_KEY=sk-your-api-key
LLM_MODEL=gpt-5
LLM_BASE_URL=https://api.openai.com/v1
AGENT_ENABLED=true
AGENT_MAX_ITERATIONS=5
AGENT_TIMEOUT=1800
ENV
placeholder_out="$placeholder_dir/placeholder.out"
set +e
( cd "$placeholder_dir" && ARGUS_STUB_DOCKER=true ./argus-reset-rebuild-start.sh ) >"$placeholder_out" 2>&1
placeholder_rc=$?
set -e
[[ "$placeholder_rc" -ne 0 ]] || fail "Placeholder config should fail"
assert_not_contains "$placeholder_out" "docker compose"
assert_not_contains "$placeholder_out" "docker image rm"

# Missing required key exits before Docker cleanup.
missing_key_dir="$(new_fixture missing-key)"
write_valid_config "$missing_key_dir"
grep -v '^LLM_MODEL=' "$missing_key_dir/.argus-intelligent-audit.env" > "$missing_key_dir/.argus-intelligent-audit.env.tmp"
mv "$missing_key_dir/.argus-intelligent-audit.env.tmp" "$missing_key_dir/.argus-intelligent-audit.env"
missing_key_out="$missing_key_dir/missing-key.out"
set +e
( cd "$missing_key_dir" && ARGUS_STUB_DOCKER=true ./argus-reset-rebuild-start.sh ) >"$missing_key_out" 2>&1
missing_key_rc=$?
set -e
[[ "$missing_key_rc" -ne 0 ]] || fail "Missing required key should fail"
assert_contains "$missing_key_out" "LLM_MODEL"
assert_not_contains "$missing_key_out" "docker compose"
assert_not_contains "$missing_key_out" "docker image rm"

# Valid config fully overwrites backend .env, redacts secrets, preserves volumes, skips buildx prune by default,
# and removes only allowlisted local images.
valid_dir="$(new_fixture valid)"
write_valid_config "$valid_dir"
printf 'STALE_KEY=must_be_removed\n' > "$valid_dir/docker/env/backend/.env"
valid_out="$valid_dir/valid.out"
( cd "$valid_dir" && ARGUS_STUB_DOCKER=true ./argus-reset-rebuild-start.sh ) >"$valid_out" 2>&1
cmp "$valid_dir/.argus-intelligent-audit.env" "$valid_dir/docker/env/backend/.env" >/dev/null || fail "backend .env should be fully overwritten"
assert_not_contains "$valid_dir/docker/env/backend/.env" "STALE_KEY"
assert_not_contains "$valid_out" "SECRET_SENTINEL_SHOULD_NOT_PRINT"
assert_contains "$valid_out" "preserving volumes"
assert_not_contains "$valid_out" "[stub] docker buildx prune -a -f"
assert_contains "$valid_out" "docker image rm argus/agentflow-runner:stub"
assert_contains "$valid_out" "docker image rm Argus/opengrep-runner-local:stub"
assert_contains "$valid_out" "docker image rm argus-backend:stub"
assert_contains "$valid_out" "docker image rm argus-frontend:stub"
assert_not_contains "$valid_out" "postgres"
assert_not_contains "$valid_out" "redis"
assert_not_contains "$valid_out" "adminer"
assert_not_contains "$valid_out" "docker image prune"
assert_not_contains "$valid_out" "docker system prune"
assert_contains "$valid_out" "AGENTFLOW_BUILD_CACHE_SCOPE=argus-agentflow-"
assert_contains "$valid_out" "up -d --build --wait"
assert_contains "$valid_out" "http://127.0.0.1:18000/health"
assert_contains "$valid_out" "http://127.0.0.1:13000"
validation_line=$(grep -n "Config key AGENT_TIMEOUT is configured" "$valid_out" | head -n1 | cut -d: -f1)
overwrite_line=$(grep -n "Fully overwrote docker/env/backend/.env" "$valid_out" | head -n1 | cut -d: -f1)
down_line=$(grep -n "down --remove-orphans" "$valid_out" | head -n1 | cut -d: -f1)
image_line=$(grep -n "docker image rm argus/agentflow-runner:stub" "$valid_out" | head -n1 | cut -d: -f1)
skip_prune_line=$(grep -n "Skipping docker buildx prune" "$valid_out" | head -n1 | cut -d: -f1)
up_line=$(grep -n "up -d --build --wait" "$valid_out" | head -n1 | cut -d: -f1)
[[ "$validation_line" -lt "$overwrite_line" && "$overwrite_line" -lt "$down_line" && "$down_line" -lt "$image_line" && "$image_line" -lt "$skip_prune_line" && "$skip_prune_line" -lt "$up_line" ]] || fail "Expected validation -> overwrite -> down -> image removal -> prune decision -> up order"

# Unsafe image refs are refused and never passed to docker image rm.
unsafe_dir="$(new_fixture unsafe-image)"
write_valid_config "$unsafe_dir"
unsafe_out="$unsafe_dir/unsafe.out"
set +e
( cd "$unsafe_dir" && ARGUS_STUB_DOCKER=true ARGUS_STUB_IMAGE_REF_BACKEND=postgres:latest ./argus-reset-rebuild-start.sh ) >"$unsafe_out" 2>&1
unsafe_rc=$?
set -e
[[ "$unsafe_rc" -ne 0 ]] || fail "Unsafe image ref should fail"
assert_contains "$unsafe_out" "Refusing to remove non-allowlisted image for backend: postgres:latest"
assert_not_contains "$unsafe_out" "docker image rm postgres:latest"

# Explicit volume deletion previews exact names and remains compose-scoped.
vol_dir="$(new_fixture volumes)"
write_valid_config "$vol_dir"
vol_out="$vol_dir/volumes.out"
( cd "$vol_dir" && ARGUS_STUB_DOCKER=true ARGUS_RESET_VOLUMES=delete ./argus-reset-rebuild-start.sh ) >"$vol_out" 2>&1
assert_contains "$vol_out" "Argus_agentflow_runner_work"
assert_contains "$vol_out" "Argus_scan_workspace"
assert_contains "$vol_out" "--volumes"
assert_not_contains "$vol_out" "docker volume prune"

# Explicit Buildx prune runs after compose down and before compose up.
prune_dir="$(new_fixture prune)"
write_valid_config "$prune_dir"
prune_out="$prune_dir/prune.out"
( cd "$prune_dir" && ARGUS_STUB_DOCKER=true ARGUS_BUILDX_PRUNE=true ./argus-reset-rebuild-start.sh ) >"$prune_out" 2>&1
assert_contains "$prune_out" "[stub] docker buildx prune -a -f"
down_line=$(grep -n "down --remove-orphans" "$prune_out" | head -n1 | cut -d: -f1)
prune_line=$(grep -n "docker buildx prune -a -f" "$prune_out" | head -n1 | cut -d: -f1)
up_line=$(grep -n "up -d --build --wait" "$prune_out" | head -n1 | cut -d: -f1)
[[ "$down_line" -lt "$prune_line" && "$prune_line" -lt "$up_line" ]] || fail "Buildx prune should occur after down and before up"

# Dry-run keeps file operations non-mutating while showing command plan.
dry_dir="$(new_fixture dry)"
write_valid_config "$dry_dir"
printf 'STALE_KEY=still_here\n' > "$dry_dir/docker/env/backend/.env"
dry_out="$dry_dir/dry.out"
( cd "$dry_dir" && ./argus-reset-rebuild-start.sh --dry-run ) >"$dry_out" 2>&1
assert_contains "$dry_out" "[dry-run] cp"
assert_contains "$dry_out" "[dry-run] docker compose"
assert_contains "$dry_dir/docker/env/backend/.env" "STALE_KEY=still_here"

echo "[test] argus-reset-rebuild-start tests passed"
