#!/usr/bin/env bash
set -euo pipefail

log_info() {
  echo "[INFO] $*"
}

log_info_err() {
  echo "[INFO] $*" >&2
}

log_warn() {
  echo "[WARN] $*" >&2
}

log_error() {
  echo "[ERROR] $*" >&2
}

detect_compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_BIN=(docker compose)
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_BIN=(docker-compose)
    return
  fi
  log_error "docker compose (or docker-compose) not found"
  exit 127
}

require_positive_int() {
  local name="$1"
  local value="$2"
  if ! [[ "$value" =~ ^[0-9]+$ ]] || [ "$value" -lt 1 ]; then
    log_error "${name} must be a positive integer, got: ${value}"
    exit 2
  fi
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

first_csv_item() {
  local csv="$1"
  local item
  IFS=',' read -r item _ <<<"$csv"
  trim "$item"
}

second_csv_item() {
  local csv="$1"
  local _ item
  IFS=',' read -r _ item _ <<<"$csv"
  trim "$item"
}

csv_item_or_last() {
  local csv="$1"
  local index="$2"
  local -a items=()
  local raw
  IFS=',' read -r -a raw <<<"$csv"
  local it
  if [ "${#raw[@]}" -gt 0 ]; then
    for it in "${raw[@]}"; do
      it="$(trim "$it")"
      [ -n "$it" ] && items+=("$it")
    done
  fi
  if [ "${#items[@]}" -eq 0 ]; then
    return 1
  fi
  if [ "$index" -lt "${#items[@]}" ]; then
    printf '%s' "${items[$index]}"
  else
    printf '%s' "${items[$((${#items[@]} - 1))]}"
  fi
}

count_csv_items() {
  local csv="$1"
  local -a raw=()
  IFS=',' read -r -a raw <<<"$csv"
  local count=0
  local it
  if [ "${#raw[@]}" -gt 0 ]; then
    for it in "${raw[@]}"; do
      it="$(trim "$it")"
      [ -n "$it" ] && count=$((count + 1))
    done
  fi
  printf '%s' "$count"
}

dedupe_csv() {
  local csv="$1"
  local -a raw=()
  local -a dedup=()
  IFS=',' read -r -a raw <<<"$csv"
  local item
  if [ "${#raw[@]}" -gt 0 ]; then
    for item in "${raw[@]}"; do
      item="$(trim "$item")"
      [ -z "$item" ] && continue
      local seen=0
      local existing
      if [ "${#dedup[@]}" -gt 0 ]; then
        for existing in "${dedup[@]}"; do
          if [ "$existing" = "$item" ]; then
            seen=1
            break
          fi
        done
      fi
      [ "$seen" -eq 0 ] && dedup+=("$item")
    done
  fi
  local out=""
  local i
  for i in "${!dedup[@]}"; do
    if [ "$i" -gt 0 ]; then
      out+=","
    fi
    out+="${dedup[$i]}"
  done
  printf '%s' "$out"
}

build_probe_url() {
  local kind="$1"
  local candidate="$2"
  local apt_codename="$3"
  case "$kind" in
    dockerhub)
      # docker.m.daocloud.io/library -> docker.m.daocloud.io
      # docker.io/library -> registry-1.docker.io (canonical Docker Hub registry host)
      local host="${candidate%%/*}"
      if [ "$host" = "docker.io" ] || [ "$host" = "index.docker.io" ]; then
        host="registry-1.docker.io"
      fi
      printf 'https://%s/v2/' "$host"
      ;;
    ghcr)
      printf 'https://%s/v2/' "$candidate"
      ;;
    npm)
      printf '%s/-/ping' "${candidate%/}"
      ;;
    pypi)
      if [[ "$candidate" == */simple || "$candidate" == */simple/ ]]; then
        printf '%s' "$candidate"
      else
        printf '%s/simple/' "${candidate%/}"
      fi
      ;;
    apt)
      printf 'https://%s/debian/dists/%s/Release' "$candidate" "$apt_codename"
      ;;
    apt-security)
      printf 'https://%s/debian-security/dists/%s-security/Release' "$candidate" "$apt_codename"
      ;;
    *)
      return 1
      ;;
  esac
}

probe_median_seconds() {
  local url="$1"
  local -a samples=()
  local i output code total

  for ((i = 1; i <= PROBE_ATTEMPTS; i++)); do
    output="$(curl -L -o /dev/null -sS \
      --connect-timeout "$PROBE_CONNECT_TIMEOUT_SECONDS" \
      --max-time "$PROBE_TIMEOUT_SECONDS" \
      -w '%{http_code} %{time_total}' "$url" || true)"
    code="${output%% *}"
    total="${output##* }"

    if [[ "$code" =~ ^[0-9]{3}$ ]] && [ "$code" != "000" ] && [[ "$total" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
      samples+=("$total")
    fi
  done

  if [ "${#samples[@]}" -eq 0 ]; then
    return 1
  fi

  printf '%s\n' "${samples[@]}" | sort -g | awk '
    { a[NR]=$1 }
    END {
      if (NR == 0) exit 1;
      if (NR % 2 == 1) {
        printf "%.6f", a[(NR+1)/2];
      } else {
        printf "%.6f", (a[NR/2] + a[NR/2+1]) / 2;
      }
    }
  '
}

rank_candidates() {
  local kind="$1"
  local label="$2"
  local candidates_csv="$3"
  local apt_codename="$4"

  candidates_csv="$(dedupe_csv "$candidates_csv")"
  if [ -z "$candidates_csv" ]; then
    return 1
  fi

  local tmp
  tmp="$(mktemp)"
  local raw
  IFS=',' read -r -a raw <<<"$candidates_csv"

  local candidate url median
  if [ "${#raw[@]}" -gt 0 ]; then
    for candidate in "${raw[@]}"; do
      candidate="$(trim "$candidate")"
      [ -z "$candidate" ] && continue

      if ! url="$(build_probe_url "$kind" "$candidate" "$apt_codename")"; then
        continue
      fi

      if median="$(probe_median_seconds "$url")"; then
      log_info_err "probe ${label}: ${candidate} median=${median}s url=${url}"
      printf '%s|%s\n' "$median" "$candidate" >>"$tmp"
      else
        log_warn "probe ${label}: ${candidate} failed url=${url}"
        printf '9999|%s\n' "$candidate" >>"$tmp"
      fi
    done
  fi

  if [ ! -s "$tmp" ]; then
    rm -f "$tmp"
    return 1
  fi

  local ranked
  ranked="$(sort -t'|' -g -k1,1 "$tmp" | cut -d'|' -f2 | paste -sd, -)"
  rm -f "$tmp"

  [ -n "$ranked" ] || return 1
  printf '%s' "$ranked"
}

rank_candidates_parallel() {
  local kind="$1"
  local label="$2"
  local candidates_csv="$3"
  local apt_codename="$4"

  candidates_csv="$(dedupe_csv "$candidates_csv")"
  if [ -z "$candidates_csv" ]; then
    return 1
  fi

  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local ranking_file
  ranking_file="$(mktemp)"
  local raw
  IFS=',' read -r -a raw <<<"$candidates_csv"

  local -a pids=()
  local -a result_files=()
  local candidate
  local index=0
  if [ "${#raw[@]}" -gt 0 ]; then
    for candidate in "${raw[@]}"; do
      candidate="$(trim "$candidate")"
      [ -z "$candidate" ] && continue

      local result_file="${tmp_dir}/probe-${index}.result"
      result_files+=("$result_file")
      (
        local url median
        if ! url="$(build_probe_url "$kind" "$candidate" "$apt_codename")"; then
          printf 'skip|||%s\n' "$candidate"
          exit 0
        fi

        if median="$(probe_median_seconds "$url")"; then
          printf 'ok|%s|%s|%s\n' "$median" "$candidate" "$url"
        else
          printf 'fail|9999|%s|%s\n' "$candidate" "$url"
        fi
      ) >"$result_file" &
      pids+=("$!")
      index=$((index + 1))
    done
  fi

  if [ "${#pids[@]}" -eq 0 ]; then
    rm -f "$ranking_file"
    rm -rf "$tmp_dir"
    return 1
  fi

  local pid
  if [ "${#pids[@]}" -gt 0 ]; then
    for pid in "${pids[@]}"; do
      if ! wait "$pid"; then
        log_warn "probe ${label}: worker exited unexpectedly pid=${pid}"
      fi
    done
  fi

  local result_line status median url
  if [ "${#result_files[@]}" -gt 0 ]; then
    for result_file in "${result_files[@]}"; do
      [ -f "$result_file" ] || continue
      result_line="$(cat "$result_file")"
      IFS='|' read -r status median candidate url <<<"$result_line"
      case "$status" in
        ok)
          log_info_err "probe ${label}: ${candidate} median=${median}s url=${url}"
          printf '%s|%s\n' "$median" "$candidate" >>"$ranking_file"
          ;;
        fail)
          log_warn "probe ${label}: ${candidate} failed url=${url}"
          printf '9999|%s\n' "$candidate" >>"$ranking_file"
          ;;
        *)
          ;;
      esac
    done
  fi

  rm -rf "$tmp_dir"

  if [ ! -s "$ranking_file" ]; then
    rm -f "$ranking_file"
    return 1
  fi

  local ranked
  ranked="$(sort -t'|' -g -k1,1 "$ranking_file" | cut -d'|' -f2 | paste -sd, -)"
  rm -f "$ranking_file"

  [ -n "$ranked" ] || return 1
  printf '%s' "$ranked"
}

choose_primary_fallback() {
  local ranked_csv="$1"
  local explicit_primary="$2"
  local explicit_fallback="$3"

  local primary fallback
  if [ -n "$explicit_primary" ]; then
    primary="$explicit_primary"
  else
    primary="$(first_csv_item "$ranked_csv")"
  fi

  if [ -n "$explicit_fallback" ]; then
    fallback="$explicit_fallback"
  else
    fallback="$(second_csv_item "$ranked_csv")"
    if [ -z "$fallback" ] || [ "$fallback" = "$primary" ]; then
      fallback="$(first_csv_item "$ranked_csv")"
    fi
  fi

  printf '%s|%s' "$primary" "$fallback"
}

run_with_retries() {
  local phase="$1"
  local retry_count="$2"
  local dockerhub_mirror="$3"
  local ghcr_registry="$4"
  local uv_image="$5"
  local sandbox_base_image="$6"
  local sandbox_image="$7"

  local attempt=1
  local rc=1
  while [ "$attempt" -le "$retry_count" ]; do
    log_info "Phase=${phase} attempt ${attempt}/${retry_count}"
    log_info "DOCKERHUB_LIBRARY_MIRROR=${dockerhub_mirror}"
    log_info "GHCR_REGISTRY=${ghcr_registry}"
    log_info "UV_IMAGE=${uv_image}"
    log_info "SANDBOX_BASE_IMAGE=${sandbox_base_image}"
    log_info "SANDBOX_IMAGE=${sandbox_image}"
    log_info "BACKEND_NPM_REGISTRY_PRIMARY=${BACKEND_NPM_REGISTRY_PRIMARY_SELECTED}"
    log_info "BACKEND_NPM_REGISTRY_FALLBACK=${BACKEND_NPM_REGISTRY_FALLBACK_SELECTED}"
    log_info "FRONTEND_NPM_REGISTRY=${FRONTEND_NPM_REGISTRY_SELECTED}"
    log_info "FRONTEND_NPM_REGISTRY_FALLBACK=${FRONTEND_NPM_REGISTRY_FALLBACK_SELECTED}"

    set +e
    DOCKERHUB_LIBRARY_MIRROR="${dockerhub_mirror}" \
      GHCR_REGISTRY="${ghcr_registry}" \
      UV_IMAGE="${uv_image}" \
      SANDBOX_BASE_IMAGE="${sandbox_base_image}" \
      SANDBOX_IMAGE="${sandbox_image}" \
      BACKEND_NPM_REGISTRY_PRIMARY="${BACKEND_NPM_REGISTRY_PRIMARY_SELECTED}" \
      BACKEND_NPM_REGISTRY_FALLBACK="${BACKEND_NPM_REGISTRY_FALLBACK_SELECTED}" \
      FRONTEND_NPM_REGISTRY="${FRONTEND_NPM_REGISTRY_SELECTED}" \
      FRONTEND_NPM_REGISTRY_FALLBACK="${FRONTEND_NPM_REGISTRY_FALLBACK_SELECTED}" \
      BACKEND_PYPI_INDEX_PRIMARY="${BACKEND_PYPI_INDEX_PRIMARY_SELECTED}" \
      BACKEND_PYPI_INDEX_FALLBACK="${BACKEND_PYPI_INDEX_FALLBACK_SELECTED}" \
      SANDBOX_PYPI_INDEX_PRIMARY="${SANDBOX_PYPI_INDEX_PRIMARY_SELECTED}" \
      SANDBOX_PYPI_INDEX_FALLBACK="${SANDBOX_PYPI_INDEX_FALLBACK_SELECTED}" \
      BACKEND_APT_MIRROR_PRIMARY="${BACKEND_APT_MIRROR_PRIMARY_SELECTED}" \
      BACKEND_APT_SECURITY_PRIMARY="${BACKEND_APT_SECURITY_PRIMARY_SELECTED}" \
      BACKEND_APT_MIRROR_FALLBACK="${BACKEND_APT_MIRROR_FALLBACK_SELECTED}" \
      BACKEND_APT_SECURITY_FALLBACK="${BACKEND_APT_SECURITY_FALLBACK_SELECTED}" \
      SANDBOX_APT_MIRROR_PRIMARY="${SANDBOX_APT_MIRROR_PRIMARY_SELECTED}" \
      SANDBOX_APT_SECURITY_PRIMARY="${SANDBOX_APT_SECURITY_PRIMARY_SELECTED}" \
      SANDBOX_APT_MIRROR_FALLBACK="${SANDBOX_APT_MIRROR_FALLBACK_SELECTED}" \
      SANDBOX_APT_SECURITY_FALLBACK="${SANDBOX_APT_SECURITY_FALLBACK_SELECTED}" \
      SANDBOX_NPM_REGISTRY_PRIMARY="${SANDBOX_NPM_REGISTRY_PRIMARY_SELECTED}" \
      SANDBOX_NPM_REGISTRY_FALLBACK="${SANDBOX_NPM_REGISTRY_FALLBACK_SELECTED}" \
      "${COMPOSE_BIN[@]}" "${COMPOSE_ARGS[@]}"
    rc=$?
    set -e

    if [ "$rc" -eq 0 ]; then
      log_info "Phase=${phase} succeeded on attempt ${attempt}"
      return 0
    fi

    log_warn "Phase=${phase} failed on attempt ${attempt}, exit_code=${rc}"
    if [ "$attempt" -lt "$retry_count" ]; then
      log_info "Retrying in ${RETRY_INTERVAL_SECONDS}s..."
      sleep "${RETRY_INTERVAL_SECONDS}"
    fi
    attempt=$((attempt + 1))
  done

  return "$rc"
}

detect_compose_cmd

if [ "$#" -eq 0 ]; then
  COMPOSE_ARGS=(up -d --build)
else
  COMPOSE_ARGS=("$@")
fi

export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"
export COMPOSE_DOCKER_CLI_BUILD="${COMPOSE_DOCKER_CLI_BUILD:-1}"

PHASE_RETRY_COUNT="${PHASE_RETRY_COUNT:-${CN_RETRY_COUNT:-3}}"
RETRY_INTERVAL_SECONDS="${RETRY_INTERVAL_SECONDS:-5}"
PROBE_ATTEMPTS="${PROBE_ATTEMPTS:-3}"
PROBE_TIMEOUT_SECONDS="${PROBE_TIMEOUT_SECONDS:-10}"
PROBE_CONNECT_TIMEOUT_SECONDS="${PROBE_CONNECT_TIMEOUT_SECONDS:-3}"
APT_PROBE_CODENAME="${APT_PROBE_CODENAME:-bookworm}"

require_positive_int "PHASE_RETRY_COUNT" "${PHASE_RETRY_COUNT}"
require_positive_int "RETRY_INTERVAL_SECONDS" "${RETRY_INTERVAL_SECONDS}"
require_positive_int "PROBE_ATTEMPTS" "${PROBE_ATTEMPTS}"
require_positive_int "PROBE_TIMEOUT_SECONDS" "${PROBE_TIMEOUT_SECONDS}"
require_positive_int "PROBE_CONNECT_TIMEOUT_SECONDS" "${PROBE_CONNECT_TIMEOUT_SECONDS}"

DOCKERHUB_CN_CANDIDATES_DEFAULT="${CN_DOCKERHUB_LIBRARY_MIRRORS:-${CN_DOCKERHUB_LIBRARY_MIRROR:-docker.m.daocloud.io/library,docker.1ms.run/library}}"
GHCR_CN_CANDIDATES_DEFAULT="${CN_GHCR_REGISTRIES:-${CN_GHCR_REGISTRY:-ghcr.nju.edu.cn,ghcr.m.daocloud.io}}"
DOCKERHUB_CANDIDATES_DEFAULT="${DOCKERHUB_LIBRARY_MIRROR_CANDIDATES:-${DOCKERHUB_CN_CANDIDATES_DEFAULT},${OFFICIAL_DOCKERHUB_LIBRARY_MIRROR:-docker.io/library}}"
GHCR_CANDIDATES_DEFAULT="${GHCR_REGISTRY_CANDIDATES:-${GHCR_CN_CANDIDATES_DEFAULT},${OFFICIAL_GHCR_REGISTRY:-ghcr.io}}"
BACKEND_NPM_CANDIDATES_DEFAULT="${BACKEND_NPM_REGISTRY_CANDIDATES:-https://registry.npmmirror.com,https://registry.npmjs.org}"
FRONTEND_NPM_CANDIDATES_DEFAULT="${FRONTEND_NPM_REGISTRY_CANDIDATES:-${BACKEND_NPM_CANDIDATES_DEFAULT}}"
SANDBOX_NPM_CANDIDATES_DEFAULT="${SANDBOX_NPM_REGISTRY_CANDIDATES:-${BACKEND_NPM_CANDIDATES_DEFAULT}}"
BACKEND_PYPI_CANDIDATES_DEFAULT="${BACKEND_PYPI_INDEX_CANDIDATES:-https://mirrors.aliyun.com/pypi/simple/,https://pypi.org/simple}"
SANDBOX_PYPI_CANDIDATES_DEFAULT="${SANDBOX_PYPI_INDEX_CANDIDATES:-${BACKEND_PYPI_CANDIDATES_DEFAULT}}"
BACKEND_APT_MIRROR_CANDIDATES_DEFAULT="${BACKEND_APT_MIRROR_CANDIDATES:-mirrors.aliyun.com,deb.debian.org}"
BACKEND_APT_SECURITY_CANDIDATES_DEFAULT="${BACKEND_APT_SECURITY_CANDIDATES:-mirrors.aliyun.com,security.debian.org}"
SANDBOX_APT_MIRROR_CANDIDATES_DEFAULT="${SANDBOX_APT_MIRROR_CANDIDATES:-mirrors.aliyun.com,deb.debian.org}"
SANDBOX_APT_SECURITY_CANDIDATES_DEFAULT="${SANDBOX_APT_SECURITY_CANDIDATES:-mirrors.aliyun.com,security.debian.org}"

if [ -n "${DOCKERHUB_LIBRARY_MIRROR:-}" ]; then
  DOCKERHUB_RANKED="$(dedupe_csv "${DOCKERHUB_LIBRARY_MIRROR},${DOCKERHUB_CANDIDATES_DEFAULT}")"
  log_info "skip probe dockerhub: explicit DOCKERHUB_LIBRARY_MIRROR=${DOCKERHUB_LIBRARY_MIRROR}"
else
  DOCKERHUB_RANKED="$(rank_candidates_parallel dockerhub dockerhub "${DOCKERHUB_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$DOCKERHUB_RANKED" ] || DOCKERHUB_RANKED="$(dedupe_csv "${DOCKERHUB_CANDIDATES_DEFAULT}")"
fi

if [ -n "${GHCR_REGISTRY:-}" ]; then
  GHCR_RANKED="$(dedupe_csv "${GHCR_REGISTRY},${GHCR_CANDIDATES_DEFAULT}")"
  log_info "skip probe ghcr: explicit GHCR_REGISTRY=${GHCR_REGISTRY}"
else
  GHCR_RANKED="$(rank_candidates_parallel ghcr ghcr "${GHCR_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$GHCR_RANKED" ] || GHCR_RANKED="$(dedupe_csv "${GHCR_CANDIDATES_DEFAULT}")"
fi

if [ -n "${BACKEND_NPM_REGISTRY_PRIMARY:-}" ] || [ -n "${BACKEND_NPM_REGISTRY_FALLBACK:-}" ]; then
  BACKEND_NPM_RANKED="$(dedupe_csv "${BACKEND_NPM_REGISTRY_PRIMARY:-},${BACKEND_NPM_REGISTRY_FALLBACK:-},${BACKEND_NPM_CANDIDATES_DEFAULT}")"
else
  BACKEND_NPM_RANKED="$(rank_candidates npm backend-npm "${BACKEND_NPM_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$BACKEND_NPM_RANKED" ] || BACKEND_NPM_RANKED="$(dedupe_csv "${BACKEND_NPM_CANDIDATES_DEFAULT}")"
fi

if [ -n "${FRONTEND_NPM_REGISTRY:-}" ] || [ -n "${FRONTEND_NPM_REGISTRY_FALLBACK:-}" ]; then
  FRONTEND_NPM_RANKED="$(dedupe_csv "${FRONTEND_NPM_REGISTRY:-},${FRONTEND_NPM_REGISTRY_FALLBACK:-},${FRONTEND_NPM_CANDIDATES_DEFAULT}")"
else
  FRONTEND_NPM_RANKED="$(rank_candidates npm frontend-npm "${FRONTEND_NPM_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$FRONTEND_NPM_RANKED" ] || FRONTEND_NPM_RANKED="$(dedupe_csv "${FRONTEND_NPM_CANDIDATES_DEFAULT}")"
fi

if [ -n "${SANDBOX_NPM_REGISTRY_PRIMARY:-}" ] || [ -n "${SANDBOX_NPM_REGISTRY_FALLBACK:-}" ]; then
  SANDBOX_NPM_RANKED="$(dedupe_csv "${SANDBOX_NPM_REGISTRY_PRIMARY:-},${SANDBOX_NPM_REGISTRY_FALLBACK:-},${SANDBOX_NPM_CANDIDATES_DEFAULT}")"
else
  SANDBOX_NPM_RANKED="$(rank_candidates npm sandbox-npm "${SANDBOX_NPM_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$SANDBOX_NPM_RANKED" ] || SANDBOX_NPM_RANKED="$(dedupe_csv "${SANDBOX_NPM_CANDIDATES_DEFAULT}")"
fi

if [ -n "${BACKEND_PYPI_INDEX_PRIMARY:-}" ] || [ -n "${BACKEND_PYPI_INDEX_FALLBACK:-}" ]; then
  BACKEND_PYPI_RANKED="$(dedupe_csv "${BACKEND_PYPI_INDEX_PRIMARY:-},${BACKEND_PYPI_INDEX_FALLBACK:-},${BACKEND_PYPI_CANDIDATES_DEFAULT}")"
else
  BACKEND_PYPI_RANKED="$(rank_candidates pypi backend-pypi "${BACKEND_PYPI_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$BACKEND_PYPI_RANKED" ] || BACKEND_PYPI_RANKED="$(dedupe_csv "${BACKEND_PYPI_CANDIDATES_DEFAULT}")"
fi

if [ -n "${SANDBOX_PYPI_INDEX_PRIMARY:-}" ] || [ -n "${SANDBOX_PYPI_INDEX_FALLBACK:-}" ]; then
  SANDBOX_PYPI_RANKED="$(dedupe_csv "${SANDBOX_PYPI_INDEX_PRIMARY:-},${SANDBOX_PYPI_INDEX_FALLBACK:-},${SANDBOX_PYPI_CANDIDATES_DEFAULT}")"
else
  SANDBOX_PYPI_RANKED="$(rank_candidates pypi sandbox-pypi "${SANDBOX_PYPI_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$SANDBOX_PYPI_RANKED" ] || SANDBOX_PYPI_RANKED="$(dedupe_csv "${SANDBOX_PYPI_CANDIDATES_DEFAULT}")"
fi

if [ -n "${BACKEND_APT_MIRROR_PRIMARY:-}" ] || [ -n "${BACKEND_APT_MIRROR_FALLBACK:-}" ]; then
  BACKEND_APT_MIRROR_RANKED="$(dedupe_csv "${BACKEND_APT_MIRROR_PRIMARY:-},${BACKEND_APT_MIRROR_FALLBACK:-},${BACKEND_APT_MIRROR_CANDIDATES_DEFAULT}")"
else
  BACKEND_APT_MIRROR_RANKED="$(rank_candidates apt backend-apt-main "${BACKEND_APT_MIRROR_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$BACKEND_APT_MIRROR_RANKED" ] || BACKEND_APT_MIRROR_RANKED="$(dedupe_csv "${BACKEND_APT_MIRROR_CANDIDATES_DEFAULT}")"
fi

if [ -n "${BACKEND_APT_SECURITY_PRIMARY:-}" ] || [ -n "${BACKEND_APT_SECURITY_FALLBACK:-}" ]; then
  BACKEND_APT_SECURITY_RANKED="$(dedupe_csv "${BACKEND_APT_SECURITY_PRIMARY:-},${BACKEND_APT_SECURITY_FALLBACK:-},${BACKEND_APT_SECURITY_CANDIDATES_DEFAULT}")"
else
  BACKEND_APT_SECURITY_RANKED="$(rank_candidates apt-security backend-apt-security "${BACKEND_APT_SECURITY_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$BACKEND_APT_SECURITY_RANKED" ] || BACKEND_APT_SECURITY_RANKED="$(dedupe_csv "${BACKEND_APT_SECURITY_CANDIDATES_DEFAULT}")"
fi

if [ -n "${SANDBOX_APT_MIRROR_PRIMARY:-}" ] || [ -n "${SANDBOX_APT_MIRROR_FALLBACK:-}" ]; then
  SANDBOX_APT_MIRROR_RANKED="$(dedupe_csv "${SANDBOX_APT_MIRROR_PRIMARY:-},${SANDBOX_APT_MIRROR_FALLBACK:-},${SANDBOX_APT_MIRROR_CANDIDATES_DEFAULT}")"
else
  SANDBOX_APT_MIRROR_RANKED="$(rank_candidates apt sandbox-apt-main "${SANDBOX_APT_MIRROR_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$SANDBOX_APT_MIRROR_RANKED" ] || SANDBOX_APT_MIRROR_RANKED="$(dedupe_csv "${SANDBOX_APT_MIRROR_CANDIDATES_DEFAULT}")"
fi

if [ -n "${SANDBOX_APT_SECURITY_PRIMARY:-}" ] || [ -n "${SANDBOX_APT_SECURITY_FALLBACK:-}" ]; then
  SANDBOX_APT_SECURITY_RANKED="$(dedupe_csv "${SANDBOX_APT_SECURITY_PRIMARY:-},${SANDBOX_APT_SECURITY_FALLBACK:-},${SANDBOX_APT_SECURITY_CANDIDATES_DEFAULT}")"
else
  SANDBOX_APT_SECURITY_RANKED="$(rank_candidates apt-security sandbox-apt-security "${SANDBOX_APT_SECURITY_CANDIDATES_DEFAULT}" "${APT_PROBE_CODENAME}" || true)"
  [ -n "$SANDBOX_APT_SECURITY_RANKED" ] || SANDBOX_APT_SECURITY_RANKED="$(dedupe_csv "${SANDBOX_APT_SECURITY_CANDIDATES_DEFAULT}")"
fi

IFS='|' read -r BACKEND_NPM_REGISTRY_PRIMARY_SELECTED BACKEND_NPM_REGISTRY_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${BACKEND_NPM_RANKED}" "${BACKEND_NPM_REGISTRY_PRIMARY:-}" "${BACKEND_NPM_REGISTRY_FALLBACK:-}")"
IFS='|' read -r FRONTEND_NPM_REGISTRY_SELECTED FRONTEND_NPM_REGISTRY_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${FRONTEND_NPM_RANKED}" "${FRONTEND_NPM_REGISTRY:-}" "${FRONTEND_NPM_REGISTRY_FALLBACK:-}")"
IFS='|' read -r SANDBOX_NPM_REGISTRY_PRIMARY_SELECTED SANDBOX_NPM_REGISTRY_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${SANDBOX_NPM_RANKED}" "${SANDBOX_NPM_REGISTRY_PRIMARY:-}" "${SANDBOX_NPM_REGISTRY_FALLBACK:-}")"
IFS='|' read -r BACKEND_PYPI_INDEX_PRIMARY_SELECTED BACKEND_PYPI_INDEX_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${BACKEND_PYPI_RANKED}" "${BACKEND_PYPI_INDEX_PRIMARY:-}" "${BACKEND_PYPI_INDEX_FALLBACK:-}")"
IFS='|' read -r SANDBOX_PYPI_INDEX_PRIMARY_SELECTED SANDBOX_PYPI_INDEX_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${SANDBOX_PYPI_RANKED}" "${SANDBOX_PYPI_INDEX_PRIMARY:-}" "${SANDBOX_PYPI_INDEX_FALLBACK:-}")"
IFS='|' read -r BACKEND_APT_MIRROR_PRIMARY_SELECTED BACKEND_APT_MIRROR_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${BACKEND_APT_MIRROR_RANKED}" "${BACKEND_APT_MIRROR_PRIMARY:-}" "${BACKEND_APT_MIRROR_FALLBACK:-}")"
IFS='|' read -r BACKEND_APT_SECURITY_PRIMARY_SELECTED BACKEND_APT_SECURITY_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${BACKEND_APT_SECURITY_RANKED}" "${BACKEND_APT_SECURITY_PRIMARY:-}" "${BACKEND_APT_SECURITY_FALLBACK:-}")"
IFS='|' read -r SANDBOX_APT_MIRROR_PRIMARY_SELECTED SANDBOX_APT_MIRROR_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${SANDBOX_APT_MIRROR_RANKED}" "${SANDBOX_APT_MIRROR_PRIMARY:-}" "${SANDBOX_APT_MIRROR_FALLBACK:-}")"
IFS='|' read -r SANDBOX_APT_SECURITY_PRIMARY_SELECTED SANDBOX_APT_SECURITY_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${SANDBOX_APT_SECURITY_RANKED}" "${SANDBOX_APT_SECURITY_PRIMARY:-}" "${SANDBOX_APT_SECURITY_FALLBACK:-}")"
IFS='|' read -r DOCKERHUB_LIBRARY_MIRROR_PRIMARY_SELECTED DOCKERHUB_LIBRARY_MIRROR_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${DOCKERHUB_RANKED}" "${DOCKERHUB_LIBRARY_MIRROR:-}" "")"
IFS='|' read -r GHCR_REGISTRY_PRIMARY_SELECTED GHCR_REGISTRY_FALLBACK_SELECTED \
  <<<"$(choose_primary_fallback "${GHCR_RANKED}" "${GHCR_REGISTRY:-}" "")"

DOCKERHUB_PHASES_COUNT="$(count_csv_items "${DOCKERHUB_RANKED}")"
GHCR_PHASES_COUNT="$(count_csv_items "${GHCR_RANKED}")"
PHASE_COUNT="$DOCKERHUB_PHASES_COUNT"
if [ "$GHCR_PHASES_COUNT" -gt "$PHASE_COUNT" ]; then
  PHASE_COUNT="$GHCR_PHASES_COUNT"
fi
[ "$PHASE_COUNT" -ge 1 ] || PHASE_COUNT=1

DEEPAUDIT_IMAGE_TAG="${DEEPAUDIT_IMAGE_TAG:-latest}"

log_info "Compose command: ${COMPOSE_BIN[*]}"
log_info "Compose args: ${COMPOSE_ARGS[*]}"
log_info "DOCKER_BUILDKIT=${DOCKER_BUILDKIT} COMPOSE_DOCKER_CLI_BUILD=${COMPOSE_DOCKER_CLI_BUILD}"
log_info "rank dockerhub=${DOCKERHUB_RANKED}"
log_info "selected dockerhub primary=${DOCKERHUB_LIBRARY_MIRROR_PRIMARY_SELECTED} fallback=${DOCKERHUB_LIBRARY_MIRROR_FALLBACK_SELECTED}"
log_info "rank ghcr=${GHCR_RANKED}"
log_info "selected ghcr primary=${GHCR_REGISTRY_PRIMARY_SELECTED} fallback=${GHCR_REGISTRY_FALLBACK_SELECTED}"
log_info "rank backend npm=${BACKEND_NPM_RANKED}"
log_info "rank frontend npm=${FRONTEND_NPM_RANKED}"
log_info "rank sandbox npm=${SANDBOX_NPM_RANKED}"
log_info "rank backend pypi=${BACKEND_PYPI_RANKED}"
log_info "rank sandbox pypi=${SANDBOX_PYPI_RANKED}"
log_info "rank backend apt main=${BACKEND_APT_MIRROR_RANKED}"
log_info "rank backend apt security=${BACKEND_APT_SECURITY_RANKED}"
log_info "rank sandbox apt main=${SANDBOX_APT_MIRROR_RANKED}"
log_info "rank sandbox apt security=${SANDBOX_APT_SECURITY_RANKED}"

for ((phase_index = 0; phase_index < PHASE_COUNT; phase_index++)); do
  dockerhub_mirror="$(csv_item_or_last "${DOCKERHUB_RANKED}" "${phase_index}")"
  ghcr_registry="$(csv_item_or_last "${GHCR_RANKED}" "${phase_index}")"

  if [ -n "${UV_IMAGE:-}" ]; then
    uv_image="${UV_IMAGE}"
  else
    uv_image="${ghcr_registry}/astral-sh/uv:latest"
  fi

  if [ -n "${SANDBOX_BASE_IMAGE:-}" ]; then
    sandbox_base_image="${SANDBOX_BASE_IMAGE}"
  else
    sandbox_base_image="${dockerhub_mirror}/python:3.12-slim"
  fi

  if [ -n "${SANDBOX_IMAGE:-}" ]; then
    sandbox_image="${SANDBOX_IMAGE}"
  else
    sandbox_image="${ghcr_registry}/lintsinghua/deepaudit-sandbox:${DEEPAUDIT_IMAGE_TAG}"
  fi

  phase_name="rank-$((phase_index + 1))"
  log_info "Phase=${phase_name} mirror selection dockerhub=${dockerhub_mirror} ghcr=${ghcr_registry}"
  if run_with_retries \
    "${phase_name}" \
    "${PHASE_RETRY_COUNT}" \
    "${dockerhub_mirror}" \
    "${ghcr_registry}" \
    "${uv_image}" \
    "${sandbox_base_image}" \
    "${sandbox_image}"; then
    exit 0
  fi

done

log_error "All ranked phases exhausted. Exiting with failure."
exit 1
