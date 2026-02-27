#!/usr/bin/env bash
set -u

bool_true() {
  local v
  v="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "$v" == "1" || "$v" == "true" || "$v" == "yes" || "$v" == "on" ]]
}

SYNC_ENABLED="${MCP_SOURCE_SYNC_ENABLED:-true}"
if ! bool_true "$SYNC_ENABLED"; then
  echo "ℹ️  MCP 源码同步已禁用（MCP_SOURCE_SYNC_ENABLED=${SYNC_ENABLED}）"
  exit 0
fi

SOURCE_ROOT="${MCP_SOURCE_ROOT:-/app/data/mcp/sources}"
SYNC_DEPTH="${MCP_SOURCE_SYNC_DEPTH:-1}"
SYNC_STRICT="${MCP_SOURCE_SYNC_STRICT:-false}"

mkdir -p "${SOURCE_ROOT}"

echo "📚 开始同步 MCP 源码到: ${SOURCE_ROOT}"

sync_repo() {
  local name="$1"
  local repo_url="$2"
  local branch="$3"
  local target="${SOURCE_ROOT}/${name}"

  if [ -d "${target}/.git" ]; then
    echo "🔄 更新 ${name} (${branch})"
    if ! git -C "${target}" fetch --depth "${SYNC_DEPTH}" origin "${branch}"; then
      return 1
    fi
    if ! git -C "${target}" checkout -q "${branch}"; then
      return 1
    fi
    if ! git -C "${target}" reset --hard "origin/${branch}"; then
      return 1
    fi
  else
    echo "⬇️  拉取 ${name} (${branch})"
    if ! git clone --depth "${SYNC_DEPTH}" --branch "${branch}" "${repo_url}" "${target}"; then
      return 1
    fi
  fi

  local commit_sha
  commit_sha="$(git -C "${target}" rev-parse --short HEAD 2>/dev/null || true)"
  echo "✅ ${name} 就绪 @ ${commit_sha:-unknown}"
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
