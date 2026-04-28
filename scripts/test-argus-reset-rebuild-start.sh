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

assert_no_global_prune_execution() {
  local file="$1"
  if grep -Eq '\[(stub|dry-run)\] docker (system|buildx) prune' "$file"; then
    fail "Expected $file not to execute global Docker prune commands"
  fi
}

assert_banner_contact() {
  local file="$1"
  assert_contains "$file" "ARGUS"
  assert_contains "$file" "happytraveller"
  assert_contains "$file" "18630897985"
  assert_contains "$file" "happytraveller@163.com"
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
    volumes:
      - agentflow_runner_work:/work
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
    volumes:
      - backend_uploads:/app/uploads
      - backend_runtime_data:/app/data/runtime
      - scan_workspace:/tmp/Argus/scans
  frontend:
    build:
      context: ./frontend
    ports:
      - "${Argus_FRONTEND_PORT:-13000}:5173"
    volumes:
      - frontend_node_modules:/app/node_modules
      - frontend_pnpm_store:/pnpm/store
  db:
    image: postgres:18-alpine
    volumes:
      - postgres_data:/var/lib/postgresql
  redis:
    image: redis:8-alpine
    volumes:
      - redis_data:/data
  adminer:
    image: adminer:latest
volumes:
  agentflow_runner_work:
  postgres_data:
  backend_uploads:
  backend_runtime_data:
  scan_workspace:
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

# Help documents the new operator contract and author/commercial notice.
help_dir="$(new_fixture help)"
help_out="$help_dir/help.out"
( cd "$help_dir" && ./argus-reset-rebuild-start.sh --help ) >"$help_out" 2>&1
assert_banner_contact "$help_out"
assert_contains "$help_out" "./argus-reset-rebuild-start.sh [--dry-run] [--wait-exit] [--help] -- <mode>"
assert_contains "$help_out" "Run modes:"
assert_contains "$help_out" "default"
assert_contains "$help_out" "keep-cache"
assert_contains "$help_out" "aggressive"
assert_contains "$help_out" "Run directly from bash, zsh, or another shell"
assert_contains "$help_out" "Interactive TTY runs"
assert_contains "$help_out" "CI=true or non-TTY runs never prompt"
assert_contains "$help_out" "docker system prune -af --volumes"
assert_contains "$help_out" "docker compose up --build"
assert_contains "$help_out" "--wait-exit"
assert_contains "$help_out" "ARGUS_STUB_DOCKER=true"

# Parser rejects invalid post-separator modes before config or Docker work.
invalid_dir="$(new_fixture invalid-mode)"
invalid_out="$invalid_dir/invalid-mode.out"
set +e
( cd "$invalid_dir" && ./argus-reset-rebuild-start.sh -- banana ) >"$invalid_out" 2>&1
invalid_rc=$?
set -e
[[ "$invalid_rc" -ne 0 ]] || fail "Unknown mode should fail"
assert_contains "$invalid_out" "Unknown run mode: banana"
assert_contains "$invalid_out" "Supported run modes"
assert_not_contains "$invalid_out" "docker compose"

extra_dir="$(new_fixture extra-mode)"
extra_out="$extra_dir/extra-mode.out"
set +e
( cd "$extra_dir" && ./argus-reset-rebuild-start.sh -- default extra ) >"$extra_out" 2>&1
extra_rc=$?
set -e
[[ "$extra_rc" -ne 0 ]] || fail "Multiple post-separator tokens should fail"
assert_contains "$extra_out" "Expected at most one run mode after --"
assert_not_contains "$extra_out" "docker compose"

flag_after_dir="$(new_fixture flag-after)"
flag_after_out="$flag_after_dir/flag-after.out"
set +e
( cd "$flag_after_dir" && ./argus-reset-rebuild-start.sh -- --wait-exit ) >"$flag_after_out" 2>&1
flag_after_rc=$?
set -e
[[ "$flag_after_rc" -ne 0 ]] || fail "Flag after separator should be treated as invalid mode"
assert_contains "$flag_after_out" "Unknown run mode: --wait-exit"
assert_not_contains "$flag_after_out" "docker compose"

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
    ./argus-reset-rebuild-start.sh --wait-exit -- default
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
assert_no_global_prune_execution "$interactive_out"

# Valid config fully overwrites backend .env, redacts secrets, preserves volumes/cache by default, and starts Compose in foreground.
valid_dir="$(new_fixture valid)"
write_valid_config "$valid_dir"
printf 'STALE_KEY=must_be_removed\n' > "$valid_dir/docker/env/backend/.env"
valid_out="$valid_dir/valid.out"
( cd "$valid_dir" && ARGUS_STUB_DOCKER=true ./argus-reset-rebuild-start.sh ) >"$valid_out" 2>&1
cmp "$valid_dir/.argus-intelligent-audit.env" "$valid_dir/docker/env/backend/.env" >/dev/null || fail "backend .env should be fully overwritten"
assert_not_contains "$valid_dir/docker/env/backend/.env" "STALE_KEY"
assert_not_contains "$valid_out" "SECRET_SENTINEL_SHOULD_NOT_PRINT"
assert_banner_contact "$valid_out"
assert_contains "$valid_out" "Run mode: default"
assert_contains "$valid_out" "preserving data volumes and Docker image/build cache"
assert_contains "$valid_out" "down --remove-orphans"
assert_not_contains "$valid_out" "down --volumes --remove-orphans"
assert_contains "$valid_out" "AGENTFLOW_BUILD_CACHE_SCOPE=argus-agentflow-"
assert_contains "$valid_out" "up --build"
assert_not_contains "$valid_out" "up -d --build --wait"
assert_not_contains "$valid_out" "curl -fsS http://127.0.0.1:13000"
assert_no_global_prune_execution "$valid_out"
banner_line="$(line_no "$valid_out" "happytraveller")"
validation_line="$(line_no "$valid_out" "Config key AGENT_TIMEOUT is configured")"
overwrite_line="$(line_no "$valid_out" "Fully overwrote docker/env/backend/.env")"
down_line="$(line_no "$valid_out" "down --remove-orphans")"
up_line="$(line_no "$valid_out" "up --build")"
[[ "$banner_line" -lt "$validation_line" && "$validation_line" -lt "$overwrite_line" && "$overwrite_line" -lt "$down_line" && "$down_line" -lt "$up_line" ]] || fail "Expected banner -> validation -> overwrite -> down -> foreground up order"

# Explicit default matches no-mode safety, even when legacy prune env is true.
default_dir="$(new_fixture explicit-default)"
write_valid_config "$default_dir"
default_out="$default_dir/default.out"
( cd "$default_dir" && ARGUS_STUB_DOCKER=true ARGUS_DOCKER_SYSTEM_PRUNE=true ./argus-reset-rebuild-start.sh -- default ) >"$default_out" 2>&1
assert_contains "$default_out" "Run mode: default"
assert_contains "$default_out" "down --remove-orphans"
assert_not_contains "$default_out" "down --volumes --remove-orphans"
assert_no_global_prune_execution "$default_out"

# keep-cache deletes this Compose project's managed volumes, but never executes global image/build cache prune.
keep_cache_dir="$(new_fixture keep-cache)"
write_valid_config "$keep_cache_dir"
keep_cache_out="$keep_cache_dir/keep-cache.out"
( cd "$keep_cache_dir" && ARGUS_STUB_DOCKER=true ARGUS_DOCKER_SYSTEM_PRUNE=true ./argus-reset-rebuild-start.sh -- keep-cache ) >"$keep_cache_out" 2>&1
assert_contains "$keep_cache_out" "Run mode: keep-cache"
assert_contains "$keep_cache_out" "removing this Compose project's managed volumes"
assert_contains "$keep_cache_out" "preserving Docker image/build cache"
assert_contains "$keep_cache_out" "down --volumes --remove-orphans"
assert_no_global_prune_execution "$keep_cache_out"

# aggressive mode explicitly permits destructive Compose volume cleanup and global system prune.
aggressive_dir="$(new_fixture aggressive)"
write_valid_config "$aggressive_dir"
aggressive_out="$aggressive_dir/aggressive.out"
( cd "$aggressive_dir" && ARGUS_STUB_DOCKER=true ./argus-reset-rebuild-start.sh -- aggressive ) >"$aggressive_out" 2>&1
assert_contains "$aggressive_out" "Run mode: aggressive"
assert_contains "$aggressive_out" "WARNING: aggressive mode enabled"
assert_contains "$aggressive_out" "down --volumes --remove-orphans"
assert_contains "$aggressive_out" "[stub] docker system prune -af --volumes"
aggressive_warning_line="$(line_no "$aggressive_out" "WARNING: aggressive mode enabled")"
aggressive_prune_line="$(line_no "$aggressive_out" "[stub] docker system prune -af --volumes")"
[[ "$aggressive_warning_line" -lt "$aggressive_prune_line" ]] || fail "Aggressive warning should appear before system prune"

# Legacy env can disable only aggressive global system prune; compose volume cleanup still happens.
aggressive_skip_dir="$(new_fixture aggressive-skip)"
write_valid_config "$aggressive_skip_dir"
aggressive_skip_out="$aggressive_skip_dir/aggressive-skip.out"
( cd "$aggressive_skip_dir" && ARGUS_STUB_DOCKER=true ARGUS_DOCKER_SYSTEM_PRUNE=false ./argus-reset-rebuild-start.sh -- aggressive ) >"$aggressive_skip_out" 2>&1
assert_contains "$aggressive_skip_out" "Run mode: aggressive"
assert_contains "$aggressive_skip_out" "down --volumes --remove-orphans"
assert_contains "$aggressive_skip_out" "Skipping global Docker prune because ARGUS_DOCKER_SYSTEM_PRUNE=false"
assert_no_global_prune_execution "$aggressive_skip_out"

# Wait-exit honors configured frontend port and exits after stubbed readiness with modes.
wait_dir="$(new_fixture wait)"
write_valid_config "$wait_dir"
wait_out="$wait_dir/wait.out"
( cd "$wait_dir" && ARGUS_STUB_DOCKER=true Argus_FRONTEND_PORT=13099 ./argus-reset-rebuild-start.sh --wait-exit -- default ) >"$wait_out" 2>&1
assert_contains "$wait_out" "up -d --build"
assert_contains "$wait_out" "curl -fsS http://127.0.0.1:13099"
assert_contains "$wait_out" "Complete. Frontend: http://127.0.0.1:13099"
assert_no_global_prune_execution "$wait_out"

wait_aggressive_dir="$(new_fixture wait-aggressive)"
write_valid_config "$wait_aggressive_dir"
wait_aggressive_out="$wait_aggressive_dir/wait-aggressive.out"
( cd "$wait_aggressive_dir" && ARGUS_STUB_DOCKER=true Argus_FRONTEND_PORT=13100 ./argus-reset-rebuild-start.sh --wait-exit -- aggressive ) >"$wait_aggressive_out" 2>&1
assert_contains "$wait_aggressive_out" "Run mode: aggressive"
assert_contains "$wait_aggressive_out" "down --volumes --remove-orphans"
assert_contains "$wait_aggressive_out" "[stub] docker system prune -af --volumes"
assert_contains "$wait_aggressive_out" "up -d --build"
assert_contains "$wait_aggressive_out" "curl -fsS http://127.0.0.1:13100"
assert_contains "$wait_aggressive_out" "Complete. Frontend: http://127.0.0.1:13100"

# Dry-run keeps backend env non-mutating while showing the safe default command plan.
dry_dir="$(new_fixture dry)"
write_valid_config "$dry_dir"
printf 'STALE_KEY=still_here\n' > "$dry_dir/docker/env/backend/.env"
dry_out="$dry_dir/dry.out"
( cd "$dry_dir" && ./argus-reset-rebuild-start.sh --dry-run -- default ) >"$dry_out" 2>&1
assert_contains "$dry_out" "[dry-run] cp"
assert_contains "$dry_out" "[dry-run] docker compose"
assert_no_global_prune_execution "$dry_out"
assert_contains "$dry_dir/docker/env/backend/.env" "STALE_KEY=still_here"

# Aggressive dry-run exposes the destructive plan without executing it.
dry_aggressive_dir="$(new_fixture dry-aggressive)"
write_valid_config "$dry_aggressive_dir"
dry_aggressive_out="$dry_aggressive_dir/dry-aggressive.out"
( cd "$dry_aggressive_dir" && ./argus-reset-rebuild-start.sh --dry-run -- aggressive ) >"$dry_aggressive_out" 2>&1
assert_contains "$dry_aggressive_out" "[dry-run] docker compose"
assert_contains "$dry_aggressive_out" "[dry-run] docker system prune -af --volumes"

# Bare separator is accepted and means default.
bare_dir="$(new_fixture bare-separator)"
write_valid_config "$bare_dir"
bare_out="$bare_dir/bare.out"
( cd "$bare_dir" && ARGUS_STUB_DOCKER=true ./argus-reset-rebuild-start.sh -- ) >"$bare_out" 2>&1
assert_contains "$bare_out" "Run mode: default"
assert_no_global_prune_execution "$bare_out"

echo "[test] argus-reset-rebuild-start tests passed"
