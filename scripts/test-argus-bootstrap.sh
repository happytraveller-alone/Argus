#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_SRC="$ROOT_DIR/argus-bootstrap.sh"
SHUTDOWN_SRC="$ROOT_DIR/argus-shutdown.sh"
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

install_fake_curl_for_shutdown() {
  local dir="$1"
  local bin_dir="$dir/fake-bin"
  mkdir -p "$bin_dir"
  cat > "$bin_dir/curl" <<'FAKECURL'
#!/usr/bin/env bash
set -euo pipefail
method="GET"
url=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -X) method="$2"; shift 2 ;;
    -H) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
printf '%s %s\n' "$method" "$url" >> "${FAKE_CURL_LOG:?}"
case "$url" in
  */health) printf '{"status":"ok"}\n' ;;
  */api/v1/static-tasks/tasks\?status=running) printf '[{"id":"opengrep-running"}]\n' ;;
  */api/v1/static-tasks/codeql/tasks\?status=running) printf '[{"task_id":"codeql-running"}]\n' ;;
  */api/v1/static-tasks/joern/tasks\?status=running) printf '[{"taskId":"joern-running"}]\n' ;;
  */api/v1/intelligent-tasks\?limit=200) printf '[{"taskId":"intel-pending","status":"pending"},{"taskId":"intel-running","status":"running"}]\n' ;;
  */interrupt|*/cancel) printf '{"status":"cancelled"}\n' ;;
  *) printf '{}\n' ;;
esac
FAKECURL
  chmod +x "$bin_dir/curl"
  printf '%s' "$bin_dir"
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

assert_source_order() {
  local file="$1" first="$2" second="$3"
  local first_line second_line
  first_line="$(line_no "$file" "$first")"
  second_line="$(line_no "$file" "$second")"
  [[ "$first_line" -lt "$second_line" ]] || fail "Expected $first to appear before $second in $file"
}

new_fixture() {
  local name="$1"
  local dir="$TMP_ROOT/$name"
  mkdir -p "$dir/scripts"
  cp "$SCRIPT_SRC" "$dir/argus-bootstrap.sh"
  cp "$SHUTDOWN_SRC" "$dir/argus-shutdown.sh"
  cp "$VALIDATOR_SRC" "$dir/scripts/validate-llm-config.sh"
  cp "$ROOT_DIR/env.example" "$dir/env.example"
  cp "$ROOT_DIR/llm.env.example" "$dir/llm.env.example"
  chmod +x "$dir/argus-bootstrap.sh"
  chmod +x "$dir/argus-shutdown.sh"
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
      - path: "${ARGUS_LLM_ENV_FILE:-./.argus-llm.env}"
        required: true
    environment:
      ARGUS_RESET_IMPORT_TOKEN: "${ARGUS_RESET_IMPORT_TOKEN:-}"
    ports:
      - "${Argus_BACKEND_PORT:-18000}:8000"
    volumes:
      - backend_uploads:/app/uploads
      - backend_runtime_data:/app/data/runtime
      - scan_workspace:/tmp/Argus/scans
    devices:
      - /dev/kvm:/dev/kvm
      - /dev/vhost-vsock:/dev/vhost-vsock
      - /dev/net/tun:/dev/net/tun
    group_add:
      - "${ARGUS_KVM_GROUP_ID:-109}"
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
  mkdir -p "$dir/docker"
  cat > "$dir/docker/backend.Dockerfile" <<'DOCKERFILE'
FROM scratch
RUN --mount=type=cache,target=/tmp/cache echo backend
DOCKERFILE
  cat > "$dir/docker/frontend.Dockerfile" <<'DOCKERFILE'
FROM scratch AS dev
RUN --mount=type=cache,target=/tmp/cache echo frontend
DOCKERFILE
  cat > "$dir/docker/opengrep-runner.Dockerfile" <<'DOCKERFILE'
FROM scratch AS opengrep-runner
RUN --mount=type=cache,target=/tmp/cache echo opengrep
DOCKERFILE
  printf '%s' "$dir"
}

write_valid_config() {
  local dir="$1"
  cat > "$dir/.env" <<'ENV'
SECRET_KEY=local_test_secret_0123456789abcdef
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=11520
DOCKER_SOCKET_PATH=/var/run/docker.sock
ENV
  cat > "$dir/.argus-llm.env" <<'ENV'
LLM_PROVIDER=openai_compatible
LLM_API_KEY=SECRET_SENTINEL_SHOULD_NOT_PRINT
LLM_MODEL=gpt-5
LLM_BASE_URL=https://api.openai.com/v1
LLM_TIMEOUT=150
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=4096
AGENT_TIMEOUT=1800
ENV
}

# Help documents the new operator contract and author/commercial notice.
help_dir="$(new_fixture help)"
help_out="$help_dir/help.out"
( cd "$help_dir" && ./argus-bootstrap.sh --help ) >"$help_out" 2>&1
assert_banner_contact "$help_out"
assert_contains "$help_out" "./argus-bootstrap.sh [--runtime docker|podman] [--dry-run] [--wait-exit] [--sequential-build] [--help] -- <mode>"
assert_contains "$help_out" "Run modes:"
assert_contains "$help_out" "default"
assert_contains "$help_out" "keep-cache"
assert_contains "$help_out" "aggressive"
assert_contains "$help_out" "Compatible with both bash and zsh"
assert_contains "$help_out" "Start modes:"
assert_contains "$help_out" "llm.env.example"
assert_contains "$help_out" ".env"
assert_contains "$help_out" "docker system prune -af --volumes"
assert_contains "$help_out" "docker compose up -d --build"
assert_contains "$help_out" "--wait-exit"
assert_contains "$help_out" "--runtime docker|podman"
assert_contains "$help_out" "rootless"
assert_contains "$help_out" "Podman with no host Docker socket"
assert_contains "$help_out" "ARGUS_STUB_DOCKER=true"
assert_contains "$help_out" "scripts/validate-llm-config.sh --env-file"

# Podman pre-pulls the Joern scanner image with build base images, and normal
# readiness polling suppresses transient curl stderr while retaining dry-run
# command visibility through the stub/dry-run branches.
assert_contains "$SCRIPT_SRC" 'log "Pre-pulling base/scanner images in parallel..."'
assert_contains "$SCRIPT_SRC" 'log "Dry-run/stub: skipping base/scanner image pre-pull."'
assert_contains "$SCRIPT_SRC" 'joern_image="$(joern_runner_image_ref)"'
assert_contains "$SCRIPT_SRC" '"$joern_image"'
assert_contains "$SCRIPT_SRC" 'curl -fsS "$BACKEND_HEALTH_URL" >/dev/null 2>&1'
assert_contains "$SCRIPT_SRC" 'curl -fsS "$url" >/dev/null 2>&1'
assert_source_order "$SCRIPT_SRC" 'joern_image="$(joern_runner_image_ref)"' 'podman pull "$img"'
assert_source_order "$SCRIPT_SRC" 'podman_prepull_base_images' 'local build_funcs=("podman_build_opengrep_runner_image"'

backend_wait_suppression_out="$help_dir/backend-wait-suppression.out"
set +e
(
  cd "$ROOT_DIR"
  # shellcheck disable=SC1090
  source <(sed '$d' "$SCRIPT_SRC")
  DRY_RUN=false
  STUB_DOCKER=false
  WAIT_TIMEOUT=0
  WAIT_INTERVAL=0
  BACKEND_HEALTH_URL="http://127.0.0.1:18000/health"
  curl() {
    echo "curl: (7) Failed to connect to 127.0.0.1 port 18000" >&2
    return 7
  }
  wait_for_backend
) >"$backend_wait_suppression_out" 2>&1
backend_wait_suppression_rc=$?
set -e
[[ "$backend_wait_suppression_rc" -ne 0 ]] || fail "Backend wait should fail on timeout when curl never succeeds"
assert_contains "$backend_wait_suppression_out" "Backend did not become reachable within"
assert_not_contains "$backend_wait_suppression_out" "curl: (7)"

backend_wait_retry_out="$help_dir/backend-wait-retry.out"
(
  cd "$ROOT_DIR"
  # shellcheck disable=SC1090
  source <(sed '$d' "$SCRIPT_SRC")
  DRY_RUN=false
  STUB_DOCKER=false
  WAIT_TIMEOUT=2
  WAIT_INTERVAL=0
  BACKEND_HEALTH_URL="http://127.0.0.1:18000/health"
  attempts=0
  curl() {
    attempts=$((attempts + 1))
    if [[ "$attempts" -lt 2 ]]; then
      echo "curl: (7) Failed to connect to 127.0.0.1 port 18000" >&2
      return 7
    fi
    return 0
  }
  wait_for_backend
) >"$backend_wait_retry_out" 2>&1
assert_contains "$backend_wait_retry_out" "Backend is reachable: http://127.0.0.1:18000/health"
assert_not_contains "$backend_wait_retry_out" "curl: (7)"

shutdown_help_out="$help_dir/shutdown-help.out"
( cd "$help_dir" && ./argus-shutdown.sh --help ) >"$shutdown_help_out" 2>&1
assert_contains "$shutdown_help_out" "--runtime docker|podman"

# Standalone validator accepts valid LLM env and rejects missing/placeholder values.
validator_dir="$(new_fixture validator)"
write_valid_config "$validator_dir"
validator_out="$validator_dir/validator.out"
( cd "$validator_dir" && ./scripts/validate-llm-config.sh --env-file ./.argus-llm.env ) >"$validator_out" 2>&1
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
( cd "$extra_dir" && ./argus-bootstrap.sh --runtime docker -- default extra ) >"$extra_out" 2>&1
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

invalid_runtime_dir="$(new_fixture invalid-runtime)"
write_valid_config "$invalid_runtime_dir"
invalid_runtime_out="$invalid_runtime_dir/invalid-runtime.out"
set +e
( cd "$invalid_runtime_dir" && ARGUS_STUB_DOCKER=true ./argus-bootstrap.sh --runtime banana -- default ) >"$invalid_runtime_out" 2>&1
invalid_runtime_rc=$?
set -e
[[ "$invalid_runtime_rc" -ne 0 ]] || fail "Unknown runtime should fail"
assert_contains "$invalid_runtime_out" "Unknown container runtime: banana"
assert_not_contains "$invalid_runtime_out" "docker compose"
assert_not_contains "$invalid_runtime_out" "podman build"

# No runtime flag is now the recommended Podman path; Docker fallback must be
# explicit via `--runtime docker`.
default_podman_dir="$(new_fixture default-podman)"
write_valid_config "$default_podman_dir"
default_podman_out="$default_podman_dir/default-podman.out"
( cd "$default_podman_dir" && ./argus-bootstrap.sh --dry-run --wait-exit -- default ) >"$default_podman_out" 2>&1
assert_contains "$default_podman_out" "Container runtime: podman"
assert_contains "$default_podman_out" "podman build --file $default_podman_dir/docker/opengrep-runner.Dockerfile --target opengrep-runner"
assert_contains "$default_podman_out" "--http-proxy=false"
[[ "$(grep -o -- '--http-proxy=false' "$default_podman_out" | wc -l | tr -d ' ')" -eq 5 ]] || fail "Expected every Podman image build to disable proxy injection"
assert_contains "$default_podman_out" "OPENGREP_RUNNER_RUNTIME=podman"
assert_contains "$default_podman_out" "Ensuring Joern scanner image container starts (Podman mode): ghcr.nju.edu.cn/joernio/joern:nightly"
assert_contains "$default_podman_out" "podman run --rm --network none ghcr.nju.edu.cn/joernio/joern:nightly"
assert_not_contains "$default_podman_out" "docker compose"
assert_not_contains "$default_podman_out" "/var/run/docker.sock"

legacy_joern_dir="$(new_fixture legacy-joern-image)"
write_valid_config "$legacy_joern_dir"
legacy_ghcr_registry="ghcr."
legacy_ghcr_registry="${legacy_ghcr_registry}io"
legacy_joern_image="${legacy_ghcr_registry}/joernio/joern:nightly"
printf '\nSCANNER_JOERN_IMAGE=%s\n' "$legacy_joern_image" >> "$legacy_joern_dir/.env"
legacy_joern_out="$legacy_joern_dir/legacy-joern.out"
( cd "$legacy_joern_dir" && ./argus-bootstrap.sh --dry-run --wait-exit -- default ) >"$legacy_joern_out" 2>&1
assert_contains "$legacy_joern_out" "Normalized SCANNER_JOERN_IMAGE=ghcr.nju.edu.cn/joernio/joern:nightly"
assert_contains "$legacy_joern_out" "Ensuring Joern scanner image container starts (Podman mode): ghcr.nju.edu.cn/joernio/joern:nightly"
assert_not_contains "$legacy_joern_out" "$legacy_joern_image"
assert_contains "$legacy_joern_dir/.env" "SCANNER_JOERN_IMAGE=ghcr.nju.edu.cn/joernio/joern:nightly"
assert_not_contains "$legacy_joern_dir/.env" "SCANNER_JOERN_IMAGE=$legacy_joern_image"

# Missing env exits before Docker cleanup after creating runtime and LLM templates.
missing_dir="$(new_fixture missing)"
missing_out="$missing_dir/missing.out"
set +e
( cd "$missing_dir" && CI=true ARGUS_STUB_DOCKER=true ./argus-bootstrap.sh ) >"$missing_out" 2>&1
missing_rc=$?
set -e
[[ "$missing_rc" -ne 0 ]] || fail "Missing env should stop bootstrap after creating template"
assert_contains "$missing_out" "Created runtime .env"
assert_contains "$missing_out" "Created dedicated LLM env from llm.env.example"
assert_contains "$missing_out" "Generated SECRET_KEY in root .env"
assert_contains "$missing_out" "scripts/validate-llm-config.sh --env-file ./.argus-llm.env"
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
ENV
cat > "$missing_secret_dir/.argus-llm.env" <<'ENV'
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-your-api-key
LLM_MODEL=gpt-5
LLM_BASE_URL=https://api.openai.com/v1
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
ENV
cat > "$placeholder_secret_dir/.argus-llm.env" <<'ENV'
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-your-api-key
LLM_MODEL=gpt-5
LLM_BASE_URL=https://api.openai.com/v1
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
( cd "$preserve_secret_dir" && ARGUS_STUB_DOCKER=true ARGUS_TEST_IMPORT_TOKEN=IMPORT_TOKEN_SHOULD_NOT_PRINT ./argus-bootstrap.sh --runtime docker --wait-exit -- default ) >"$preserve_secret_out" 2>&1
after_secret="$(grep '^SECRET_KEY=' "$preserve_secret_dir/.env" | cut -d= -f2-)"
[[ "$before_secret" == "$after_secret" ]] || fail "Existing real SECRET_KEY should not be regenerated on every bootstrap"
assert_not_contains "$preserve_secret_out" "Generated SECRET_KEY in root .env"

# Placeholder config exits before Docker cleanup in non-interactive mode.
placeholder_dir="$(new_fixture placeholder)"
cat > "$placeholder_dir/.env" <<'ENV'
SECRET_KEY=local_test_secret_0123456789abcdef
DOCKER_SOCKET_PATH=/var/run/docker.sock
ENV
cat > "$placeholder_dir/.argus-llm.env" <<'ENV'
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-your-api-key
LLM_MODEL=gpt-5
LLM_BASE_URL=https://api.openai.com/v1
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
grep -v '^LLM_MODEL=' "$missing_key_dir/.argus-llm.env" > "$missing_key_dir/.argus-llm.env.tmp"
mv "$missing_key_dir/.argus-llm.env.tmp" "$missing_key_dir/.argus-llm.env"
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
( cd "$valid_dir" && ARGUS_STUB_DOCKER=true ARGUS_TEST_IMPORT_TOKEN=IMPORT_TOKEN_SHOULD_NOT_PRINT ./argus-bootstrap.sh --runtime docker ) >"$valid_out" 2>&1
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
assert_contains "$valid_out" "ARGUS_LLM_ENV_FILE=$valid_dir/.argus-llm.env"
assert_contains "$valid_out" "ARGUS_RESET_IMPORT_TOKEN="
assert_contains "$valid_out" "redacted-import-token"
assert_contains "$valid_out" "curl -fsS http://127.0.0.1:18000/health"
assert_contains "$valid_out" "Ensuring backend Podman can start Joern image: ghcr.nju.edu.cn/joernio/joern:nightly"
assert_contains "$valid_out" 'podman image inspect "$image"'
assert_contains "$valid_out" 'podman pull "$image"'
assert_contains "$valid_out" 'podman run --rm --network none "$image"'
assert_contains "$valid_out" "joern-parse"
assert_not_contains "$valid_out" "A3S Box cache"
assert_not_contains "$valid_out" "a3s-box load -i"
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
joern_image_line="$(line_no "$valid_out" "Ensuring backend Podman can start Joern image")"
import_line="$(line_no "$valid_out" "curl -fsS -X POST")"
logs_line="$(line_no "$valid_out" "logs -f")"
[[ "$banner_line" -lt "$validation_line" && "$validation_line" -lt "$down_line" && "$down_line" -lt "$runner_build_line" && "$runner_build_line" -lt "$up_line" && "$up_line" -lt "$backend_wait_line" && "$backend_wait_line" -lt "$joern_image_line" && "$joern_image_line" -lt "$import_line" && "$import_line" -lt "$logs_line" ]] || fail "Expected banner -> validation -> down -> runner image build -> detached up -> backend readiness -> Joern image startup -> import -> logs order"

podman_word="podman"
podman_compose_cmd="${podman_word} compose"
podman_volume_rm_cmd="${podman_word} volume rm"
podman_image_rm_cmd="${podman_word} image rm"
podman_rmi_cmd="${podman_word} rmi"
podman_prune_cmd="${podman_word} system prune"
podman_rm_volume_flag_cmd="${podman_word} rm -v"

# Podman runtime is explicit, builds local images, runs exact Argus containers, and does not use Compose/destructive cleanup.
podman_dir="$(new_fixture podman)"
write_valid_config "$podman_dir"
podman_out="$podman_dir/podman.out"
( cd "$podman_dir" && ./argus-bootstrap.sh --runtime podman --dry-run --wait-exit -- default ) >"$podman_out" 2>&1
assert_contains "$podman_out" "Container runtime: podman"
assert_contains "$podman_out" "podman build --file $podman_dir/docker/opengrep-runner.Dockerfile --target opengrep-runner"
assert_contains "$podman_out" "--http-proxy=false"
[[ "$(grep -o -- '--http-proxy=false' "$podman_out" | wc -l | tr -d ' ')" -eq 5 ]] || fail "Expected every Podman image build to disable proxy injection"
assert_contains "$podman_out" "--tag argus/opengrep-runner-local:latest"
assert_contains "$podman_out" "podman build --file $podman_dir/docker/backend.Dockerfile --target runtime-plain"
assert_contains "$podman_out" "--platform linux/amd64"
assert_not_contains "$podman_out" "--build-arg UV_IMAGE="
assert_not_contains "$podman_out" "--build-arg DOCKER_CLI_IMAGE="
assert_contains "$podman_out" "--tag argus/backend-local:latest"
assert_contains "$podman_out" "podman build --file $podman_dir/docker/frontend.Dockerfile --target dev"
assert_not_contains "$podman_out" "--build-arg PNPM_VERSION="
assert_not_contains "$podman_out" "--build-arg NPM_REGISTRY="
assert_not_contains "$podman_out" "--build-arg WEAK_NETWORK="
assert_contains "$podman_out" "--tag argus/frontend-local:latest"
assert_contains "$podman_out" "podman run -d --name argus-db"
assert_contains "$podman_out" "podman run -d --name argus-redis"
assert_contains "$podman_out" "podman run -d --name argus-backend"
assert_contains "$podman_out" "podman run -d --name argus-frontend"
assert_contains "$podman_out" "--label io.argus.project=argus"
assert_contains "$podman_out" "--label io.argus.runtime=podman"
assert_contains "$podman_out" "--env-file $podman_dir/.argus-llm.env"
assert_contains "$podman_out" "BIND_ADDR=0.0.0.0:18000"
assert_contains "$podman_out" "OPENGREP_RUNNER_RUNTIME=podman"
assert_contains "$podman_out" "Argus_PODMAN_BIN=podman"
assert_contains "$podman_out" "CONTAINER_HOST=unix:///run/podman/podman.sock"
assert_contains "$podman_out" "CONTAINER_CLI=podman"
assert_contains "$podman_out" "RUNNER_PREFLIGHT_STRICT=false"
assert_contains "$podman_out" "SCANNER_JOERN_IMAGE=ghcr.nju.edu.cn/joernio/joern:nightly"
assert_contains "$podman_out" "Ensuring Joern scanner image container starts (Podman mode): ghcr.nju.edu.cn/joernio/joern:nightly"
assert_contains "$podman_out" "podman image inspect ghcr.nju.edu.cn/joernio/joern:nightly"
assert_contains "$podman_out" "podman pull ghcr.nju.edu.cn/joernio/joern:nightly"
assert_contains "$podman_out" "podman run --rm --network none ghcr.nju.edu.cn/joernio/joern:nightly"
assert_contains "$podman_out" "joern-parse"
assert_contains "$podman_out" "/run/user/"
assert_contains "$podman_out" "/podman/podman.sock:/run/podman/podman.sock"
assert_contains "$podman_out" "argus_scan_workspace"
assert_contains "$podman_out" "VITE_API_TARGET=http://127.0.0.1:18000"
assert_contains "$podman_out" "FRONTEND_NPM_REGISTRY=https://registry.npmmirror.com"
assert_contains "$podman_out" "PNPM_VERSION=10.11.0"
assert_contains "$podman_out" "FRONTEND_DEV_PORT=13000"
assert_contains "$podman_out" "curl -fsS http://127.0.0.1:18000/health"
assert_contains "$podman_out" "curl -fsS http://127.0.0.1:13000"
podman_joern_line="$(line_no "$podman_out" "Ensuring Joern scanner image container starts (Podman mode)")"
podman_db_line="$(line_no "$podman_out" "podman run -d --name argus-db")"
podman_redis_line="$(line_no "$podman_out" "podman run -d --name argus-redis")"
podman_backend_line="$(line_no "$podman_out" "podman run -d --name argus-backend")"
podman_backend_wait_line="$(line_no "$podman_out" "curl -fsS http://127.0.0.1:18000/health")"
podman_frontend_line="$(line_no "$podman_out" "podman run -d --name argus-frontend")"
podman_frontend_wait_line="$(line_no "$podman_out" "curl -fsS http://127.0.0.1:13000")"
[[ "$podman_joern_line" -lt "$podman_db_line" \
  && "$podman_db_line" -lt "$podman_redis_line" \
  && "$podman_redis_line" -lt "$podman_backend_line" \
  && "$podman_backend_line" -lt "$podman_backend_wait_line" \
  && "$podman_backend_wait_line" -lt "$podman_frontend_line" \
  && "$podman_frontend_line" -lt "$podman_frontend_wait_line" ]] \
  || fail "Expected Podman order: Joern image ready -> db/redis/backend -> backend readiness -> frontend -> frontend readiness"
assert_not_contains "$podman_out" "docker compose"
assert_not_contains "$podman_out" "$podman_compose_cmd"
assert_not_contains "$podman_out" "$podman_volume_rm_cmd"
assert_not_contains "$podman_out" "$podman_image_rm_cmd"
assert_not_contains "$podman_out" "$podman_rmi_cmd"
assert_not_contains "$podman_out" "$podman_prune_cmd"
assert_not_contains "$podman_out" "podman image prune"
assert_not_contains "$podman_out" "$podman_rm_volume_flag_cmd"
assert_not_contains "$podman_out" "/var/run/docker.sock"
assert_not_contains "$ROOT_DIR/argus-bootstrap.sh" "podman save --format oci-archive"
assert_contains "$ROOT_DIR/argus-bootstrap.sh" "podman_cleanup_after_successful_build"
assert_not_contains "$ROOT_DIR/argus-bootstrap.sh" "podman image prune"

podman_separate_images_dir="$(new_fixture podman-separate-images)"
write_valid_config "$podman_separate_images_dir"
printf '\nSCANNER_OPENGREP_IMAGE=argus/opengrep-default:test\nSCANNER_OPENGREP_A3S_BOX_IMAGE=argus/opengrep-a3s:test\n' >> "$podman_separate_images_dir/.env"
podman_separate_images_out="$podman_separate_images_dir/podman-separate-images.out"
( cd "$podman_separate_images_dir" && ./argus-bootstrap.sh --runtime podman --dry-run --wait-exit -- default ) >"$podman_separate_images_out" 2>&1
assert_contains "$podman_separate_images_out" "--tag argus/opengrep-default:test"
assert_not_contains "$podman_separate_images_out" "--tag argus/opengrep-a3s:test"

podman_docker_socket_dir="$(new_fixture podman-docker-socket)"
write_valid_config "$podman_docker_socket_dir"
podman_docker_socket_out="$podman_docker_socket_dir/podman-docker-socket.out"
set +e
( cd "$podman_docker_socket_dir" && CONTAINER_HOST=unix:///var/run/docker.sock ./argus-bootstrap.sh --runtime podman --dry-run -- default ) >"$podman_docker_socket_out" 2>&1
podman_docker_socket_rc=$?
set -e
[[ "$podman_docker_socket_rc" -ne 0 ]] || fail "Podman runtime must reject Docker socket CONTAINER_HOST"
assert_contains "$podman_docker_socket_out" "Podman runtime must not use Docker socket path"
assert_not_contains "$podman_docker_socket_out" "podman build"

podman_prepare_dir="$(mktemp -d "$TMP_ROOT/podman-dockerfile.XXXXXX")"
(
  cd "$ROOT_DIR"
  repo_root="$ROOT_DIR"
  # Load helper definitions without executing main so the Podman compatibility
  # rewrite is covered even when dry-run keeps the original Dockerfile path.
  # shellcheck disable=SC1090
  source <(sed '$d' "$ROOT_DIR/argus-bootstrap.sh")
  prepare_podman_dockerfile "$repo_root/docker/backend.Dockerfile" "$podman_prepare_dir/backend.Dockerfile"
  prepare_podman_dockerfile "$repo_root/docker/frontend.Dockerfile" "$podman_prepare_dir/frontend.Dockerfile"
)
assert_not_contains "$podman_prepare_dir/backend.Dockerfile" "--mount=type=cache"
assert_not_contains "$podman_prepare_dir/frontend.Dockerfile" "--mount=type=cache"
assert_contains "$podman_prepare_dir/backend.Dockerfile" "RUN set -eux;"
assert_contains "$podman_prepare_dir/backend.Dockerfile" "RUN CARGO_HTTP_TIMEOUT="
assert_contains "$podman_prepare_dir/frontend.Dockerfile" "RUN set -eux;"
assert_contains "$podman_prepare_dir/frontend.Dockerfile" "RUN VITE_CACHE_DIR=/tmp/vite-build-cache"

podman_shutdown_out="$podman_dir/podman-shutdown.out"
( cd "$podman_dir" && ./argus-shutdown.sh --runtime podman --dry-run --full ) >"$podman_shutdown_out" 2>&1
assert_contains "$podman_shutdown_out" "runtime=podman"
assert_contains "$podman_shutdown_out" "Mode=full under Podman: preserving Podman volumes and images"
for podman_container in argus-frontend argus-backend argus-redis argus-db; do
  assert_contains "$podman_shutdown_out" "podman stop $podman_container"
  assert_contains "$podman_shutdown_out" "podman rm -f $podman_container"
done
assert_not_contains "$podman_shutdown_out" "argus-*"
assert_not_contains "$podman_shutdown_out" "$podman_compose_cmd"
assert_not_contains "$podman_shutdown_out" "$podman_volume_rm_cmd"
assert_not_contains "$podman_shutdown_out" "$podman_image_rm_cmd"
assert_not_contains "$podman_shutdown_out" "$podman_rmi_cmd"
assert_not_contains "$podman_shutdown_out" "$podman_prune_cmd"
assert_not_contains "$podman_shutdown_out" "$podman_rm_volume_flag_cmd"

shutdown_fake_dir="$(new_fixture shutdown-fake-curl)"
write_valid_config "$shutdown_fake_dir"
shutdown_fake_bin="$(install_fake_curl_for_shutdown "$shutdown_fake_dir")"
shutdown_fake_log="$shutdown_fake_dir/fake-curl.log"
shutdown_fake_out="$shutdown_fake_dir/shutdown-fake.out"
( cd "$shutdown_fake_dir" && PATH="$shutdown_fake_bin:$PATH" FAKE_CURL_LOG="$shutdown_fake_log" ./argus-shutdown.sh --runtime docker --dry-run --hard ) >"$shutdown_fake_out" 2>&1
assert_contains "$shutdown_fake_out" "Step 1: Force-cancel all running scans"
assert_contains "$shutdown_fake_out" "Force-cancelling opengrep scan task: opengrep-running"
assert_contains "$shutdown_fake_out" "Force-cancelling codeql scan task: codeql-running"
assert_contains "$shutdown_fake_out" "Force-cancelling joern scan task: joern-running"
assert_contains "$shutdown_fake_out" "Force-cancelling intelligent scan task: intel-running"
assert_contains "$shutdown_fake_out" "POST /api/v1/static-tasks/tasks/opengrep-running/interrupt"
assert_contains "$shutdown_fake_out" "POST /api/v1/static-tasks/codeql/tasks/codeql-running/interrupt"
assert_contains "$shutdown_fake_out" "POST /api/v1/static-tasks/joern/tasks/joern-running/interrupt"
assert_contains "$shutdown_fake_out" "POST /api/v1/intelligent-tasks/intel-running/cancel"
assert_contains "$shutdown_fake_log" "GET http://127.0.0.1:18000/api/v1/static-tasks/joern/tasks?status=running"
assert_contains "$shutdown_fake_log" "GET http://127.0.0.1:18000/api/v1/intelligent-tasks?limit=200"

# Explicit default matches no-mode safety, even when legacy prune env is true.
default_dir="$(new_fixture explicit-default)"
write_valid_config "$default_dir"
default_out="$default_dir/default.out"
( cd "$default_dir" && ARGUS_STUB_DOCKER=true ARGUS_DOCKER_SYSTEM_PRUNE=true ./argus-bootstrap.sh --runtime docker -- default ) >"$default_out" 2>&1
assert_contains "$default_out" "Run mode: default"
assert_contains "$default_out" "down --remove-orphans"
assert_not_contains "$default_out" "down --volumes --remove-orphans"
assert_no_global_prune_execution "$default_out"

# keep-cache deletes this Compose project's managed volumes, but never executes global image/build cache prune.
keep_cache_dir="$(new_fixture keep-cache)"
write_valid_config "$keep_cache_dir"
keep_cache_out="$keep_cache_dir/keep-cache.out"
( cd "$keep_cache_dir" && ARGUS_STUB_DOCKER=true ARGUS_DOCKER_SYSTEM_PRUNE=true ./argus-bootstrap.sh --runtime docker -- keep-cache ) >"$keep_cache_out" 2>&1
assert_contains "$keep_cache_out" "Run mode: keep-cache"
assert_contains "$keep_cache_out" "removing this Compose project's managed volumes"
assert_contains "$keep_cache_out" "preserving Docker image/build cache"
assert_contains "$keep_cache_out" "down --volumes --remove-orphans"
assert_no_global_prune_execution "$keep_cache_out"

# aggressive mode explicitly permits destructive Compose volume cleanup and global system prune.
aggressive_dir="$(new_fixture aggressive)"
write_valid_config "$aggressive_dir"
aggressive_out="$aggressive_dir/aggressive.out"
( cd "$aggressive_dir" && ARGUS_STUB_DOCKER=true ./argus-bootstrap.sh --runtime docker -- aggressive ) >"$aggressive_out" 2>&1
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
( cd "$aggressive_skip_dir" && ARGUS_STUB_DOCKER=true ARGUS_DOCKER_SYSTEM_PRUNE=false ./argus-bootstrap.sh --runtime docker -- aggressive ) >"$aggressive_skip_out" 2>&1
assert_contains "$aggressive_skip_out" "Run mode: aggressive"
assert_contains "$aggressive_skip_out" "down --volumes --remove-orphans"
assert_contains "$aggressive_skip_out" "Skipping global Docker prune because ARGUS_DOCKER_SYSTEM_PRUNE=false"
assert_no_global_prune_execution "$aggressive_skip_out"

# Wait-exit honors configured frontend port and exits after stubbed readiness with modes.
wait_dir="$(new_fixture wait)"
write_valid_config "$wait_dir"
wait_out="$wait_dir/wait.out"
( cd "$wait_dir" && ARGUS_STUB_DOCKER=true Argus_FRONTEND_PORT=13099 ./argus-bootstrap.sh --runtime docker --wait-exit -- default ) >"$wait_out" 2>&1
assert_contains "$wait_out" "build opengrep-runner"
assert_not_contains "$wait_out" "build opengrep-runner codeql-runner"
assert_contains "$wait_out" "up -d --build"
assert_contains "$wait_out" "curl -fsS http://127.0.0.1:18000/health"
assert_contains "$wait_out" "Ensuring backend Podman can start Joern image: ghcr.nju.edu.cn/joernio/joern:nightly"
assert_not_contains "$wait_out" "A3S Box cache"
assert_contains "$wait_out" "curl -fsS -X POST"
assert_contains "$wait_out" "curl -fsS http://127.0.0.1:13099"
assert_contains "$wait_out" "Complete. Frontend: http://127.0.0.1:13099"
assert_no_global_prune_execution "$wait_out"

# Sanitized HTTP 200 import-test failure exits before reporting frontend readiness.
import_failure_dir="$(new_fixture import-failure)"
write_valid_config "$import_failure_dir"
import_failure_out="$import_failure_dir/import-failure.out"
set +e
( cd "$import_failure_dir" && ARGUS_STUB_DOCKER=true ARGUS_TEST_IMPORT_RESPONSE='{"success":false,"message":"mock failure","reasonCode":"llm_test_failed"}' ./argus-bootstrap.sh --runtime docker --wait-exit -- default ) >"$import_failure_out" 2>&1
import_failure_rc=$?
set -e
[[ "$import_failure_rc" -ne 0 ]] || fail "Import/test failure should stop bootstrap"
assert_contains "$import_failure_out" '"success":false'
assert_contains "$import_failure_out" "backend LLM env import/test returned failure"
assert_not_contains "$import_failure_out" "Complete. Frontend: http://127.0.0.1:13000"

wait_aggressive_dir="$(new_fixture wait-aggressive)"
write_valid_config "$wait_aggressive_dir"
wait_aggressive_out="$wait_aggressive_dir/wait-aggressive.out"
( cd "$wait_aggressive_dir" && ARGUS_STUB_DOCKER=true Argus_FRONTEND_PORT=13100 ./argus-bootstrap.sh --runtime docker --wait-exit -- aggressive ) >"$wait_aggressive_out" 2>&1
assert_contains "$wait_aggressive_out" "Run mode: aggressive"
assert_contains "$wait_aggressive_out" "down --volumes --remove-orphans"
assert_contains "$wait_aggressive_out" "[stub] docker system prune -af --volumes"
assert_contains "$wait_aggressive_out" "build opengrep-runner"
assert_not_contains "$wait_aggressive_out" "build opengrep-runner codeql-runner"
assert_contains "$wait_aggressive_out" "up -d --build"
assert_contains "$wait_aggressive_out" "curl -fsS http://127.0.0.1:18000/health"
assert_contains "$wait_aggressive_out" "Ensuring backend Podman can start Joern image: ghcr.nju.edu.cn/joernio/joern:nightly"
assert_not_contains "$wait_aggressive_out" "A3S Box cache"
assert_contains "$wait_aggressive_out" "curl -fsS -X POST"
assert_contains "$wait_aggressive_out" "curl -fsS http://127.0.0.1:13100"
assert_contains "$wait_aggressive_out" "Complete. Frontend: http://127.0.0.1:13100"

# Dry-run keeps backend env non-mutating while showing the safe default command plan and redacted import call.
dry_dir="$(new_fixture dry)"
write_valid_config "$dry_dir"
dry_out="$dry_dir/dry.out"
( cd "$dry_dir" && ./argus-bootstrap.sh --runtime docker --dry-run -- default ) >"$dry_out" 2>&1
assert_not_contains "$dry_out" "[dry-run] cp"
assert_contains "$dry_out" "[dry-run] docker compose"
assert_contains "$dry_out" "[dry-run] curl -fsS -X POST"
assert_contains "$dry_out" "redacted-import-token"
assert_no_global_prune_execution "$dry_out"

# docker/env is retired; root env.example plus llm.env.example are the only environment template surfaces.
retired_env_out="$TMP_ROOT/docker-env-retired.out"
while IFS= read -r tracked_env_path; do
  if [ -e "$ROOT_DIR/$tracked_env_path" ]; then
    echo "$tracked_env_path" >&2
    fail "docker/env should not contain tracked environment templates"
  fi
done < <(git -C "$ROOT_DIR" ls-files docker/env)
if rg -n "docker/env|(^|[^[:alnum:]_-])\\.env\\.example" \
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
empty_compose_env="$TMP_ROOT/empty-compose.env"
cat >"$empty_compose_env" <<ENV
ARGUS_ENV_FILE=$TMP_ROOT/compose-root.env
ARGUS_LLM_ENV_FILE=$TMP_ROOT/compose-llm.env
ENV
: >"$TMP_ROOT/compose-root.env"
: >"$TMP_ROOT/compose-llm.env"
docker compose --env-file "$empty_compose_env" --project-directory "$ROOT_DIR" --file "$ROOT_DIR/docker-compose.yml" config >"$compose_render_out"
runner_profile_count="$(grep -F -c 'profiles: [ "runner-build" ]' "$ROOT_DIR/docker-compose.yml" || true)"
[[ "$runner_profile_count" -eq 1 ]] || fail "only opengrep runner service should be a profile-only image build target"
assert_contains "$ROOT_DIR/docker-compose.yml" "\"host.docker.internal:host-gateway\""
assert_contains "$ROOT_DIR/env.example" "VITE_API_TARGET=http://host.docker.internal:18000"
assert_contains "$ROOT_DIR/llm.env.example" "LLM_PROVIDER=openai_compatible"
assert_not_contains "$ROOT_DIR/env.example" "VITE_API_TARGET=http://backend:8000"
assert_contains "$ROOT_DIR/frontend/vite.config.ts" "http://127.0.0.1:18000"
assert_contains "$compose_render_out" "VITE_API_TARGET: http://host.docker.internal:18000"
assert_not_contains "$compose_render_out" "VITE_API_TARGET: http://backend:8000"
assert_contains "$compose_render_out" "FRONTEND_NPM_REGISTRY: https://registry.npmmirror.com"
assert_contains "$compose_render_out" "PNPM_VERSION: 10.11.0"
assert_not_contains "$compose_render_out" "UV_IMAGE:"
if grep -Eq '^[[:space:]]+NPM_REGISTRY:' "$compose_render_out"; then
  fail "compose backend/frontend build args must not include retired NPM_REGISTRY"
fi
if grep -Eq '^[[:space:]]+WEAK_NETWORK:' "$compose_render_out"; then
  fail "compose backend/frontend build args must not include retired WEAK_NETWORK"
fi
if awk '
  /^  frontend:/ { in_frontend = 1; in_build = 0; in_args = 0; next }
  /^  [a-zA-Z0-9_-]+:/ { in_frontend = 0; in_build = 0; in_args = 0 }
  in_frontend && /^    build:/ { in_build = 1; next }
  in_frontend && in_build && /^    [a-zA-Z0-9_-]+:/ && $1 != "build:" { in_build = 0; in_args = 0 }
  in_frontend && in_build && /^      args:/ { in_args = 1; next }
  in_frontend && in_args && /^      [a-zA-Z0-9_-]+:/ && $1 != "args:" { in_args = 0 }
  in_frontend && in_args && /(PNPM_VERSION|NPM_REGISTRY|WEAK_NETWORK|BUILD_WEAK_NETWORK)/ { found = 1 }
  END { exit found ? 0 : 1 }
' "$compose_render_out"; then
  fail "compose frontend dev build args must not include runtime-only npm/network settings"
fi
retired_sandbox_name="Cube""Sandbox"
retired_sandbox_lower="cube""sandbox"
retired_sandbox_script="${retired_sandbox_lower}-quickstart.sh"
retired_sandbox_env="CUBE""SANDBOX_HELPER_PATH=/app/scripts/${retired_sandbox_script}"
retired_sandbox_copy="COPY --chmod=755 scripts/${retired_sandbox_script} /app/scripts/${retired_sandbox_script}"
assert_contains "$ROOT_DIR/docs/archive/cubesandbox/INDEX.md" "$retired_sandbox_name"
assert_not_contains "$ROOT_DIR/env.example" "$retired_sandbox_env"
assert_not_contains "$ROOT_DIR/docker/backend.Dockerfile" "$retired_sandbox_copy"
assert_contains "$ROOT_DIR/docker/backend.Dockerfile" "openssh-client"
assert_contains "$ROOT_DIR/docker/backend.Dockerfile" "podman"
assert_contains "$ROOT_DIR/docker/backend-entrypoint.sh" "podmansock"
assert_not_contains "$ROOT_DIR/scripts/release-templates/backend.Dockerfile" "$retired_sandbox_copy"
assert_contains "$ROOT_DIR/scripts/release-templates/backend.Dockerfile" "openssh-client"
assert_contains "$ROOT_DIR/scripts/release-templates/backend.Dockerfile" "podman"
assert_contains "$compose_render_out" "source: /dev/kvm"
assert_contains "$compose_render_out" "target: /dev/kvm"
assert_contains "$compose_render_out" "source: /dev/vhost-vsock"
assert_contains "$compose_render_out" "target: /dev/vhost-vsock"
assert_contains "$compose_render_out" "source: /dev/net/tun"
assert_contains "$compose_render_out" "target: /dev/net/tun"
assert_contains "$compose_render_out" "group_add:"
assert_contains "$compose_render_out" "- \"109\""
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
assert_not_contains "$compose_render_out" "SCANNER_CODEQL_COMPILE_SANDBOX_IMAGE"

release_compose_render_out="$TMP_ROOT/release-compose.out"
docker compose \
  --env-file "$empty_compose_env" \
  --project-directory "$ROOT_DIR" \
  --file "$ROOT_DIR/scripts/release-templates/docker-compose.release-slim.yml" \
  config >"$release_compose_render_out"
assert_contains "$release_compose_render_out" "SCANNER_OPENGREP_IMAGE: ghcr.nju.edu.cn/happytraveller-alone/argus-opengrep-runner:latest"
assert_contains "$release_compose_render_out" "source: /dev/kvm"
assert_contains "$release_compose_render_out" "target: /dev/kvm"
assert_contains "$release_compose_render_out" "source: /dev/vhost-vsock"
assert_contains "$release_compose_render_out" "target: /dev/vhost-vsock"
assert_contains "$release_compose_render_out" "source: /dev/net/tun"
assert_contains "$release_compose_render_out" "target: /dev/net/tun"
assert_not_contains "$release_compose_render_out" "codeql-runner"
assert_not_contains "$release_compose_render_out" "SCANNER_CODEQL_IMAGE"
assert_not_contains "$release_compose_render_out" "SCANNER_CODEQL_COMPILE_SANDBOX_IMAGE"
if grep -Eq '^  (opengrep-runner|codeql-runner):$' "$release_compose_render_out"; then
  fail "release compose must not define runner service containers"
fi

assert_not_contains "$ROOT_DIR/.github/workflows/docker-publish.yml" "argus-codeql-runner"
assert_not_contains "$ROOT_DIR/.github/workflows/docker-publish.yml" "docker/codeql-runner.Dockerfile"
for retired_codeql_docker_path in \
  docker/codeql-runner.Dockerfile \
  docker/codeql-scan.sh \
  docker/codeql-compile-sandbox.sh \
  docker/test-codeql-diagnostics.sh
do
  if [ -e "$ROOT_DIR/$retired_codeql_docker_path" ]; then
    fail "$retired_codeql_docker_path should not exist in the Docker tree"
  fi
done
assert_not_contains "$ROOT_DIR/docker-compose.yml" "$retired_sandbox_lower"

# Aggressive dry-run exposes the destructive plan without executing it.
dry_aggressive_dir="$(new_fixture dry-aggressive)"
write_valid_config "$dry_aggressive_dir"
dry_aggressive_out="$dry_aggressive_dir/dry-aggressive.out"
( cd "$dry_aggressive_dir" && ./argus-bootstrap.sh --runtime docker --dry-run -- aggressive ) >"$dry_aggressive_out" 2>&1
assert_contains "$dry_aggressive_out" "[dry-run] docker compose"
assert_contains "$dry_aggressive_out" "[dry-run] docker system prune -af --volumes"

# Bare separator is accepted and means default.
bare_dir="$(new_fixture bare-separator)"
write_valid_config "$bare_dir"
bare_out="$bare_dir/bare.out"
( cd "$bare_dir" && ARGUS_STUB_DOCKER=true ./argus-bootstrap.sh --runtime docker -- ) >"$bare_out" 2>&1
assert_contains "$bare_out" "Run mode: default"
assert_no_global_prune_execution "$bare_out"

echo "[test] argus-bootstrap tests passed"
