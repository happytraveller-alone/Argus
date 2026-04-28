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

line_no() {
  local file="$1" pattern="$2"
  local line
  line="$(grep -n -F -- "$pattern" "$file" | head -n1 | cut -d: -f1 || true)"
  [[ -n "$line" ]] || fail "Expected $file to contain line for: $pattern"
  printf '%s' "$line"
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

# Help documents the new operator contract.
help_dir="$(new_fixture help)"
help_out="$help_dir/help.out"
( cd "$help_dir" && ./argus-reset-rebuild-start.sh --help ) >"$help_out" 2>&1
assert_contains "$help_out" "./argus-reset-rebuild-start.sh [--dry-run] [--wait-exit] [--help]"
assert_contains "$help_out" "Run directly from bash, zsh, or another shell"
assert_contains "$help_out" "Interactive TTY runs"
assert_contains "$help_out" "CI=true or non-TTY runs never prompt"
assert_contains "$help_out" "docker system prune -af --volumes"
assert_contains "$help_out" "docker compose up --build"
assert_contains "$help_out" "--wait-exit"
assert_contains "$help_out" "ARGUS_STUB_DOCKER=true"

# Missing config in CI/non-TTY exits before Docker cleanup and creates a template/example.
missing_dir="$(new_fixture missing)"
missing_out="$missing_dir/missing.out"
set +e
( cd "$missing_dir" && CI=true ARGUS_STUB_DOCKER=true ./argus-reset-rebuild-start.sh ) >"$missing_out" 2>&1
missing_rc=$?
set -e
[[ "$missing_rc" -ne 0 ]] || fail "Missing config should fail in CI/non-TTY"
[[ -f "$missing_dir/.argus-intelligent-audit.env.example" ]] || fail "Missing config should create template/example"
assert_not_contains "$missing_out" "docker compose"
assert_not_contains "$missing_out" "docker system prune"
assert_not_contains "$missing_out" "curl -fsS"

# Placeholder config exits before Docker cleanup in non-interactive mode.
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
( cd "$placeholder_dir" && CI=true ARGUS_STUB_DOCKER=true ./argus-reset-rebuild-start.sh ) >"$placeholder_out" 2>&1
placeholder_rc=$?
set -e
[[ "$placeholder_rc" -ne 0 ]] || fail "Placeholder config should fail"
assert_not_contains "$placeholder_out" "docker compose"
assert_not_contains "$placeholder_out" "docker system prune"

# Missing required key exits before Docker cleanup in non-interactive mode.
missing_key_dir="$(new_fixture missing-key)"
write_valid_config "$missing_key_dir"
grep -v '^LLM_MODEL=' "$missing_key_dir/.argus-intelligent-audit.env" > "$missing_key_dir/.argus-intelligent-audit.env.tmp"
mv "$missing_key_dir/.argus-intelligent-audit.env.tmp" "$missing_key_dir/.argus-intelligent-audit.env"
missing_key_out="$missing_key_dir/missing-key.out"
set +e
( cd "$missing_key_dir" && CI=true ARGUS_STUB_DOCKER=true ./argus-reset-rebuild-start.sh ) >"$missing_key_out" 2>&1
missing_key_rc=$?
set -e
[[ "$missing_key_rc" -ne 0 ]] || fail "Missing required key should fail"
assert_contains "$missing_key_out" "LLM_MODEL"
assert_not_contains "$missing_key_out" "docker compose"
assert_not_contains "$missing_key_out" "docker system prune"

# Interactive setup generates config from template, redacts secrets, overwrites backend env, and wait-exit polls frontend.
interactive_dir="$(new_fixture interactive)"
interactive_out="$interactive_dir/interactive.out"
set +e
(
  cd "$interactive_dir"
  printf 'openai\nINTERACTIVE_API_KEY_SHOULD_NOT_PRINT\ngpt-5.5\nhttps://api.openai.com/v1\n' | \
    ARGUS_TEST_INTERACTIVE=true \
    ARGUS_TEST_SECRET_KEY=GENERATED_SECRET_FOR_TEST \
    ARGUS_STUB_DOCKER=true \
    ./argus-reset-rebuild-start.sh --wait-exit
) >"$interactive_out" 2>&1
interactive_rc=$?
set -e
[[ "$interactive_rc" -eq 0 ]] || fail "Interactive setup should pass; output: $(cat "$interactive_out")"
[[ -f "$interactive_dir/.argus-intelligent-audit.env" ]] || fail "Interactive config should be written"
cmp "$interactive_dir/.argus-intelligent-audit.env" "$interactive_dir/docker/env/backend/.env" >/dev/null || fail "backend .env should match generated config"
assert_contains "$interactive_dir/.argus-intelligent-audit.env" "SECRET_KEY=GENERATED_SECRET_FOR_TEST"
assert_contains "$interactive_dir/.argus-intelligent-audit.env" "LLM_API_KEY=INTERACTIVE_API_KEY_SHOULD_NOT_PRINT"
assert_contains "$interactive_dir/.argus-intelligent-audit.env" "LLM_MODEL=gpt-5.5"
assert_contains "$interactive_dir/.argus-intelligent-audit.env" "AGENT_ENABLED=true"
assert_not_contains "$interactive_out" "INTERACTIVE_API_KEY_SHOULD_NOT_PRINT"
assert_not_contains "$interactive_out" "GENERATED_SECRET_FOR_TEST"
assert_contains "$interactive_out" "up -d --build"
assert_contains "$interactive_out" "curl -fsS http://127.0.0.1:13000"

# Valid config fully overwrites backend .env, redacts secrets, runs default global system prune,
# and starts Compose in foreground by default.
valid_dir="$(new_fixture valid)"
write_valid_config "$valid_dir"
printf 'STALE_KEY=must_be_removed\n' > "$valid_dir/docker/env/backend/.env"
valid_out="$valid_dir/valid.out"
( cd "$valid_dir" && ARGUS_STUB_DOCKER=true ./argus-reset-rebuild-start.sh ) >"$valid_out" 2>&1
cmp "$valid_dir/.argus-intelligent-audit.env" "$valid_dir/docker/env/backend/.env" >/dev/null || fail "backend .env should be fully overwritten"
assert_not_contains "$valid_dir/docker/env/backend/.env" "STALE_KEY"
assert_not_contains "$valid_out" "SECRET_SENTINEL_SHOULD_NOT_PRINT"
assert_contains "$valid_out" "docker system prune -af --volumes"
assert_contains "$valid_out" "AGENTFLOW_BUILD_CACHE_SCOPE=argus-agentflow-"
assert_contains "$valid_out" "up --build"
assert_not_contains "$valid_out" "up -d --build --wait"
assert_not_contains "$valid_out" "curl -fsS http://127.0.0.1:13000"
validation_line="$(line_no "$valid_out" "Config key AGENT_TIMEOUT is configured")"
overwrite_line="$(line_no "$valid_out" "Fully overwrote docker/env/backend/.env")"
down_line="$(line_no "$valid_out" "down --remove-orphans")"
prune_line="$(line_no "$valid_out" "docker system prune -af --volumes")"
up_line="$(line_no "$valid_out" "up --build")"
[[ "$validation_line" -lt "$overwrite_line" && "$overwrite_line" -lt "$down_line" && "$down_line" -lt "$prune_line" && "$prune_line" -lt "$up_line" ]] || fail "Expected validation -> overwrite -> down -> system prune -> foreground up order"

# The accepted prune command can be disabled explicitly without changing the default.
skip_prune_dir="$(new_fixture skip-prune)"
write_valid_config "$skip_prune_dir"
skip_prune_out="$skip_prune_dir/skip-prune.out"
( cd "$skip_prune_dir" && ARGUS_STUB_DOCKER=true ARGUS_DOCKER_SYSTEM_PRUNE=false ./argus-reset-rebuild-start.sh ) >"$skip_prune_out" 2>&1
assert_contains "$skip_prune_out" "Skipping docker system prune -af --volumes"
assert_not_contains "$skip_prune_out" "[stub] docker system prune -af --volumes"

# Wait-exit honors configured frontend port and exits after stubbed readiness.
wait_dir="$(new_fixture wait)"
write_valid_config "$wait_dir"
wait_out="$wait_dir/wait.out"
( cd "$wait_dir" && ARGUS_STUB_DOCKER=true Argus_FRONTEND_PORT=13099 ./argus-reset-rebuild-start.sh --wait-exit ) >"$wait_out" 2>&1
assert_contains "$wait_out" "up -d --build"
assert_contains "$wait_out" "curl -fsS http://127.0.0.1:13099"
assert_contains "$wait_out" "Complete. Frontend: http://127.0.0.1:13099"

# Dry-run keeps backend env non-mutating while showing command plan.
dry_dir="$(new_fixture dry)"
write_valid_config "$dry_dir"
printf 'STALE_KEY=still_here\n' > "$dry_dir/docker/env/backend/.env"
dry_out="$dry_dir/dry.out"
( cd "$dry_dir" && ./argus-reset-rebuild-start.sh --dry-run ) >"$dry_out" 2>&1
assert_contains "$dry_out" "[dry-run] cp"
assert_contains "$dry_out" "[dry-run] docker compose"
assert_contains "$dry_out" "[dry-run] docker system prune -af --volumes"
assert_contains "$dry_dir/docker/env/backend/.env" "STALE_KEY=still_here"

echo "[test] argus-reset-rebuild-start tests passed"
