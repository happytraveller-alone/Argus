#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_SRC="$ROOT_DIR/argus-bootstrap.sh"
VALIDATOR_SRC="$ROOT_DIR/scripts/validate-llm-config.sh"
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
  mkdir -p "$dir/scripts"
  cp "$SCRIPT_SRC" "$dir/argus-bootstrap.sh"
  cp "$VALIDATOR_SRC" "$dir/scripts/validate-llm-config.sh"
  cp "$ROOT_DIR/env.example" "$dir/env.example"
  chmod +x "$dir/argus-bootstrap.sh"
  chmod +x "$dir/scripts/validate-llm-config.sh"
  cat > "$dir/docker-compose.yml" <<'COMPOSE'
services:
  opengrep-runner:
    build:
      context: .
  backend:
    build:
      context: .
    env_file:
      - path: "${ARGUS_ENV_FILE:-./.env}"
        required: true
    environment:
      ARGUS_RESET_IMPORT_TOKEN: "${ARGUS_RESET_IMPORT_TOKEN:-}"
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
  cat > "$dir/.env" <<'ENV'
SECRET_KEY=local_test_secret_0123456789abcdef
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=11520
DOCKER_SOCKET_PATH=/var/run/docker.sock
LLM_PROVIDER=openai_compatible
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
( cd "$help_dir" && ./argus-bootstrap.sh --help ) >"$help_out" 2>&1
assert_banner_contact "$help_out"
assert_contains "$help_out" "./argus-bootstrap.sh [--dry-run] [--wait-exit] [--help] -- <mode>"
assert_contains "$help_out" "Run modes:"
assert_contains "$help_out" "default"
assert_contains "$help_out" "keep-cache"
assert_contains "$help_out" "aggressive"
assert_contains "$help_out" "Compatible with both bash and zsh"
assert_contains "$help_out" "Start modes:"
assert_contains "$help_out" "env.example"
assert_contains "$help_out" ".env"
assert_contains "$help_out" "docker system prune -af --volumes"
assert_contains "$help_out" "docker compose up -d --build"
assert_contains "$help_out" "--wait-exit"
assert_contains "$help_out" "ARGUS_STUB_DOCKER=true"
assert_contains "$help_out" "scripts/validate-llm-config.sh --env-file"

# Standalone validator accepts valid LLM env and rejects missing/placeholder values.
validator_dir="$(new_fixture validator)"
write_valid_config "$validator_dir"
validator_out="$validator_dir/validator.out"
( cd "$validator_dir" && ./scripts/validate-llm-config.sh --env-file ./.env ) >"$validator_out" 2>&1
assert_contains "$validator_out" "LLM env config is valid"

# Parser rejects invalid post-separator modes before config or Docker work.
invalid_dir="$(new_fixture invalid-mode)"
invalid_out="$invalid_dir/invalid-mode.out"
set +e
( cd "$invalid_dir" && ./argus-bootstrap.sh -- banana ) >"$invalid_out" 2>&1
invalid_rc=$?
set -e
[[ "$invalid_rc" -ne 0 ]] || fail "Unknown mode should fail"
assert_contains "$invalid_out" "Unknown run mode: banana"
assert_contains "$invalid_out" "Supported run modes"
assert_not_contains "$invalid_out" "docker compose"

extra_dir="$(new_fixture extra-mode)"
extra_out="$extra_dir/extra-mode.out"
set +e
( cd "$extra_dir" && ./argus-bootstrap.sh -- default extra ) >"$extra_out" 2>&1
extra_rc=$?
set -e
[[ "$extra_rc" -ne 0 ]] || fail "Multiple post-separator tokens should fail"
assert_contains "$extra_out" "Expected at most one run mode after --"
assert_not_contains "$extra_out" "docker compose"

flag_after_dir="$(new_fixture flag-after)"
flag_after_out="$flag_after_dir/flag-after.out"
set +e
( cd "$flag_after_dir" && ./argus-bootstrap.sh -- --wait-exit ) >"$flag_after_out" 2>&1
flag_after_rc=$?
set -e
[[ "$flag_after_rc" -ne 0 ]] || fail "Flag after separator should be treated as invalid mode"
assert_contains "$flag_after_out" "Unknown run mode: --wait-exit"
assert_not_contains "$flag_after_out" "docker compose"

# Missing root .env exits before Docker cleanup after copying env.example.
missing_dir="$(new_fixture missing)"
missing_out="$missing_dir/missing.out"
set +e
( cd "$missing_dir" && CI=true ARGUS_STUB_DOCKER=true ./argus-bootstrap.sh ) >"$missing_out" 2>&1
missing_rc=$?
set -e
[[ "$missing_rc" -ne 0 ]] || fail "Missing .env should stop bootstrap after copying template"
assert_contains "$missing_out" "Created .env from env.example"
assert_contains "$missing_out" "Generated SECRET_KEY in root .env"
assert_contains "$missing_out" "scripts/validate-llm-config.sh --env-file ./.env"
assert_not_contains "$missing_out" "docker compose"
assert_not_contains "$missing_out" "docker system prune"
assert_not_contains "$missing_out" "curl -fsS"
missing_secret="$(grep '^SECRET_KEY=' "$missing_dir/.env" | cut -d= -f2-)"
[[ -n "$missing_secret" ]] || fail "Missing .env should get a generated SECRET_KEY"
[[ "$missing_secret" != "your-super-secret-key-change-this-in-production" ]] || fail "Generated .env should not keep SECRET_KEY placeholder"
[[ "${#missing_secret}" -ge 64 ]] || fail "Generated SECRET_KEY should be at least 64 characters"

# Existing root .env missing SECRET_KEY is repaired before validation so users only fill LLM settings manually.
missing_secret_dir="$(new_fixture missing-secret)"
cat > "$missing_secret_dir/.env" <<'ENV'
DOCKER_SOCKET_PATH=/var/run/docker.sock
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-your-api-key
LLM_MODEL=gpt-5
LLM_BASE_URL=https://api.openai.com/v1
AGENT_ENABLED=true
AGENT_MAX_ITERATIONS=5
AGENT_TIMEOUT=1800
ENV
missing_secret_out="$missing_secret_dir/missing-secret.out"
set +e
( cd "$missing_secret_dir" && CI=true ARGUS_STUB_DOCKER=true ./argus-bootstrap.sh ) >"$missing_secret_out" 2>&1
missing_secret_rc=$?
set -e
[[ "$missing_secret_rc" -ne 0 ]] || fail "Placeholder LLM config should still fail after SECRET_KEY repair"
assert_contains "$missing_secret_out" "Generated SECRET_KEY in root .env"
assert_contains "$missing_secret_out" "LLM_API_KEY still contains a placeholder value"
assert_not_contains "$missing_secret_out" "Required env key SECRET_KEY is missing or empty"
repaired_secret="$(grep '^SECRET_KEY=' "$missing_secret_dir/.env" | cut -d= -f2-)"
[[ -n "$repaired_secret" ]] || fail "Existing .env missing SECRET_KEY should be repaired"
[[ "${#repaired_secret}" -ge 64 ]] || fail "Repaired SECRET_KEY should be at least 64 characters"

# Existing root .env with the template SECRET_KEY placeholder is repaired, but real values are preserved.
placeholder_secret_dir="$(new_fixture placeholder-secret)"
cat > "$placeholder_secret_dir/.env" <<'ENV'
SECRET_KEY=your-super-secret-key-change-this-in-production
DOCKER_SOCKET_PATH=/var/run/docker.sock
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-your-api-key
LLM_MODEL=gpt-5
LLM_BASE_URL=https://api.openai.com/v1
AGENT_ENABLED=true
AGENT_MAX_ITERATIONS=5
AGENT_TIMEOUT=1800
ENV
placeholder_secret_out="$placeholder_secret_dir/placeholder-secret.out"
set +e
( cd "$placeholder_secret_dir" && CI=true ARGUS_STUB_DOCKER=true ./argus-bootstrap.sh ) >"$placeholder_secret_out" 2>&1
placeholder_secret_rc=$?
set -e
[[ "$placeholder_secret_rc" -ne 0 ]] || fail "Placeholder LLM config should still fail after placeholder SECRET_KEY repair"
assert_contains "$placeholder_secret_out" "Generated SECRET_KEY in root .env"
assert_not_contains "$placeholder_secret_out" "SECRET_KEY still contains a placeholder value"
placeholder_repaired_secret="$(grep '^SECRET_KEY=' "$placeholder_secret_dir/.env" | cut -d= -f2-)"
[[ "$placeholder_repaired_secret" != "your-super-secret-key-change-this-in-production" ]] || fail "Template SECRET_KEY placeholder should be replaced"
[[ "${#placeholder_repaired_secret}" -ge 64 ]] || fail "Placeholder SECRET_KEY replacement should be at least 64 characters"

preserve_secret_dir="$(new_fixture preserve-secret)"
write_valid_config "$preserve_secret_dir"
before_secret="$(grep '^SECRET_KEY=' "$preserve_secret_dir/.env" | cut -d= -f2-)"
preserve_secret_out="$preserve_secret_dir/preserve-secret.out"
( cd "$preserve_secret_dir" && ARGUS_STUB_DOCKER=true ARGUS_TEST_IMPORT_TOKEN=IMPORT_TOKEN_SHOULD_NOT_PRINT ./argus-bootstrap.sh --wait-exit -- default ) >"$preserve_secret_out" 2>&1
after_secret="$(grep '^SECRET_KEY=' "$preserve_secret_dir/.env" | cut -d= -f2-)"
[[ "$before_secret" == "$after_secret" ]] || fail "Existing real SECRET_KEY should not be regenerated on every bootstrap"
assert_not_contains "$preserve_secret_out" "Generated SECRET_KEY in root .env"

# Placeholder config exits before Docker cleanup in non-interactive mode.
placeholder_dir="$(new_fixture placeholder)"
cat > "$placeholder_dir/.env" <<'ENV'
SECRET_KEY=local_test_secret_0123456789abcdef
DOCKER_SOCKET_PATH=/var/run/docker.sock
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-your-api-key
LLM_MODEL=gpt-5
LLM_BASE_URL=https://api.openai.com/v1
AGENT_ENABLED=true
AGENT_MAX_ITERATIONS=5
AGENT_TIMEOUT=1800
ENV
placeholder_out="$placeholder_dir/placeholder.out"
set +e
( cd "$placeholder_dir" && CI=true ARGUS_STUB_DOCKER=true ./argus-bootstrap.sh ) >"$placeholder_out" 2>&1
placeholder_rc=$?
set -e
[[ "$placeholder_rc" -ne 0 ]] || fail "Placeholder config should fail"
assert_not_contains "$placeholder_out" "docker compose"
assert_not_contains "$placeholder_out" "docker system prune"

# Missing required key exits before Docker cleanup in non-interactive mode.
missing_key_dir="$(new_fixture missing-key)"
write_valid_config "$missing_key_dir"
grep -v '^LLM_MODEL=' "$missing_key_dir/.env" > "$missing_key_dir/.env.tmp"
mv "$missing_key_dir/.env.tmp" "$missing_key_dir/.env"
missing_key_out="$missing_key_dir/missing-key.out"
set +e
( cd "$missing_key_dir" && CI=true ARGUS_STUB_DOCKER=true ./argus-bootstrap.sh ) >"$missing_key_out" 2>&1
missing_key_rc=$?
set -e
[[ "$missing_key_rc" -ne 0 ]] || fail "Missing required key should fail"
assert_contains "$missing_key_out" "LLM_MODEL"
assert_not_contains "$missing_key_out" "docker compose"
assert_not_contains "$missing_key_out" "docker system prune"

# Valid root .env redacts secrets/tokens, preserves volumes/cache by default, imports after backend readiness, and follows logs in foreground.
valid_dir="$(new_fixture valid)"
write_valid_config "$valid_dir"
valid_out="$valid_dir/valid.out"
( cd "$valid_dir" && ARGUS_STUB_DOCKER=true ARGUS_TEST_IMPORT_TOKEN=IMPORT_TOKEN_SHOULD_NOT_PRINT ./argus-bootstrap.sh ) >"$valid_out" 2>&1
assert_not_contains "$valid_out" "SECRET_SENTINEL_SHOULD_NOT_PRINT"
assert_banner_contact "$valid_out"
assert_contains "$valid_out" "Run mode: default"
assert_contains "$valid_out" "preserving data volumes and Docker image/build cache"
assert_contains "$valid_out" "down --remove-orphans"
assert_not_contains "$valid_out" "down --volumes --remove-orphans"
assert_contains "$valid_out" "Building Opengrep runner image without starting runner service containers"
assert_contains "$valid_out" "build opengrep-runner"
assert_not_contains "$valid_out" "build opengrep-runner codeql-runner"
assert_contains "$valid_out" "up -d --build"
assert_contains "$valid_out" "ARGUS_ENV_FILE=$valid_dir/.env"
assert_contains "$valid_out" "ARGUS_RESET_IMPORT_TOKEN="
assert_contains "$valid_out" "redacted-import-token"
assert_contains "$valid_out" "curl -fsS http://127.0.0.1:18000/health"
assert_contains "$valid_out" "curl -fsS -X POST"
assert_contains "$valid_out" "logs -f"
assert_not_contains "$valid_out" "IMPORT_TOKEN_SHOULD_NOT_PRINT"
assert_not_contains "$valid_out" "curl -fsS http://127.0.0.1:13000"
assert_no_global_prune_execution "$valid_out"
banner_line="$(line_no "$valid_out" "happytraveller")"
validation_line="$(line_no "$valid_out" "LLM env config is valid")"
down_line="$(line_no "$valid_out" "down --remove-orphans")"
runner_build_line="$(line_no "$valid_out" "build opengrep-runner")"
up_line="$(line_no "$valid_out" "up -d --build")"
backend_wait_line="$(line_no "$valid_out" "curl -fsS http://127.0.0.1:18000/health")"
import_line="$(line_no "$valid_out" "curl -fsS -X POST")"
logs_line="$(line_no "$valid_out" "logs -f")"
[[ "$banner_line" -lt "$validation_line" && "$validation_line" -lt "$down_line" && "$down_line" -lt "$runner_build_line" && "$runner_build_line" -lt "$up_line" && "$up_line" -lt "$backend_wait_line" && "$backend_wait_line" -lt "$import_line" && "$import_line" -lt "$logs_line" ]] || fail "Expected banner -> validation -> down -> runner image build -> detached up -> backend readiness -> import -> logs order"

# Explicit default matches no-mode safety, even when legacy prune env is true.
default_dir="$(new_fixture explicit-default)"
write_valid_config "$default_dir"
default_out="$default_dir/default.out"
( cd "$default_dir" && ARGUS_STUB_DOCKER=true ARGUS_DOCKER_SYSTEM_PRUNE=true ./argus-bootstrap.sh -- default ) >"$default_out" 2>&1
assert_contains "$default_out" "Run mode: default"
assert_contains "$default_out" "down --remove-orphans"
assert_not_contains "$default_out" "down --volumes --remove-orphans"
assert_no_global_prune_execution "$default_out"

# keep-cache deletes this Compose project's managed volumes, but never executes global image/build cache prune.
keep_cache_dir="$(new_fixture keep-cache)"
write_valid_config "$keep_cache_dir"
keep_cache_out="$keep_cache_dir/keep-cache.out"
( cd "$keep_cache_dir" && ARGUS_STUB_DOCKER=true ARGUS_DOCKER_SYSTEM_PRUNE=true ./argus-bootstrap.sh -- keep-cache ) >"$keep_cache_out" 2>&1
assert_contains "$keep_cache_out" "Run mode: keep-cache"
assert_contains "$keep_cache_out" "removing this Compose project's managed volumes"
assert_contains "$keep_cache_out" "preserving Docker image/build cache"
assert_contains "$keep_cache_out" "down --volumes --remove-orphans"
assert_no_global_prune_execution "$keep_cache_out"

# aggressive mode explicitly permits destructive Compose volume cleanup and global system prune.
aggressive_dir="$(new_fixture aggressive)"
write_valid_config "$aggressive_dir"
aggressive_out="$aggressive_dir/aggressive.out"
( cd "$aggressive_dir" && ARGUS_STUB_DOCKER=true ./argus-bootstrap.sh -- aggressive ) >"$aggressive_out" 2>&1
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
( cd "$aggressive_skip_dir" && ARGUS_STUB_DOCKER=true ARGUS_DOCKER_SYSTEM_PRUNE=false ./argus-bootstrap.sh -- aggressive ) >"$aggressive_skip_out" 2>&1
assert_contains "$aggressive_skip_out" "Run mode: aggressive"
assert_contains "$aggressive_skip_out" "down --volumes --remove-orphans"
assert_contains "$aggressive_skip_out" "Skipping global Docker prune because ARGUS_DOCKER_SYSTEM_PRUNE=false"
assert_no_global_prune_execution "$aggressive_skip_out"

# Wait-exit honors configured frontend port and exits after stubbed readiness with modes.
wait_dir="$(new_fixture wait)"
write_valid_config "$wait_dir"
wait_out="$wait_dir/wait.out"
( cd "$wait_dir" && ARGUS_STUB_DOCKER=true Argus_FRONTEND_PORT=13099 ./argus-bootstrap.sh --wait-exit -- default ) >"$wait_out" 2>&1
assert_contains "$wait_out" "build opengrep-runner"
assert_not_contains "$wait_out" "build opengrep-runner codeql-runner"
assert_contains "$wait_out" "up -d --build"
assert_contains "$wait_out" "curl -fsS http://127.0.0.1:18000/health"
assert_contains "$wait_out" "curl -fsS -X POST"
assert_contains "$wait_out" "curl -fsS http://127.0.0.1:13099"
assert_contains "$wait_out" "Complete. Frontend: http://127.0.0.1:13099"
assert_no_global_prune_execution "$wait_out"

# Sanitized HTTP 200 import-test failure exits before reporting frontend readiness.
import_failure_dir="$(new_fixture import-failure)"
write_valid_config "$import_failure_dir"
import_failure_out="$import_failure_dir/import-failure.out"
set +e
( cd "$import_failure_dir" && ARGUS_STUB_DOCKER=true ARGUS_TEST_IMPORT_RESPONSE='{"success":false,"message":"mock failure","reasonCode":"llm_test_failed"}' ./argus-bootstrap.sh --wait-exit -- default ) >"$import_failure_out" 2>&1
import_failure_rc=$?
set -e
[[ "$import_failure_rc" -ne 0 ]] || fail "Import/test failure should stop bootstrap"
assert_contains "$import_failure_out" '"success":false'
assert_contains "$import_failure_out" "backend LLM env import/test returned failure"
assert_not_contains "$import_failure_out" "Complete. Frontend: http://127.0.0.1:13000"

wait_aggressive_dir="$(new_fixture wait-aggressive)"
write_valid_config "$wait_aggressive_dir"
wait_aggressive_out="$wait_aggressive_dir/wait-aggressive.out"
( cd "$wait_aggressive_dir" && ARGUS_STUB_DOCKER=true Argus_FRONTEND_PORT=13100 ./argus-bootstrap.sh --wait-exit -- aggressive ) >"$wait_aggressive_out" 2>&1
assert_contains "$wait_aggressive_out" "Run mode: aggressive"
assert_contains "$wait_aggressive_out" "down --volumes --remove-orphans"
assert_contains "$wait_aggressive_out" "[stub] docker system prune -af --volumes"
assert_contains "$wait_aggressive_out" "build opengrep-runner"
assert_not_contains "$wait_aggressive_out" "build opengrep-runner codeql-runner"
assert_contains "$wait_aggressive_out" "up -d --build"
assert_contains "$wait_aggressive_out" "curl -fsS http://127.0.0.1:18000/health"
assert_contains "$wait_aggressive_out" "curl -fsS -X POST"
assert_contains "$wait_aggressive_out" "curl -fsS http://127.0.0.1:13100"
assert_contains "$wait_aggressive_out" "Complete. Frontend: http://127.0.0.1:13100"

# Dry-run keeps backend env non-mutating while showing the safe default command plan and redacted import call.
dry_dir="$(new_fixture dry)"
write_valid_config "$dry_dir"
dry_out="$dry_dir/dry.out"
( cd "$dry_dir" && ./argus-bootstrap.sh --dry-run -- default ) >"$dry_out" 2>&1
assert_not_contains "$dry_out" "[dry-run] cp"
assert_contains "$dry_out" "[dry-run] docker compose"
assert_contains "$dry_out" "[dry-run] curl -fsS -X POST"
assert_contains "$dry_out" "redacted-import-token"
assert_no_global_prune_execution "$dry_out"

# docker/env is retired; root env.example is the only environment template surface.
retired_env_out="$TMP_ROOT/docker-env-retired.out"
while IFS= read -r tracked_env_path; do
  if [ -e "$ROOT_DIR/$tracked_env_path" ]; then
    echo "$tracked_env_path" >&2
    fail "docker/env should not contain tracked environment templates"
  fi
done < <(git -C "$ROOT_DIR" ls-files docker/env)
if rg -n "docker/env|\\.env\\.example" \
  "$ROOT_DIR/argus-bootstrap.sh" \
  "$ROOT_DIR/docker-compose.yml" \
  "$ROOT_DIR/scripts/validate-llm-config.sh" \
  "$ROOT_DIR/scripts/release-allowlist.txt" \
  "$ROOT_DIR/scripts/generate-release-branch.sh" \
  "$ROOT_DIR/scripts/release-templates" \
  "$ROOT_DIR/frontend/vite.config.ts" \
  "$ROOT_DIR/frontend/scripts/setup.cjs" \
  "$ROOT_DIR/frontend/scripts/setup.sh" \
  >"$retired_env_out"; then
  cat "$retired_env_out" >&2
  fail "docker/env or per-directory .env.example references should be retired"
fi

# Runner services are image-build targets only; default compose startup must not keep
# preflight service containers around after validation.
compose_render_out="$TMP_ROOT/compose.out"
docker compose --project-directory "$ROOT_DIR" --file "$ROOT_DIR/docker-compose.yml" config >"$compose_render_out"
runner_profile_count="$(grep -F -c 'profiles: [ "runner-build" ]' "$ROOT_DIR/docker-compose.yml" || true)"
[[ "$runner_profile_count" -eq 1 ]] || fail "only opengrep runner service should be a profile-only image build target"
if awk '
  /^  backend:/ { in_backend = 1; in_depends = 0; next }
  /^  [a-zA-Z0-9_-]+:/ { in_backend = 0; in_depends = 0 }
  in_backend && /^    depends_on:/ { in_depends = 1; next }
  in_backend && in_depends && /^    [a-zA-Z0-9_-]+:/ && $1 != "depends_on:" { in_depends = 0 }
  in_backend && in_depends && /opengrep-runner|codeql-runner|service_completed_successfully/ { found = 1 }
  END { exit found ? 0 : 1 }
' "$compose_render_out"; then
  fail "backend must not depend on one-shot runner service containers"
fi
assert_not_contains "$compose_render_out" "codeql-runner"
assert_not_contains "$compose_render_out" "SCANNER_CODEQL_IMAGE"
assert_not_contains "$compose_render_out" "SCANNER_CODEQL_COMPILE_SANDBOX_IMAGE"

release_compose_render_out="$TMP_ROOT/release-compose.out"
docker compose \
  --project-directory "$ROOT_DIR" \
  --file "$ROOT_DIR/scripts/release-templates/docker-compose.release-slim.yml" \
  config >"$release_compose_render_out"
assert_contains "$release_compose_render_out" "SCANNER_OPENGREP_IMAGE: ghcr.io/happytraveller-alone/argus-opengrep-runner:latest"
assert_not_contains "$release_compose_render_out" "codeql-runner"
assert_not_contains "$release_compose_render_out" "SCANNER_CODEQL_IMAGE"
assert_not_contains "$release_compose_render_out" "SCANNER_CODEQL_COMPILE_SANDBOX_IMAGE"
if grep -Eq '^  (opengrep-runner|codeql-runner):$' "$release_compose_render_out"; then
  fail "release compose must not define runner service containers"
fi

assert_not_contains "$ROOT_DIR/.github/workflows/docker-publish.yml" "argus-codeql-runner"
assert_not_contains "$ROOT_DIR/.github/workflows/docker-publish.yml" "docker/codeql-runner.Dockerfile"

# Aggressive dry-run exposes the destructive plan without executing it.
dry_aggressive_dir="$(new_fixture dry-aggressive)"
write_valid_config "$dry_aggressive_dir"
dry_aggressive_out="$dry_aggressive_dir/dry-aggressive.out"
( cd "$dry_aggressive_dir" && ./argus-bootstrap.sh --dry-run -- aggressive ) >"$dry_aggressive_out" 2>&1
assert_contains "$dry_aggressive_out" "[dry-run] docker compose"
assert_contains "$dry_aggressive_out" "[dry-run] docker system prune -af --volumes"

# Bare separator is accepted and means default.
bare_dir="$(new_fixture bare-separator)"
write_valid_config "$bare_dir"
bare_out="$bare_dir/bare.out"
( cd "$bare_dir" && ARGUS_STUB_DOCKER=true ./argus-bootstrap.sh -- ) >"$bare_out" 2>&1
assert_contains "$bare_out" "Run mode: default"
assert_no_global_prune_execution "$bare_out"

echo "[test] argus-bootstrap tests passed"
