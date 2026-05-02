#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/cubesandbox-quickstart.sh"
DOC="$ROOT_DIR/docs/cubesandbox-python-quickstart.md"
OCI_DOCKERFILE="$ROOT_DIR/oci/cubesandbox/codeql-cpp.Dockerfile"
OCI_README="$ROOT_DIR/oci/cubesandbox/README.md"

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

bash -n "$SCRIPT"

[[ -f "$OCI_DOCKERFILE" ]] || fail "Expected OCI image config at $OCI_DOCKERFILE"
[[ -f "$OCI_README" ]] || fail "Expected OCI image docs at $OCI_README"

help_out="$(mktemp)"
trap 'rm -f "$help_out"' EXIT
"$SCRIPT" --help >"$help_out"

assert_contains "$help_out" "WSL2-native"
assert_not_contains "$help_out" "build-toolbox"
assert_not_contains "$help_out" "toolbox-doctor"
assert_not_contains "$help_out" "--toolbox"

assert_not_contains "$SCRIPT" "CUBE_TOOLBOX"
assert_not_contains "$SCRIPT" "build_toolbox"
assert_not_contains "$SCRIPT" "toolbox_run"
assert_not_contains "$SCRIPT" "toolbox"
assert_not_contains "$SCRIPT" "--toolbox"
assert_contains "$SCRIPT" "https://v6.gh-proxy.org/"
assert_contains "$SCRIPT" "https://m.daocloud.io/docker.io"
assert_contains "$SCRIPT" "m.daocloud.io/docker.io"
assert_contains "$SCRIPT" '${CUBE_GITHUB_MIRROR_PREFIX}https://github.com/TencentCloud/CubeSandbox.git'
assert_contains "$SCRIPT" '${CUBE_GITHUB_MIRROR_PREFIX}https://github.com/TencentCloud/CubeSandbox/releases/download/'
assert_contains "$SCRIPT" '${CUBE_GITHUB_MIRROR_PREFIX}https://github.com/tencentcloud/CubeSandbox/raw/master/deploy/one-click/online-install.sh'
assert_contains "$SCRIPT" "configure-docker-mirror"
assert_contains "$SCRIPT" "build-codeql-cpp-image"
assert_contains "$SCRIPT" "build-codeql-cpp-image-wsl"
assert_contains "$SCRIPT" "shell-codeql-cpp-image-wsl"
assert_contains "$SCRIPT" "create-codeql-cpp-template"
assert_contains "$SCRIPT" "codeql-cpp-smoke"
assert_contains "$SCRIPT" "CUBE_CODEQL_CPP_DOCKERFILE"
assert_contains "$SCRIPT" "CUBE_CODEQL_CPP_WSL_IMAGE"
assert_contains "$SCRIPT" "codeql-cpp.Dockerfile"
assert_not_contains "$SCRIPT" "cat > Dockerfile <<'DOCKERFILE'"
assert_contains "$SCRIPT" "CODEQL_DB_OK"

assert_contains "$OCI_DOCKERFILE" "FROM ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest"
assert_contains "$OCI_DOCKERFILE" 'ARG CUBE_LOCAL_REGISTRY_IMAGE'
assert_contains "$OCI_DOCKERFILE" 'ARG CUBE_CODEQL_BUNDLE_URL'
assert_contains "$OCI_DOCKERFILE" "mirrors.aliyun.com/debian"
assert_contains "$OCI_DOCKERFILE" "codeql resolve languages"

assert_contains "$OCI_README" ".cubesandbox/CubeSandbox/dev-env/README.md"
assert_contains "$OCI_README" ".cubesandbox/CubeSandbox/docker/README.md"
assert_contains "$OCI_README" "docs/cubesandbox-python-quickstart.md"
assert_contains "$OCI_README" "localhost/e2bdev/code-interpreter:ags"
assert_contains "$OCI_README" 'No matching Dockerfile for `sandbox-code:latest`'

set +e
"$SCRIPT" prepare-vm --toolbox >"$help_out" 2>&1
toolbox_rc=$?
set -e
[[ "$toolbox_rc" -ne 0 ]] || fail "prepare-vm --toolbox should fail"
assert_contains "$help_out" "unexpected extra argument(s): --toolbox"

assert_contains "$DOC" "WSL2"
assert_contains "$DOC" "m.daocloud.io/docker.io"
assert_contains "$DOC" "configure-docker-mirror"
assert_contains "$DOC" "oci/cubesandbox/codeql-cpp.Dockerfile"
assert_contains "$DOC" "build-codeql-cpp-image-wsl"
assert_contains "$DOC" "shell-codeql-cpp-image-wsl"
assert_contains "$DOC" "codeql-cpp-smoke"
assert_contains "$DOC" "tpl-a4d03d6bf9ac406e9fb6a457"
assert_not_contains "$DOC" "toolbox"
assert_not_contains "$DOC" "--toolbox"
