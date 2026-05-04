#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CUBE_WORK_DIR="${CUBE_WORK_DIR:-${ROOT_DIR}/.cubesandbox}"
CUBE_REPO_DIR="${CUBE_REPO_DIR:-${CUBE_WORK_DIR}/CubeSandbox}"
CUBE_HOST_RUNTIME_DIR="${CUBE_HOST_RUNTIME_DIR:-${TMPDIR:-/tmp}/argus-cubesandbox-${USER:-user}}"
CUBE_GITHUB_MIRROR_PREFIX="${CUBE_GITHUB_MIRROR_PREFIX:-https://v6.gh-proxy.org/}"
CUBE_REPO_URL="${CUBE_REPO_URL:-${CUBE_GITHUB_MIRROR_PREFIX}https://github.com/TencentCloud/CubeSandbox.git}"
CUBE_REPO_BRANCH="${CUBE_REPO_BRANCH:-master}"
CUBE_API_PORT="${CUBE_API_PORT:-23000}"
CUBE_PROXY_HTTP_PORT="${CUBE_PROXY_HTTP_PORT:-21080}"
CUBE_PROXY_HTTPS_PORT="${CUBE_PROXY_HTTPS_PORT:-21443}"
CUBE_WEB_UI_PORT="${CUBE_WEB_UI_PORT:-22088}"
CUBE_DISABLE_WEBUI="${CUBE_DISABLE_WEBUI:-true}"
CUBE_SSH_PORT="${CUBE_SSH_PORT:-10022}"
CUBE_SSH_HOST="${CUBE_SSH_HOST:-127.0.0.1}"
CUBE_VM_USER="${CUBE_VM_USER:-opencloudos}"
CUBE_VM_PASSWORD="${CUBE_VM_PASSWORD:-opencloudos}"
CUBE_TEMPLATE_IMAGE="${CUBE_TEMPLATE_IMAGE:-ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest}"
CUBE_TEMPLATE_WRITABLE_LAYER_SIZE="${CUBE_TEMPLATE_WRITABLE_LAYER_SIZE:-1G}"
CUBE_TEMPLATE_ID="${CUBE_TEMPLATE_ID:-}"
CUBE_PYTHON_CODE="${CUBE_PYTHON_CODE:-print('Hello from Cube Sandbox, safely isolated!')}"
CUBE_DOCKER_REGISTRY_MIRROR_URL="${CUBE_DOCKER_REGISTRY_MIRROR_URL:-https://m.daocloud.io/docker.io}"
CUBE_DOCKERHUB_MIRROR_IMAGE_PREFIX="${CUBE_DOCKERHUB_MIRROR_IMAGE_PREFIX:-m.daocloud.io/docker.io}"
CUBE_LOCAL_REGISTRY_IMAGE="${CUBE_LOCAL_REGISTRY_IMAGE:-${CUBE_DOCKERHUB_MIRROR_IMAGE_PREFIX}/library/registry:2}"
CUBE_LOCAL_REGISTRY_NAME="${CUBE_LOCAL_REGISTRY_NAME:-cube-local-registry}"
CUBE_LOCAL_REGISTRY_PORT="${CUBE_LOCAL_REGISTRY_PORT:-5000}"
CUBE_CODEQL_VERSION="${CUBE_CODEQL_VERSION:-2.20.5}"
CUBE_CODEQL_BUNDLE_URL="${CUBE_CODEQL_BUNDLE_URL:-${CUBE_GITHUB_MIRROR_PREFIX}https://github.com/github/codeql-action/releases/download/codeql-bundle-v${CUBE_CODEQL_VERSION}/codeql-bundle-linux64.tar.zst}"
CUBE_CODEQL_CPP_IMAGE="${CUBE_CODEQL_CPP_IMAGE:-127.0.0.1:${CUBE_LOCAL_REGISTRY_PORT}/cubesandbox-codeql-cpp:latest}"
CUBE_CODEQL_CPP_WSL_IMAGE="${CUBE_CODEQL_CPP_WSL_IMAGE:-argus/cubesandbox-codeql-cpp:latest}"
CUBE_CODEQL_CPP_WRITABLE_LAYER_SIZE="${CUBE_CODEQL_CPP_WRITABLE_LAYER_SIZE:-4Gi}"
CUBE_CODEQL_CPP_DOCKERFILE="${CUBE_CODEQL_CPP_DOCKERFILE:-${ROOT_DIR}/oci/cubesandbox/codeql-cpp.Dockerfile}"
CUBE_OPENGREP_IMAGE="${CUBE_OPENGREP_IMAGE:-127.0.0.1:${CUBE_LOCAL_REGISTRY_PORT}/cubesandbox-opengrep:latest}"
CUBE_OPENGREP_WSL_IMAGE="${CUBE_OPENGREP_WSL_IMAGE:-argus/cubesandbox-opengrep:latest}"
CUBE_OPENGREP_WRITABLE_LAYER_SIZE="${CUBE_OPENGREP_WRITABLE_LAYER_SIZE:-2Gi}"
CUBE_OPENGREP_DOCKERFILE="${CUBE_OPENGREP_DOCKERFILE:-${ROOT_DIR}/oci/cubesandbox/opengrep.Dockerfile}"
CUBE_RELEASE_VERSION="${CUBE_RELEASE_VERSION:-v0.1.2}"
CUBE_RELEASE_ASSET="${CUBE_RELEASE_ASSET:-cube-sandbox-one-click-aa8d642.tar.gz}"
CUBE_RELEASE_URL="${CUBE_RELEASE_URL:-${CUBE_GITHUB_MIRROR_PREFIX}https://github.com/TencentCloud/CubeSandbox/releases/download/${CUBE_RELEASE_VERSION}/${CUBE_RELEASE_ASSET}}"
CUBE_ALPINE_MIRROR_URL="${CUBE_ALPINE_MIRROR_URL:-http://mirrors.aliyun.com/alpine}"
CUBE_PIP_INDEX_URL="${CUBE_PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple}"

usage() {
  cat <<USAGE
cubesandbox-quickstart.sh - WSL2-native CubeSandbox quickstart wrapper for Argus workspaces

Usage:
  scripts/cubesandbox-quickstart.sh doctor
  scripts/cubesandbox-quickstart.sh fetch
  scripts/cubesandbox-quickstart.sh prepare-vm
  scripts/cubesandbox-quickstart.sh run-vm
  scripts/cubesandbox-quickstart.sh run-vm-background
  scripts/cubesandbox-quickstart.sh login
  scripts/cubesandbox-quickstart.sh install
  scripts/cubesandbox-quickstart.sh configure-docker-mirror
  scripts/cubesandbox-quickstart.sh start-local-registry
  scripts/cubesandbox-quickstart.sh create-template
  scripts/cubesandbox-quickstart.sh build-codeql-cpp-image
  scripts/cubesandbox-quickstart.sh build-codeql-cpp-image-wsl
  scripts/cubesandbox-quickstart.sh shell-codeql-cpp-image-wsl
  scripts/cubesandbox-quickstart.sh create-codeql-cpp-template
  scripts/cubesandbox-quickstart.sh build-opengrep-image
  scripts/cubesandbox-quickstart.sh build-opengrep-image-wsl
  scripts/cubesandbox-quickstart.sh shell-opengrep-image-wsl
  scripts/cubesandbox-quickstart.sh create-opengrep-template
  scripts/cubesandbox-quickstart.sh watch-template <job_id>
  scripts/cubesandbox-quickstart.sh provision-codeql-cpp-template
  scripts/cubesandbox-quickstart.sh provision-opengrep-template
  scripts/cubesandbox-quickstart.sh clean-provision-state
  CUBE_TEMPLATE_ID=<template_id> scripts/cubesandbox-quickstart.sh python-smoke
  CUBE_TEMPLATE_ID=<template_id> scripts/cubesandbox-quickstart.sh cc-smoke
  CUBE_TEMPLATE_ID=<template_id> scripts/cubesandbox-quickstart.sh codeql-cpp-smoke
  scripts/cubesandbox-quickstart.sh status

Defaults avoid Argus's frontend port:
  Cube API:        http://127.0.0.1:${CUBE_API_PORT} -> VM:3000
  Cube proxy HTTP: 127.0.0.1:${CUBE_PROXY_HTTP_PORT} -> VM:80
  Cube proxy TLS:  127.0.0.1:${CUBE_PROXY_HTTPS_PORT} -> VM:443
  Cube WebUI:      127.0.0.1:${CUBE_WEB_UI_PORT} -> VM:12088
  SSH:             127.0.0.1:${CUBE_SSH_PORT} -> VM:22

Runtime state is kept under:
  ${CUBE_WORK_DIR}

This helper is intentionally WSL2-native. It does not run QEMU or CubeSandbox
through a Docker helper container.
USAGE
}

log() {
  printf '[cubesandbox] %s\n' "$*"
}

fail() {
  printf '[cubesandbox] ERROR: %s\n' "$*" >&2
  exit 1
}

no_extra_args() {
  if [[ "$#" -ne 0 ]]; then
    fail "unexpected extra argument(s): $*"
  fi
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

is_truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|y|Y|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

check_cmd() {
  if command -v "$1" >/dev/null 2>&1; then
    printf 'ok   command %-22s %s\n' "$1" "$(command -v "$1")"
    return 0
  fi
  printf 'miss command %-22s\n' "$1"
  return 1
}

check_tcp_port_free() {
  local port="$1"
  if ss -ltn "( sport = :${port} )" 2>/dev/null | awk 'NR > 1 { found=1 } END { exit found ? 0 : 1 }'; then
    printf 'busy port    %-22s choose a different CUBE_*_PORT override\n' "$port"
    return 1
  fi
  printf 'ok   port    %-22s free\n' "$port"
}

doctor() {
  local failed=0
  local missing_qemu=0
  local missing_kvm_access=0
  local vm_path_not_writable=0
  local nested_path=""
  local nested_value=""

  if grep -qi microsoft /proc/version 2>/dev/null; then
    printf 'ok   wsl2    Microsoft WSL kernel detected\n'
  else
    printf 'miss wsl2    this helper is for WSL2-native CubeSandbox setup\n'
    failed=1
  fi

  local required_cmds=(git curl ssh scp setsid python3 rg qemu-system-x86_64 qemu-img ss docker)
  for cmd in "${required_cmds[@]}"; do
    if ! check_cmd "$cmd"; then
      failed=1
      if [[ "$cmd" == qemu-system-x86_64 || "$cmd" == qemu-img ]]; then
        missing_qemu=1
      fi
    fi
  done

  if [[ -e /dev/kvm ]]; then
    printf 'ok   device  /dev/kvm exists\n'
    [[ -r /dev/kvm ]] && printf 'ok   access  /dev/kvm readable\n' || {
      printf 'miss access  /dev/kvm not readable by current user\n'
      failed=1
      missing_kvm_access=1
    }
    [[ -w /dev/kvm ]] && printf 'ok   access  /dev/kvm writable\n' || {
      printf 'miss access  /dev/kvm not writable by current user\n'
      failed=1
      missing_kvm_access=1
    }
  else
    printf 'miss device  /dev/kvm does not exist\n'
    failed=1
  fi

  if [[ -f /sys/module/kvm_intel/parameters/nested ]]; then
    nested_path="/sys/module/kvm_intel/parameters/nested"
  elif [[ -f /sys/module/kvm_amd/parameters/nested ]]; then
    nested_path="/sys/module/kvm_amd/parameters/nested"
  fi
  if [[ -n "$nested_path" ]]; then
    nested_value="$(tr '[:lower:]' '[:upper:]' <"$nested_path")"
    if [[ "$nested_value" == "Y" || "$nested_value" == "1" ]]; then
      printf 'ok   nested  %s=%s\n' "$nested_path" "$nested_value"
    else
      printf 'miss nested  %s=%s, CubeSandbox needs nested KVM\n' "$nested_path" "$nested_value"
      failed=1
    fi
  else
    printf 'warn nested  kvm_intel/kvm_amd nested flag not found; verify manually\n'
  fi

  docker info >/dev/null 2>&1 && printf 'ok   docker  daemon reachable\n' || {
    printf 'miss docker  daemon is not reachable\n'
    failed=1
  }

  if [[ -e "$CUBE_WORK_DIR" && ! -w "$CUBE_WORK_DIR" ]]; then
    printf 'miss path    %s is not writable by current user\n' "$CUBE_WORK_DIR"
    failed=1
  else
    printf 'ok   path    %s writable or not yet created\n' "$CUBE_WORK_DIR"
  fi

  if [[ -e "${CUBE_WORK_DIR}/vm" && ! -w "${CUBE_WORK_DIR}/vm" ]]; then
    printf 'miss path    %s is not writable by current user; fix ownership before WSL2-native prepare-vm\n' "${CUBE_WORK_DIR}/vm"
    failed=1
    vm_path_not_writable=1
  fi

  check_tcp_port_free "$CUBE_API_PORT" || failed=1
  check_tcp_port_free "$CUBE_PROXY_HTTP_PORT" || failed=1
  check_tcp_port_free "$CUBE_PROXY_HTTPS_PORT" || failed=1
  if is_truthy "${CUBE_DISABLE_WEBUI:-}"; then
    printf 'ok   port    %-22s skipped (CUBE_DISABLE_WEBUI=true)\n' "$CUBE_WEB_UI_PORT"
  else
    check_tcp_port_free "$CUBE_WEB_UI_PORT" || failed=1
  fi
  check_tcp_port_free "$CUBE_SSH_PORT" || failed=1

  if [[ "$failed" -ne 0 ]]; then
    printf '\n[cubesandbox] WSL2-native remediation:\n' >&2
    if [[ "$missing_qemu" -eq 1 ]]; then
      printf '  sudo apt-get install -y qemu-system-x86 qemu-utils\n' >&2
    fi
    if [[ "$missing_kvm_access" -eq 1 ]]; then
      printf '  sudo usermod -aG kvm "$USER"\n' >&2
      printf '  # then open a new WSL login session so the kvm group takes effect\n' >&2
    fi
    if [[ "$vm_path_not_writable" -eq 1 ]]; then
      printf '  sudo chown -R "$USER:$USER" %q\n' "${CUBE_WORK_DIR}/vm" >&2
    fi
    printf '\n' >&2
    fail "host is not ready for CubeSandbox quickstart"
  fi
  log "host prerequisites look ready"
}

patch_run_vm_disable_webui() {
  # When CUBE_DISABLE_WEBUI=true, strip the WebUI hostfwd from the upstream
  # dev-env/run_vm.sh (it's invoked by run-vm / run-vm-background after
  # fetch_upstream). Each fetch_upstream does a `git checkout -B ... FETCH_HEAD`
  # which discards prior local edits, so we re-apply this patch every time.
  is_truthy "${CUBE_DISABLE_WEBUI:-}" || return 0
  local f="${CUBE_REPO_DIR}/dev-env/run_vm.sh"
  [[ -f "$f" ]] || return 0
  if grep -qF ',hostfwd=tcp::"${WEB_UI_PORT}"-:12088' "$f"; then
    log "patching $f to drop WebUI hostfwd (CUBE_DISABLE_WEBUI=true; host port ${CUBE_WEB_UI_PORT} not exposed)"
    sed -i 's|,hostfwd=tcp::"${WEB_UI_PORT}"-:12088||g' "$f"
  fi
}

fetch_upstream() {
  need_cmd git
  mkdir -p "$CUBE_WORK_DIR"
  if [[ ! -d "$CUBE_REPO_DIR/.git" ]]; then
    log "cloning CubeSandbox into $CUBE_REPO_DIR"
    git clone --depth 1 --branch "$CUBE_REPO_BRANCH" "$CUBE_REPO_URL" "$CUBE_REPO_DIR"
    patch_run_vm_disable_webui
    return
  fi
  log "updating CubeSandbox checkout in $CUBE_REPO_DIR"
  git -C "$CUBE_REPO_DIR" fetch --depth 1 origin "$CUBE_REPO_BRANCH"
  git -C "$CUBE_REPO_DIR" checkout -B "$CUBE_REPO_BRANCH" FETCH_HEAD
  patch_run_vm_disable_webui
}

dev_env_dir() {
  [[ -d "$CUBE_REPO_DIR/dev-env" ]] || fetch_upstream
  printf '%s/dev-env\n' "$CUBE_REPO_DIR"
}

run_dev_env() {
  local script="$1"
  shift
  local dir
  dir="$(dev_env_dir)"
  local work_dir="${CUBE_WORK_DIR}/vm"
  if [[ "$script" == "./login.sh" ]]; then
    work_dir="${CUBE_HOST_RUNTIME_DIR}/login"
  fi
  (
    cd "$dir"
    WORK_DIR="$work_dir" \
      SSH_PORT="$CUBE_SSH_PORT" \
      SSH_HOST="$CUBE_SSH_HOST" \
      VM_USER="$CUBE_VM_USER" \
      VM_PASSWORD="$CUBE_VM_PASSWORD" \
      CUBE_API_PORT="$CUBE_API_PORT" \
      CUBE_PROXY_HTTP_PORT="$CUBE_PROXY_HTTP_PORT" \
      CUBE_PROXY_HTTPS_PORT="$CUBE_PROXY_HTTPS_PORT" \
      WEB_UI_PORT="$CUBE_WEB_UI_PORT" \
      "$script" "$@"
  )
}

ssh_common_opts() {
  printf '%s\n' \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o PreferredAuthentications=password \
    -o PubkeyAuthentication=no \
    -o ConnectTimeout=10 \
    -p "$CUBE_SSH_PORT"
}

remote_root() {
  local command="$1"
  need_cmd ssh
  need_cmd setsid
  mkdir -p "$CUBE_WORK_DIR"
  local askpass="${CUBE_WORK_DIR}/.ssh-askpass.sh"
  cat >"$askpass" <<EOF
#!/usr/bin/env bash
printf '%s\n' '${CUBE_VM_PASSWORD}'
EOF
  chmod 700 "$askpass"
  mapfile -t opts < <(ssh_common_opts)
  local ssh_status=0
  set +e
  DISPLAY="${DISPLAY:-cubesandbox-quickstart}" \
    SSH_ASKPASS="$askpass" \
    SSH_ASKPASS_REQUIRE=force \
    setsid -w ssh "${opts[@]}" "${CUBE_VM_USER}@${CUBE_SSH_HOST}" "sudo -i bash -s" <<<"$command"
  ssh_status=$?
  set -e
  rm -f "$askpass"
  return "$ssh_status"
}

shell_quote() {
  printf '%q' "$1"
}

install_cube() {
  local install_cmd
  if [[ "${CUBE_MIRROR:-}" == "cn" ]]; then
    install_cmd="curl -sL https://cnb.cool/CubeSandbox/CubeSandbox/-/git/raw/master/deploy/one-click/online-install.sh | ALPINE_MIRROR_URL='${CUBE_ALPINE_MIRROR_URL}' PIP_INDEX_URL='${CUBE_PIP_INDEX_URL}' MIRROR=cn bash"
  else
    install_cmd="curl -sL ${CUBE_GITHUB_MIRROR_PREFIX}https://github.com/tencentcloud/CubeSandbox/raw/master/deploy/one-click/online-install.sh | ALPINE_MIRROR_URL='${CUBE_ALPINE_MIRROR_URL}' PIP_INDEX_URL='${CUBE_PIP_INDEX_URL}' bash -s -- --url='${CUBE_RELEASE_URL}'"
  fi
  remote_root "$install_cmd"
}

create_template() {
  remote_root "cubemastercli tpl create-from-image --image '$CUBE_TEMPLATE_IMAGE' --writable-layer-size '$CUBE_TEMPLATE_WRITABLE_LAYER_SIZE' --expose-port 49999 --expose-port 49983 --probe 49999"
}

configure_docker_mirror() {
  local mirror_q
  mirror_q="$(shell_quote "$CUBE_DOCKER_REGISTRY_MIRROR_URL")"
  remote_root "$(cat <<REMOTE
set -Eeuo pipefail
mkdir -p /etc/docker
if [[ -f /etc/docker/daemon.json ]]; then
  cp /etc/docker/daemon.json "/etc/docker/daemon.json.bak.\$(date +%s)"
fi
python3 - ${mirror_q} <<'PY'
import json
import sys
from pathlib import Path

path = Path("/etc/docker/daemon.json")
data = {}
if path.exists() and path.read_text().strip():
    data = json.loads(path.read_text())
mirror = sys.argv[1]
mirrors = data.get("registry-mirrors", [])
if mirror not in mirrors:
    mirrors.insert(0, mirror)
data["registry-mirrors"] = mirrors
path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\\n")
print(path.read_text(), end="")
PY
systemctl restart docker
sleep 3
docker info 2>/dev/null | sed -n '/Registry Mirrors:/,/Live Restore Enabled:/p'
REMOTE
)"
}

start_local_registry() {
  local image_q name_q port_q
  image_q="$(shell_quote "$CUBE_LOCAL_REGISTRY_IMAGE")"
  name_q="$(shell_quote "$CUBE_LOCAL_REGISTRY_NAME")"
  port_q="$(shell_quote "$CUBE_LOCAL_REGISTRY_PORT")"
  remote_root "$(cat <<REMOTE
set -Eeuo pipefail
docker pull ${image_q}
docker rm -f ${name_q} >/dev/null 2>&1 || true
docker run -d --restart unless-stopped --name ${name_q} -p ${port_q}:5000 ${image_q}
sleep 2
curl -fsS "http://127.0.0.1:${CUBE_LOCAL_REGISTRY_PORT}/v2/" >/dev/null
printf '%s\\n' "LOCAL_REGISTRY_OK http://127.0.0.1:${CUBE_LOCAL_REGISTRY_PORT}/v2/"
REMOTE
)"
}

build_codeql_cpp_image() {
  [[ -f "$CUBE_CODEQL_CPP_DOCKERFILE" ]] || fail "missing OCI image config: $CUBE_CODEQL_CPP_DOCKERFILE"
  need_cmd base64
  local image_q bundle_url_q registry_image_q dockerfile_q dockerfile_b64
  image_q="$(shell_quote "$CUBE_CODEQL_CPP_IMAGE")"
  bundle_url_q="$(shell_quote "$CUBE_CODEQL_BUNDLE_URL")"
  registry_image_q="$(shell_quote "$CUBE_LOCAL_REGISTRY_IMAGE")"
  dockerfile_q="$(shell_quote "$(basename "$CUBE_CODEQL_CPP_DOCKERFILE")")"
  dockerfile_b64="$(base64 -w 0 "$CUBE_CODEQL_CPP_DOCKERFILE")"
  # NOTE: Keep the docker build invocation on a SINGLE line. When this heredoc
  # is piped to the guest via `ssh ... "sudo -i bash -s" <<<"$command"`,
  # backslash-newline line continuations have been observed to be dropped in
  # transit (the first line becomes `docker build --pull=false` with no PATH,
  # and the remaining flags get parsed as separate commands), producing:
  #   "docker: 'docker build' requires 1 argument".
  # A single-line invocation sidesteps that pathology entirely.
  remote_root "$(cat <<REMOTE
set -Eeuo pipefail
mkdir -p /root/cubesandbox-codeql-cpp-build
cd /root/cubesandbox-codeql-cpp-build
printf '%s' '${dockerfile_b64}' | base64 -d > ${dockerfile_q}

docker pull ${registry_image_q}
DOCKER_BUILDKIT=0 docker build --pull=false --build-arg CUBE_LOCAL_REGISTRY_IMAGE=${registry_image_q} --build-arg CUBE_CODEQL_BUNDLE_URL=${bundle_url_q} -f ${dockerfile_q} -t ${image_q} .
docker push ${image_q}
REMOTE
)"
}

build_opengrep_image() {
  [[ -f "$CUBE_OPENGREP_DOCKERFILE" ]] || fail "missing OCI image config: $CUBE_OPENGREP_DOCKERFILE"
  [[ -f "${ROOT_DIR}/docker/opengrep-scan.sh" ]] || fail "missing opengrep scan wrapper: ${ROOT_DIR}/docker/opengrep-scan.sh"
  need_cmd base64
  local image_q registry_image_q dockerfile_q dockerfile_b64 scan_script_b64 rules_tar_b64
  image_q="$(shell_quote "$CUBE_OPENGREP_IMAGE")"
  registry_image_q="$(shell_quote "$CUBE_LOCAL_REGISTRY_IMAGE")"
  dockerfile_q="$(shell_quote "$(basename "$CUBE_OPENGREP_DOCKERFILE")")"
  dockerfile_b64="$(base64 -w 0 "$CUBE_OPENGREP_DOCKERFILE")"
  scan_script_b64="$(base64 -w 0 "${ROOT_DIR}/docker/opengrep-scan.sh")"
  rules_tar_b64="$(
    tar -C "${ROOT_DIR}/backend/assets/scan_rule_assets" -czf - rules_opengrep | base64 -w 0
  )"
  remote_root "$(cat <<REMOTE
set -Eeuo pipefail
mkdir -p /root/cubesandbox-opengrep-build/context
cd /root/cubesandbox-opengrep-build
printf '%s' '${dockerfile_b64}' | base64 -d > ${dockerfile_q}
printf '%s' '${scan_script_b64}' | base64 -d > context/opengrep-scan.sh
mkdir -p context
printf '%s' '${rules_tar_b64}' | base64 -d > context/rules.tar.gz

docker pull ${registry_image_q}
DOCKER_BUILDKIT=0 docker build --pull=false --build-arg CUBE_LOCAL_REGISTRY_IMAGE=${registry_image_q} -f ${dockerfile_q} -t ${image_q} context
docker push ${image_q}
REMOTE
)"
}

build_opengrep_image_wsl() {
  [[ -f "$CUBE_OPENGREP_DOCKERFILE" ]] || fail "missing OCI image config: $CUBE_OPENGREP_DOCKERFILE"
  need_cmd docker
  local temp_dir
  temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/argus-cube-opengrep-build.XXXXXX")"
  trap 'rm -rf "$temp_dir"' RETURN
  cp "$CUBE_OPENGREP_DOCKERFILE" "$temp_dir/opengrep.Dockerfile"
  cp "${ROOT_DIR}/docker/opengrep-scan.sh" "$temp_dir/opengrep-scan.sh"
  tar -C "${ROOT_DIR}/backend/assets/scan_rule_assets" -czf "$temp_dir/rules.tar.gz" rules_opengrep
  docker build --pull=false \
    --build-arg CUBE_LOCAL_REGISTRY_IMAGE="$CUBE_LOCAL_REGISTRY_IMAGE" \
    -f "$temp_dir/opengrep.Dockerfile" \
    -t "$CUBE_OPENGREP_WSL_IMAGE" \
    "$temp_dir"
}

shell_opengrep_image_wsl() {
  need_cmd docker
  docker run --rm -it \
    --entrypoint /bin/bash \
    "$CUBE_OPENGREP_WSL_IMAGE"
}

build_codeql_cpp_image_wsl() {
  [[ -f "$CUBE_CODEQL_CPP_DOCKERFILE" ]] || fail "missing OCI image config: $CUBE_CODEQL_CPP_DOCKERFILE"
  need_cmd docker
  docker build --pull=false \
    --build-arg CUBE_LOCAL_REGISTRY_IMAGE="$CUBE_LOCAL_REGISTRY_IMAGE" \
    --build-arg CUBE_CODEQL_BUNDLE_URL="$CUBE_CODEQL_BUNDLE_URL" \
    -f "$CUBE_CODEQL_CPP_DOCKERFILE" \
    -t "$CUBE_CODEQL_CPP_WSL_IMAGE" \
    "$ROOT_DIR"
}

shell_codeql_cpp_image_wsl() {
  need_cmd docker
  docker run --rm -it \
    --entrypoint /bin/bash \
    "$CUBE_CODEQL_CPP_WSL_IMAGE"
}

create_codeql_cpp_template() {
  local raw job_id
  raw="$(remote_root "cubemastercli tpl create-from-image --image '$(shell_quote "$CUBE_CODEQL_CPP_IMAGE")' --writable-layer-size '$(shell_quote "$CUBE_CODEQL_CPP_WRITABLE_LAYER_SIZE")' --expose-port 49999 --expose-port 49983 --probe 49999 2>&1" | tee /dev/stderr)"
  job_id="$(printf '%s\n' "$raw" | sed -nE 's/.*job[_ -]?id[: ]+([0-9a-fA-F-]+).*/\1/p' | head -n 1 || true)"
  if [[ -z "$job_id" ]]; then
    job_id="$(printf '%s\n' "$raw" | grep -Eio '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -n 1 || true)"
  fi
  [[ -n "$job_id" ]] || fail "create-codeql-cpp-template did not emit a job_id"
  printf 'JOB_ID=%s\n' "$job_id"
}

create_opengrep_template() {
  local raw job_id
  raw="$(remote_root "cubemastercli tpl create-from-image --image '$(shell_quote "$CUBE_OPENGREP_IMAGE")' --writable-layer-size '$(shell_quote "$CUBE_OPENGREP_WRITABLE_LAYER_SIZE")' --expose-port 49999 --expose-port 49983 --probe 49999 2>&1" | tee /dev/stderr)"
  job_id="$(printf '%s\n' "$raw" | sed -nE 's/.*job[_ -]?id[: ]+([0-9a-fA-F-]+).*/\1/p' | head -n 1 || true)"
  if [[ -z "$job_id" ]]; then
    job_id="$(printf '%s\n' "$raw" | grep -Eio '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -n 1 || true)"
  fi
  [[ -n "$job_id" ]] || fail "create-opengrep-template did not emit a job_id"
  printf 'JOB_ID=%s\n' "$job_id"
}

watch_template() {
  local job_id="${1:-}"
  [[ -n "$job_id" ]] || fail "watch-template requires a job_id"
  local raw template_id artifact_id status
  raw="$(remote_root "cubemastercli tpl watch --job-id '$job_id' 2>&1" | tee /dev/stderr)"
  template_id="$(printf '%s\n' "$raw" | sed -nE 's/.*template[_ ]?id[: ]+([a-zA-Z0-9_-]+).*/\1/p' | head -n 1 || true)"
  artifact_id="$(printf '%s\n' "$raw" | sed -nE 's/.*artifact[_ ]?id[: ]+([a-zA-Z0-9_-]+).*/\1/p' | head -n 1 || true)"
  status="$(printf '%s\n' "$raw" | sed -nE 's/.*(template[_ ]?)?status[: ]+([A-Za-z_]+).*/\2/p' | tail -n 1 || true)"
  [[ -n "$status" ]] || status="UNKNOWN"
  printf 'STATUS=%s\n' "$status"
  [[ -n "$template_id" ]] && printf 'TEMPLATE_ID=%s\n' "$template_id"
  [[ -n "$artifact_id" ]] && printf 'ARTIFACT_ID=%s\n' "$artifact_id"
}

clean_cube_provision_state() {
  # ── step 0a: cubemaster template registry sweep (FAILED + orphaned) ──────
  log "[clean] step 0a: cubemaster template registry sweep (FAILED + orphaned)"

  # Fetch template list from cubemaster registry (tolerates CLI errors).
  local list_raw
  list_raw=$(remote_root "cubemastercli tpl list 2>&1" || fail "template list failed")

  # Parse with python3 (already a host dependency per doctor check).
  # CLI output may be tabular or JSON depending on version — probe both.
  # Extract FAILED template_ids and all template_ids for orphan check.
  local failed_ids all_ids
  failed_ids=$(printf '%s' "$list_raw" | python3 - <<'PY'
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("data", [])
    print("\n".join(t["template_id"] for t in data if t.get("status", "").upper() == "FAILED"))
except Exception:
    # Fallback: tabular parse — columns "TEMPLATE_ID  STATUS  ..."
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].upper() == "FAILED":
            print(parts[0])
PY
)
  all_ids=$(printf '%s' "$list_raw" | python3 - <<'PY'
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("data", [])
    print("\n".join(t["template_id"] for t in data))
except Exception:
    for line in raw.splitlines():
        parts = line.split()
        if parts and parts[0] not in ("TEMPLATE_ID", ""):
            print(parts[0])
PY
)

  # Orphan detection: template_ids in cubemaster but absent from backend's
  # rust_cubesandbox_templates Postgres table. Gracefully degrades if DB unset.
  # Both sides are trimmed and lowercased before `comm` so case/whitespace
  # variants do not mis-classify a live template as an orphan.
  local db_url="${DATABASE_URL:-${ARGUS_DATABASE_URL:-}}"
  local orphan_ids=""
  if [[ -n "${db_url:-}" && -n "${all_ids:-}" ]]; then
    local known_ids psql_status
    known_ids=$(psql "$db_url" -tAc \
      "SELECT template_id FROM rust_cubesandbox_templates WHERE template_id IS NOT NULL" \
      2>/dev/null)
    psql_status=$?
    if [[ ${psql_status} -ne 0 ]]; then
      # Treat psql failure as DB-unreachable: skip orphan detection rather than
      # silently treating every cubemaster template as orphaned.
      log "[clean] psql query failed (rc=${psql_status}); skipping orphan detection"
    elif [[ -z "${known_ids// /}" ]]; then
      # Empty result set is dangerous: every cubemaster template would be
      # classified orphan. Refuse unless the operator explicitly opts in.
      if [[ "${CUBE_ALLOW_EMPTY_KNOWN_TEMPLATES:-0}" == "1" ]]; then
        log "[clean] backend reports zero known templates; treating all cubemaster templates as orphans (CUBE_ALLOW_EMPTY_KNOWN_TEMPLATES=1)"
        orphan_ids=$(printf '%s\n' "$all_ids" \
          | awk 'NF { print tolower($1) }' | sort -u)
      else
        log "[clean] backend reports zero known templates; refusing orphan sweep (set CUBE_ALLOW_EMPTY_KNOWN_TEMPLATES=1 to override)"
      fi
    else
      orphan_ids=$(comm -23 \
        <(printf '%s\n' "$all_ids"   | awk 'NF { print tolower($1) }' | sort -u) \
        <(printf '%s\n' "$known_ids" | awk 'NF { print tolower($1) }' | sort -u) \
        || true)
    fi
  else
    log "[clean] DATABASE_URL unset — skipping orphan detection"
  fi

  # Dedupe FAILED + orphaned; empty lines filtered out.
  local to_delete
  to_delete=$(printf '%s\n%s\n' "${failed_ids:-}" "${orphan_ids:-}" \
    | sort -u | grep -v '^$' || true)

  local before_count delete_count=0
  before_count=$(printf '%s' "${all_ids:-}" | grep -c . || true)

  if [[ -n "${to_delete:-}" ]]; then
    log "[clean] deleting $(printf '%s\n' "$to_delete" | grep -c . || true) stale template(s) from cubemaster"
    while IFS= read -r tid; do
      [[ -z "${tid:-}" ]] && continue
      # Defense-in-depth: refuse template_ids that could break out of single
      # quotes when interpolated into the remote sudo bash payload.
      if [[ ! "${tid}" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{2,127}$ ]]; then
        fail "[clean] refusing to delete: template id '$tid' fails safety regex"
      fi
      log "[clean]   delete $tid"
      if ! remote_root "cubemastercli template delete --template-id '$tid'" >/tmp/.cm_del 2>&1; then
        if grep -qiE 'not found|does not exist' /tmp/.cm_del 2>/dev/null; then
          log "[clean]   already gone: $tid"
        else
          cat /tmp/.cm_del >&2 2>/dev/null || true
          fail "[clean] cubemaster template delete failed for $tid (fail-fast)"
        fi
      fi
      delete_count=$((delete_count + 1))
    done <<< "$to_delete"
  else
    log "[clean] no stale templates to delete"
  fi

  # Disk space report from guest VM.
  local disk_info
  disk_info=$(remote_root "df -h /var/lib/containerd 2>/dev/null | tail -1" 2>/dev/null || echo "unavailable")
  log "[clean] template sweep done: before=${before_count} deleted=${delete_count} disk=${disk_info}"

  # ── step 0b (existing): purge rootfs-artifacts + docker dangling ─────────
  # Each create-codeql-cpp-template run leaves a /tmp/cubemaster-rootfs-artifacts/rfs-<id>/
  # directory in the guest VM holding a .tmp-rootfs.tar* (multi-GB). Without
  # cleanup these accumulate across runs and eventually exhaust guest /tmp,
  # breaking subsequent provisions with:
  #   "write /tmp/cubemaster-rootfs-artifacts/rfs-.../.tmp-rootfs.tar...: no space left on device"
  # We unconditionally drop those artifact dirs (they are transient build
  # scratch — published templates live in cubemaster's own data store) and
  # prune dangling docker containers/images to keep guest rootfs lean.
  log "[clean] purging stale guest provision scratch (rootfs-artifacts + docker dangling)"
  remote_root "$(cat <<'REMOTE'
set -Eeuo pipefail
artifact_dir=/tmp/cubemaster-rootfs-artifacts
if [ -d "$artifact_dir" ]; then
  before=$(du -sh "$artifact_dir" 2>/dev/null | awk '{print $1}' || echo '?')
  find "$artifact_dir" -mindepth 1 -maxdepth 1 -name 'rfs-*' -exec rm -rf {} + 2>/dev/null || true
  find "$artifact_dir" -mindepth 1 -maxdepth 1 -name '.tmp-rootfs.tar*' -delete 2>/dev/null || true
  after=$(du -sh "$artifact_dir" 2>/dev/null | awk '{print $1}' || echo '?')
  echo "[clean] $artifact_dir: ${before} -> ${after}"
else
  echo "[clean] $artifact_dir not present (skip)"
fi
echo "[clean] disk before:"
df -h / 2>/dev/null | awk 'NR==1 || /\/$/'
echo "[clean] docker container prune"
docker container prune -f >/dev/null 2>&1 || true
echo "[clean] docker image prune (dangling only)"
docker image prune -f >/dev/null 2>&1 || true
# Each start-local-registry creates a new docker volume backing the registry
# data. When containers are recreated, the old volumes become orphans holding
# multi-GB blobs. Without volume prune we accumulate 10+ GB per provision
# cycle. Only unused (non-mounted) volumes are removed; active registry
# volumes are preserved.
echo "[clean] docker volume prune (unused only)"
docker volume prune -f >/dev/null 2>&1 || true
# NOTE: We deliberately do NOT prune docker builder cache here. The build
# cache for the codeql-cpp image is small (a few hundred MB) but its absence
# forces a full re-download of the codeql-bundle (~1GB), which on slow
# networks can hang long enough for the legacy docker builder to drop
# the build container with "unexpected EOF". Volume + image prune above
# already reclaim >10GB; the marginal gain from builder prune is not worth
# the rebuild risk.
echo "[clean] disk after:"
df -h / 2>/dev/null | awk 'NR==1 || /\/$/'
REMOTE
)"
}

provision_codeql_cpp_template() {
  log "[provision] step 0/5 clean-provision-state (purge stale artifacts so /tmp does not exhaust)"
  clean_cube_provision_state
  log "[provision] step 1/5 configure-docker-mirror"
  configure_docker_mirror
  log "[provision] step 2/5 start-local-registry"
  start_local_registry
  log "[provision] step 3/5 build-codeql-cpp-image"
  build_codeql_cpp_image
  log "[provision] step 4/5 create-codeql-cpp-template"
  local create_output job_id
  create_output="$(create_codeql_cpp_template)"
  printf '%s\n' "$create_output"
  job_id="$(printf '%s\n' "$create_output" | sed -nE 's/^JOB_ID=(.+)$/\1/p' | head -n 1 || true)"
  [[ -n "$job_id" ]] || fail "provision: failed to capture job_id"
  log "[provision] step 5/5 watch-template ${job_id}"
  local watch_output template_id artifact_id status
  watch_output="$(watch_template "$job_id")"
  printf '%s\n' "$watch_output"
  template_id="$(printf '%s\n' "$watch_output" | sed -nE 's/^TEMPLATE_ID=(.+)$/\1/p' | head -n 1 || true)"
  artifact_id="$(printf '%s\n' "$watch_output" | sed -nE 's/^ARTIFACT_ID=(.+)$/\1/p' | head -n 1 || true)"
  status="$(printf '%s\n' "$watch_output" | sed -nE 's/^STATUS=(.+)$/\1/p' | head -n 1 || true)"
  [[ -n "$status" ]] || status="UNKNOWN"
  python3 - "$template_id" "$artifact_id" "$status" "$job_id" "$CUBE_CODEQL_CPP_IMAGE" <<'PY'
import json
import sys

template_id, artifact_id, status, job_id, image_ref = sys.argv[1:6]

def empty_to_none(value):
    return value if value else None

print(
    "PROVISION_RESULT="
    + json.dumps(
        {
            "template_id": empty_to_none(template_id),
            "artifact_id": empty_to_none(artifact_id),
            "status": status or "UNKNOWN",
            "job_id": empty_to_none(job_id),
            "image_ref": image_ref,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
)
PY
  if [[ "$status" != "READY" ]]; then
    fail "provision-codeql-cpp-template ended with status=${status}"
  fi
}

provision_opengrep_template() {
  log "[provision] step 0/5 clean-provision-state (purge stale artifacts so /tmp does not exhaust)"
  clean_cube_provision_state
  log "[provision] step 1/5 configure-docker-mirror"
  configure_docker_mirror
  log "[provision] step 2/5 start-local-registry"
  start_local_registry
  log "[provision] step 3/5 build-opengrep-image"
  build_opengrep_image
  log "[provision] step 4/5 create-opengrep-template"
  local create_output job_id
  create_output="$(create_opengrep_template)"
  printf '%s\n' "$create_output"
  job_id="$(printf '%s\n' "$create_output" | sed -nE 's/^JOB_ID=(.+)$/\1/p' | head -n 1 || true)"
  [[ -n "$job_id" ]] || fail "provision: failed to capture job_id"
  log "[provision] step 5/5 watch-template ${job_id}"
  local watch_output template_id artifact_id status
  watch_output="$(watch_template "$job_id")"
  printf '%s\n' "$watch_output"
  template_id="$(printf '%s\n' "$watch_output" | sed -nE 's/^TEMPLATE_ID=(.+)$/\1/p' | head -n 1 || true)"
  artifact_id="$(printf '%s\n' "$watch_output" | sed -nE 's/^ARTIFACT_ID=(.+)$/\1/p' | head -n 1 || true)"
  status="$(printf '%s\n' "$watch_output" | sed -nE 's/^STATUS=(.+)$/\1/p' | head -n 1 || true)"
  [[ -n "$status" ]] || status="UNKNOWN"
  python3 - "$template_id" "$artifact_id" "$status" "$job_id" "$CUBE_OPENGREP_IMAGE" <<'PY'
import json
import sys

template_id, artifact_id, status, job_id, image_ref = sys.argv[1:6]

def empty_to_none(value):
    return value if value else None

print(
    "PROVISION_RESULT="
    + json.dumps(
        {
            "template_id": empty_to_none(template_id),
            "artifact_id": empty_to_none(artifact_id),
            "status": status or "UNKNOWN",
            "job_id": empty_to_none(job_id),
            "image_ref": image_ref,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
)
PY
  if [[ "$status" != "READY" ]]; then
    fail "provision-opengrep-template ended with status=${status}"
  fi
}

python_smoke() {
  [[ -n "$CUBE_TEMPLATE_ID" ]] || fail "CUBE_TEMPLATE_ID is required"
  local template_id_q code_q
  printf -v template_id_q '%q' "$CUBE_TEMPLATE_ID"
  printf -v code_q '%q' "$CUBE_PYTHON_CODE"
  remote_root "$(cat <<REMOTE
set -Eeuo pipefail
yum install -y python3 python3-pip >/dev/null
python3 -m pip show e2b-code-interpreter >/dev/null 2>&1 || python3 -m pip install e2b-code-interpreter
export E2B_API_URL="http://127.0.0.1:3000"
export E2B_API_KEY="dummy"
export SSL_CERT_FILE="/root/.local/share/mkcert/rootCA.pem"
python3 - ${template_id_q} ${code_q} <<'PY'
import os
import sys
from e2b_code_interpreter import Sandbox

template_id, code = sys.argv[1:3]
with Sandbox.create(template=template_id) as sandbox:
    result = sandbox.run_code(code)
    print(result)
PY
REMOTE
)"
}

cc_smoke() {
  CUBE_PYTHON_CODE="$(cat <<'PY'
import pathlib
import subprocess

work = pathlib.Path("/tmp/cube-cc-smoke")
work.mkdir(exist_ok=True)
src_c = work / "hello.c"
src_cpp = work / "hello.cpp"
src_c.write_text('#include <stdio.h>\nint main(void){ printf("C_OK:%d\\n", 6*7); return 0; }\n')
src_cpp.write_text('#include <iostream>\n#include <vector>\nint main(){ std::vector<int> v{1,2,3,4}; int s=0; for(int x:v) s+=x; std::cout << "CPP_OK:" << s << "\\n"; return 0; }\n')
subprocess.check_call(["gcc", str(src_c), "-o", str(work / "hello_c")])
subprocess.check_call(["g++", "-std=c++17", str(src_cpp), "-o", str(work / "hello_cpp")])
print(subprocess.check_output([str(work / "hello_c")], text=True).strip())
print(subprocess.check_output([str(work / "hello_cpp")], text=True).strip())
PY
)" python_smoke
}

codeql_cpp_smoke() {
  CUBE_PYTHON_CODE="$(cat <<'PY'
import json
import pathlib
import subprocess

def run(cmd, cwd=None, shell=False):
    print("$", cmd if isinstance(cmd, str) else " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=cwd,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=240,
    )
    out = result.stdout
    if out.strip():
        print(out.strip())
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, out)
    return out

for cmd in [
    ["gcc", "--version"],
    ["g++", "--version"],
    ["make", "--version"],
    ["cmake", "--version"],
    ["codeql", "version"],
]:
    out = run(cmd)
    print("VERSION_OK", cmd[0], out.splitlines()[0])

work = pathlib.Path("/tmp/cube-codeql-cpp-smoke")
if work.exists():
    subprocess.run(["rm", "-rf", str(work)], check=True)
work.mkdir()

(work / "hello.c").write_text(
    '#include <stdio.h>\nint main(void){ printf("C_OK:%d\\n", 6*7); return 0; }\n'
)
run(["gcc", "hello.c", "-o", "hello_c"], cwd=work)
print(run(["./hello_c"], cwd=work).strip())

(work / "CMakeLists.txt").write_text(
    "cmake_minimum_required(VERSION 3.16)\n"
    "project(cube_codeql_cpp LANGUAGES CXX)\n"
    "add_executable(cube_cpp main.cpp)\n"
)
(work / "main.cpp").write_text(
    '#include <iostream>\n'
    '#include <vector>\n'
    'int main(){ std::vector<int> v{1,2,3,4}; int s=0; '
    'for(int x:v) s+=x; std::cout << "CPP_OK:" << s << "\\n"; return 0; }\n'
)
(work / "Makefile").write_text(
    "make_cpp: main.cpp\n\tg++ -std=c++17 main.cpp -o make_cpp\n"
)
run(["make", "make_cpp"], cwd=work)
print(run(["./make_cpp"], cwd=work).strip())
run(["cmake", "-S", ".", "-B", "build"], cwd=work)
run(["cmake", "--build", "build"], cwd=work)
print(run(["./build/cube_cpp"], cwd=work).strip())
run(["rm", "-rf", "build", "codeql-db"], cwd=work)
run(["cmake", "-S", ".", "-B", "build"], cwd=work)
run(
    [
        "codeql",
        "database",
        "create",
        "codeql-db",
        "--language=cpp",
        "--command",
        "cmake --build build",
        "--overwrite",
    ],
    cwd=work,
)
print("CODEQL_DB_OK", (work / "codeql-db").exists())
run(
    [
        "codeql",
        "database",
        "analyze",
        "codeql-db",
        "codeql/cpp-queries:Security/CWE/CWE-120/BadlyBoundedWrite.ql",
        "--format=sarifv2.1.0",
        "--output",
        "results.sarif",
        "--threads=1",
        "--ram=2048",
    ],
    cwd=work,
)
sarif_path = work / "results.sarif"
print("CODEQL_ANALYZE_OK", sarif_path.exists() and sarif_path.stat().st_size > 0)
sarif = json.loads(sarif_path.read_text())
print("CODEQL_SARIF_OK", sarif.get("version") == "2.1.0" and bool(sarif.get("runs")))
PY
)" python_smoke
}

status() {
  if curl -fsS --max-time 5 "http://127.0.0.1:${CUBE_API_PORT}/health" >/dev/null; then
    log "CubeSandbox API is healthy on http://127.0.0.1:${CUBE_API_PORT}"
  else
    log "CubeSandbox API is not healthy on http://127.0.0.1:${CUBE_API_PORT}"
    return 1
  fi
}

cmd="${1:-}"
case "$cmd" in
  doctor)
    no_extra_args "${@:2}"
    doctor
    ;;
  fetch)
    no_extra_args "${@:2}"
    fetch_upstream
    ;;
  prepare-vm)
    no_extra_args "${@:2}"
    fetch_upstream
    run_dev_env ./prepare_image.sh
    ;;
  run-vm)
    no_extra_args "${@:2}"
    fetch_upstream
    run_dev_env ./run_vm.sh
    ;;
  run-vm-background)
    no_extra_args "${@:2}"
    fetch_upstream
    VM_BACKGROUND=1 run_dev_env ./run_vm.sh
    ;;
  login)
    no_extra_args "${@:2}"
    run_dev_env ./login.sh
    ;;
  install)
    no_extra_args "${@:2}"
    install_cube
    ;;
  configure-docker-mirror)
    no_extra_args "${@:2}"
    configure_docker_mirror
    ;;
  start-local-registry)
    no_extra_args "${@:2}"
    start_local_registry
    ;;
  create-template)
    no_extra_args "${@:2}"
    create_template
    ;;
  build-codeql-cpp-image)
    no_extra_args "${@:2}"
    build_codeql_cpp_image
    ;;
  build-codeql-cpp-image-wsl)
    no_extra_args "${@:2}"
    build_codeql_cpp_image_wsl
    ;;
  shell-codeql-cpp-image-wsl)
    no_extra_args "${@:2}"
    shell_codeql_cpp_image_wsl
    ;;
  build-opengrep-image)
    no_extra_args "${@:2}"
    build_opengrep_image
    ;;
  build-opengrep-image-wsl)
    no_extra_args "${@:2}"
    build_opengrep_image_wsl
    ;;
  shell-opengrep-image-wsl)
    no_extra_args "${@:2}"
    shell_opengrep_image_wsl
    ;;
  create-codeql-cpp-template)
    no_extra_args "${@:2}"
    create_codeql_cpp_template
    ;;
  create-opengrep-template)
    no_extra_args "${@:2}"
    create_opengrep_template
    ;;
  watch-template)
    shift
    watch_template "$@"
    ;;
  clean-provision-state)
    no_extra_args "${@:2}"
    clean_cube_provision_state
    ;;
  provision-codeql-cpp-template)
    no_extra_args "${@:2}"
    provision_codeql_cpp_template
    ;;
  provision-opengrep-template)
    no_extra_args "${@:2}"
    provision_opengrep_template
    ;;
  python-smoke)
    no_extra_args "${@:2}"
    python_smoke
    ;;
  cc-smoke)
    no_extra_args "${@:2}"
    cc_smoke
    ;;
  codeql-cpp-smoke)
    no_extra_args "${@:2}"
    codeql_cpp_smoke
    ;;
  status)
    no_extra_args "${@:2}"
    status
    ;;
  ""|help|--help|-h)
    no_extra_args "${@:2}"
    usage
    ;;
  *)
    usage >&2
    fail "unknown command: $cmd"
    ;;
esac
