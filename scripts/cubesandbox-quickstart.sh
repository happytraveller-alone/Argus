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
CUBE_CODEQL_CPP_WRITABLE_LAYER_SIZE="${CUBE_CODEQL_CPP_WRITABLE_LAYER_SIZE:-4G}"
CUBE_CODEQL_CPP_DOCKERFILE="${CUBE_CODEQL_CPP_DOCKERFILE:-${ROOT_DIR}/oci/cubesandbox/codeql-cpp.Dockerfile}"
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
  scripts/cubesandbox-quickstart.sh watch-template <job_id>
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
  check_tcp_port_free "$CUBE_WEB_UI_PORT" || failed=1
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

fetch_upstream() {
  need_cmd git
  mkdir -p "$CUBE_WORK_DIR"
  if [[ ! -d "$CUBE_REPO_DIR/.git" ]]; then
    log "cloning CubeSandbox into $CUBE_REPO_DIR"
    git clone --depth 1 --branch "$CUBE_REPO_BRANCH" "$CUBE_REPO_URL" "$CUBE_REPO_DIR"
    return
  fi
  log "updating CubeSandbox checkout in $CUBE_REPO_DIR"
  git -C "$CUBE_REPO_DIR" fetch --depth 1 origin "$CUBE_REPO_BRANCH"
  git -C "$CUBE_REPO_DIR" checkout -B "$CUBE_REPO_BRANCH" FETCH_HEAD
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
  remote_root "$(cat <<REMOTE
set -Eeuo pipefail
mkdir -p /root/cubesandbox-codeql-cpp-build
cd /root/cubesandbox-codeql-cpp-build
printf '%s' '${dockerfile_b64}' | base64 -d > ${dockerfile_q}

docker pull ${registry_image_q}
DOCKER_BUILDKIT=0 docker build --pull=false \\
  --build-arg CUBE_LOCAL_REGISTRY_IMAGE=${registry_image_q} \\
  --build-arg CUBE_CODEQL_BUNDLE_URL=${bundle_url_q} \\
  -f ${dockerfile_q} \\
  -t ${image_q} .
docker push ${image_q}
REMOTE
)"
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
  remote_root "cubemastercli tpl create-from-image --image '$(shell_quote "$CUBE_CODEQL_CPP_IMAGE")' --writable-layer-size '$(shell_quote "$CUBE_CODEQL_CPP_WRITABLE_LAYER_SIZE")' --expose-port 49999 --expose-port 49983 --probe 49999"
}

watch_template() {
  local job_id="${1:-}"
  [[ -n "$job_id" ]] || fail "watch-template requires a job_id"
  remote_root "cubemastercli tpl watch --job-id '$job_id'"
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
  create-codeql-cpp-template)
    no_extra_args "${@:2}"
    create_codeql_cpp_template
    ;;
  watch-template)
    shift
    watch_template "$@"
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
