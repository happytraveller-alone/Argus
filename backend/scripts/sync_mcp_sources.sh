#!/usr/bin/env bash
set -u

bool_true() {
  local v
  v="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "$v" == "1" || "$v" == "true" || "$v" == "yes" || "$v" == "on" ]]
}

trim() {
  echo "${1:-}" | xargs
}

add_unique() {
  local value="$1"
  local -n arr_ref="$2"
  local existing
  for existing in "${arr_ref[@]:-}"; do
    if [[ "${existing}" == "${value}" ]]; then
      return 0
    fi
  done
  arr_ref+=("${value}")
}

SYNC_ENABLED="${MCP_SOURCE_SYNC_ENABLED:-true}"
if ! bool_true "$SYNC_ENABLED"; then
  echo "ℹ️  MCP 源码同步已禁用（MCP_SOURCE_SYNC_ENABLED=${SYNC_ENABLED}）"
  exit 0
fi

SOURCE_ROOT="${MCP_SOURCE_ROOT:-/app/data/mcp/sources}"
SYNC_DEPTH="${MCP_SOURCE_SYNC_DEPTH:-1}"
SYNC_STRICT="${MCP_SOURCE_SYNC_STRICT:-false}"
GIT_MIRROR_ENABLED="${GIT_MIRROR_ENABLED:-true}"
GIT_MIRROR_PREFIX="${GIT_MIRROR_PREFIX:-https://gh-proxy.com}"
GIT_MIRROR_PREFIXES="${GIT_MIRROR_PREFIXES:-https://gh-proxy.com,https://v6.gh-proxy.org}"
GIT_MIRROR_HOSTS="${GIT_MIRROR_HOSTS:-github.com}"
GIT_MIRROR_ALLOW_AUTH_URL="${GIT_MIRROR_ALLOW_AUTH_URL:-false}"
GIT_MIRROR_FALLBACK_TO_ORIGIN="${GIT_MIRROR_FALLBACK_TO_ORIGIN:-false}"

mkdir -p "${SOURCE_ROOT}"

echo "📚 开始同步 MCP 源码到: ${SOURCE_ROOT}"
echo "🔧 GitHub 代理配置: enabled=${GIT_MIRROR_ENABLED}, prefixes=${GIT_MIRROR_PREFIXES}, fallback_to_origin=${GIT_MIRROR_FALLBACK_TO_ORIGIN}"

host_allowed_for_mirror() {
  local host="$1"
  local item
  IFS=',' read -ra _hosts <<< "${GIT_MIRROR_HOSTS}"
  for item in "${_hosts[@]}"; do
    item="$(trim "${item}")"
    if [[ -n "${item}" && "${host}" == "${item}" ]]; then
      return 0
    fi
  done
  return 1
}

url_has_auth() {
  local url="$1"
  local without_scheme="${url#*://}"
  local authority="${without_scheme%%/*}"
  [[ "${authority}" == *"@"* ]]
}

build_mirror_url_with_prefix() {
  local url="$1"
  local prefix="$2"
  prefix="${prefix%/}"
  printf "%s/%s" "${prefix}" "${url}"
}

should_use_mirror() {
  local url="$1"
  if ! bool_true "${GIT_MIRROR_ENABLED}"; then
    return 1
  fi
  if [[ "${url}" != http://* && "${url}" != https://* ]]; then
    return 1
  fi
  if ! bool_true "${GIT_MIRROR_ALLOW_AUTH_URL}" && url_has_auth "${url}"; then
    return 1
  fi
  local without_scheme="${url#*://}"
  local authority="${without_scheme%%/*}"
  local host="${authority##*@}"
  host="${host%%:*}"
  host_allowed_for_mirror "${host}"
}

collect_mirror_prefixes() {
  local raw_prefixes item
  raw_prefixes="$(trim "${GIT_MIRROR_PREFIXES}")"
  if [[ -n "${raw_prefixes}" ]]; then
    IFS=',' read -ra _prefixes <<< "${raw_prefixes}"
    for item in "${_prefixes[@]}"; do
      item="$(trim "${item}")"
      if [[ -n "${item}" ]]; then
        echo "${item}"
      fi
    done
    return 0
  fi

  item="$(trim "${GIT_MIRROR_PREFIX}")"
  if [[ -n "${item}" ]]; then
    echo "${item}"
  fi
}

build_candidate_urls() {
  local repo_url="$1"
  local -a candidates=()
  local prefix mirror_url

  if should_use_mirror "${repo_url}"; then
    while IFS= read -r prefix; do
      [[ -z "${prefix}" ]] && continue
      mirror_url="$(build_mirror_url_with_prefix "${repo_url}" "${prefix}")"
      if [[ -n "${mirror_url}" ]]; then
        add_unique "${mirror_url}" candidates
      fi
    done < <(collect_mirror_prefixes)

    if bool_true "${GIT_MIRROR_FALLBACK_TO_ORIGIN}"; then
      add_unique "${repo_url}" candidates
    fi
  else
    add_unique "${repo_url}" candidates
  fi

  if [[ "${#candidates[@]}" -eq 0 ]]; then
    add_unique "${repo_url}" candidates
  fi

  printf '%s\n' "${candidates[@]}"
}

sync_repo() {
  local name="$1"
  local repo_url="$2"
  local branch="$3"
  local target="${SOURCE_ROOT}/${name}"
  local -a candidates=()
  local candidate
  local using_origin=0

  mapfile -t candidates < <(build_candidate_urls "${repo_url}")
  if [[ "${#candidates[@]}" -eq 0 ]]; then
    candidates=("${repo_url}")
  fi
  echo "🔗 ${name} 候选源: ${candidates[*]}"
  if should_use_mirror "${repo_url}" && ! bool_true "${GIT_MIRROR_FALLBACK_TO_ORIGIN}"; then
    echo "🚫 ${name} 已禁用回源（GIT_MIRROR_FALLBACK_TO_ORIGIN=${GIT_MIRROR_FALLBACK_TO_ORIGIN}）"
  fi

  if [ -d "${target}/.git" ]; then
    echo "🔄 更新 ${name} (${branch})"
    local fetched=0
    local fetch_error=""
    for candidate in "${candidates[@]}"; do
      fetch_error="$(git -C "${target}" fetch --depth "${SYNC_DEPTH}" "${candidate}" "+refs/heads/${branch}:refs/remotes/origin/${branch}" 2>&1)"
      if [[ $? -eq 0 ]]; then
        fetched=1
        if [[ "${candidate}" == "${repo_url}" ]]; then
          using_origin=1
        fi
        break
      fi
      echo "⚠️  ${name} fetch 失败: ${candidate} (${fetch_error})"
    done
    if [[ ${fetched} -ne 1 ]]; then
      if should_use_mirror "${repo_url}" && ! bool_true "${GIT_MIRROR_FALLBACK_TO_ORIGIN}"; then
        echo "❌ ${name} 镜像全部失败，已按策略终止当前候选（未启用回源）"
      fi
      return 1
    fi
    if ! git -C "${target}" checkout -q -B "${branch}" "origin/${branch}" >/dev/null 2>&1; then
      return 1
    fi
  else
    echo "⬇️  拉取 ${name} (${branch})"
    local cloned=0
    local clone_error=""
    for candidate in "${candidates[@]}"; do
      clone_error="$(git clone --depth "${SYNC_DEPTH}" --branch "${branch}" "${candidate}" "${target}" 2>&1)"
      if [[ $? -eq 0 ]]; then
        cloned=1
        if [[ "${candidate}" == "${repo_url}" ]]; then
          using_origin=1
        else
          git -C "${target}" remote set-url origin "${repo_url}" >/dev/null 2>&1 || true
        fi
        break
      fi
      echo "⚠️  ${name} clone 失败: ${candidate} (${clone_error})"
    done
    if [[ ${cloned} -ne 1 ]]; then
      if should_use_mirror "${repo_url}" && ! bool_true "${GIT_MIRROR_FALLBACK_TO_ORIGIN}"; then
        echo "❌ ${name} 镜像全部失败，已按策略终止当前候选（未启用回源）"
      fi
      return 1
    fi
  fi

  local commit_sha
  commit_sha="$(git -C "${target}" rev-parse --short HEAD 2>/dev/null || true)"
  if [[ ${using_origin} -eq 1 ]]; then
    echo "✅ ${name} 就绪 @ ${commit_sha:-unknown} (origin)"
  else
    echo "✅ ${name} 就绪 @ ${commit_sha:-unknown} (mirror)"
  fi
  return 0
}

FAILED=0

if ! sync_repo "modelcontextprotocol-servers" "https://github.com/modelcontextprotocol/servers.git" "main"; then
  echo "⚠️  modelcontextprotocol-servers 同步失败"
  FAILED=1
fi

if ! sync_repo "code-index-mcp" "https://github.com/johnhuang316/code-index-mcp.git" "master"; then
  echo "⚠️  code-index-mcp 同步失败"
  FAILED=1
fi

if ! sync_repo "qmd" "https://github.com/tobi/qmd.git" "main"; then
  echo "⚠️  qmd 同步失败"
  FAILED=1
fi

if ! sync_repo "codebadger" "https://github.com/Lekssays/codebadger.git" "main"; then
  echo "⚠️  codebadger 同步失败"
  FAILED=1
fi

if [ "${FAILED}" -ne 0 ]; then
  if bool_true "${SYNC_STRICT}"; then
    echo "❌ MCP 源码同步失败（严格模式）"
    exit 1
  fi
  echo "⚠️  MCP 源码同步存在失败项，已按非严格模式继续启动"
else
  echo "🎉 MCP 源码同步完成"
fi

exit 0
