ARG CUBE_LOCAL_REGISTRY_IMAGE=m.daocloud.io/docker.io/library/registry:2
ARG CUBE_OPENGREP_BASE_IMAGE=m.daocloud.io/docker.io/library/debian:trixie-slim
ARG CUBE_ENVD_BASE_IMAGE=ghcr.io/tencentcloud/cubesandbox-base:2026.16
FROM ${CUBE_LOCAL_REGISTRY_IMAGE} AS dockerhub_mirror_probe
FROM ${CUBE_ENVD_BASE_IMAGE} AS cubesandbox_envd

FROM ${CUBE_OPENGREP_BASE_IMAGE}

ARG OPENGREP_VERSION=v1.20.0
ARG TARGETARCH

ENV ENVD_PORT=49983
ENV ENVD_LOG_FILE=/var/log/envd.log
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONUTF8=1
ENV OPENGREP_RULES_ROOT=/opt/opengrep/rules
ENV OPENGREP_RULES_ARCHIVE=/opt/opengrep/rules.tar.gz

RUN set -eux; \
    mkdir -p /etc/apt/disabled-sources.list.d; \
    find /etc/apt/sources.list.d -maxdepth 1 -type f \( -name '*cran*' -o -name '*r-project*' -o -name '*nodesource*' \) -exec mv {} /etc/apt/disabled-sources.list.d/ \; 2>/dev/null || true; \
    if [ -f /etc/apt/sources.list ]; then \
      sed -i \
        -e 's#http://deb.debian.org/debian#http://mirrors.aliyun.com/debian#g' \
        -e 's#https://deb.debian.org/debian#http://mirrors.aliyun.com/debian#g' \
        -e 's#http://security.debian.org/debian-security#http://mirrors.aliyun.com/debian-security#g' \
        -e 's#https://security.debian.org/debian-security#http://mirrors.aliyun.com/debian-security#g' \
        /etc/apt/sources.list; \
    fi; \
    find /etc/apt/sources.list.d -type f \( -name '*.list' -o -name '*.sources' \) -print0 2>/dev/null | xargs -0 -r sed -i \
      -e 's#http://deb.debian.org/debian#http://mirrors.aliyun.com/debian#g' \
      -e 's#https://deb.debian.org/debian#http://mirrors.aliyun.com/debian#g' \
      -e 's#http://security.debian.org/debian-security#http://mirrors.aliyun.com/debian-security#g' \
      -e 's#https://security.debian.org/debian-security#http://mirrors.aliyun.com/debian-security#g'; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl bash python3-minimal tar tini; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /opt/opengrep /scan /var/log

COPY --from=cubesandbox_envd /usr/bin/envd /usr/bin/envd

RUN set -eux; \
    ARCH="${TARGETARCH:-}"; \
    if [ -z "${ARCH}" ]; then ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"; fi; \
    case "${ARCH}" in \
      amd64|x86_64) OG_DIST="opengrep_manylinux_x86" ;; \
      arm64|aarch64) OG_DIST="opengrep_manylinux_aarch64" ;; \
      *) echo "unsupported arch: ${ARCH}" >&2; exit 1 ;; \
    esac; \
    download_with_fallback() { \
      output="$1"; shift; \
      for url in "$@"; do \
        echo "[opengrep] trying: ${url}"; \
        if curl -fL --connect-timeout 15 --max-time 600 --retry 2 --retry-delay 3 --retry-connrefused "${url}" -o "${output}.tmp"; then \
          mv "${output}.tmp" "${output}"; return 0; \
        fi; \
        rm -f "${output}.tmp"; \
      done; \
      return 1; \
    }; \
    download_with_fallback /opt/opengrep/opengrep.real \
      "https://gh-proxy.com/https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}" \
      "https://v6.gh-proxy.org/https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}" \
      "https://gh-proxy.org/https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}" \
      "https://github.com/opengrep/opengrep/releases/download/${OPENGREP_VERSION}/${OG_DIST}"; \
    chmod +x /opt/opengrep/opengrep.real; \
    printf '%s\n' '#!/bin/sh' \
      'unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy' \
      'export NO_PROXY=*' \
      'export no_proxy=*' \
      'exec /opt/opengrep/opengrep.real "$@"' \
      > /usr/local/bin/opengrep; \
    chmod +x /usr/local/bin/opengrep

COPY opengrep-scan.sh /usr/local/bin/opengrep-scan
COPY rules.tar.gz /opt/opengrep/rules.tar.gz

RUN set -eux; \
    chmod +x /usr/local/bin/opengrep-scan /usr/bin/envd; \
    printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'ENVD_BIN="${ENVD_BIN:-/usr/bin/envd}"' \
      'ENVD_PORT="${ENVD_PORT:-49983}"' \
      'ENVD_LOG_FILE="${ENVD_LOG_FILE:-/var/log/envd.log}"' \
      'ENVD_EXTRA_ARGS="${ENVD_EXTRA_ARGS:-}"' \
      '' \
      'start_envd() {' \
      '  if [ "${ENVD_LOG_FILE}" = "-" ]; then' \
      '    # shellcheck disable=SC2086' \
      '    "${ENVD_BIN}" -port "${ENVD_PORT}" ${ENVD_EXTRA_ARGS} &' \
      '  else' \
      '    mkdir -p "$(dirname "${ENVD_LOG_FILE}")"' \
      '    # shellcheck disable=SC2086' \
      '    "${ENVD_BIN}" -port "${ENVD_PORT}" ${ENVD_EXTRA_ARGS} >>"${ENVD_LOG_FILE}" 2>&1 &' \
      '  fi' \
      '  ENVD_PID=$!' \
      '  echo "opengrep-cube-entrypoint: started envd pid=${ENVD_PID} port=${ENVD_PORT}" >&2' \
      '}' \
      '' \
      'start_envd' \
      'if [ "$#" -eq 0 ]; then' \
      '  wait "${ENVD_PID}"' \
      '  exit $?' \
      'fi' \
      '' \
      'USER_PID=""' \
      'forward_signal() {' \
      '  sig="$1"' \
      '  if [ -n "${USER_PID}" ]; then' \
      '    kill -s "${sig}" "${USER_PID}" 2>/dev/null || true' \
      '  fi' \
      '}' \
      'trap '\''forward_signal TERM'\'' TERM' \
      'trap '\''forward_signal INT'\'' INT' \
      'trap '\''forward_signal HUP'\'' HUP' \
      '"$@" &' \
      'USER_PID=$!' \
      'wait "${USER_PID}"' \
      'exit $?' \
      > /usr/local/bin/opengrep-cube-entrypoint; \
    chmod +x /usr/local/bin/opengrep-cube-entrypoint; \
    mkdir -p /opt/opengrep/rules /scan; \
    /usr/local/bin/opengrep-scan --self-test; \
    rm -rf /tmp/* /var/cache/apt /usr/share/doc/* /usr/share/locale/* /usr/share/man/* 2>/dev/null || true

WORKDIR /scan
EXPOSE 49983
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/opengrep-cube-entrypoint"]
CMD []
