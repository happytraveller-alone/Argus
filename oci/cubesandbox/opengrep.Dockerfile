ARG CUBE_LOCAL_REGISTRY_IMAGE=m.daocloud.io/docker.io/library/registry:2
FROM ${CUBE_LOCAL_REGISTRY_IMAGE} AS dockerhub_mirror_probe
FROM ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest

ARG OPENGREP_VERSION=v1.20.0
ARG TARGETARCH

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
        -e 's#http://deb.debian.org/debian#https://mirrors.aliyun.com/debian#g' \
        -e 's#https://deb.debian.org/debian#https://mirrors.aliyun.com/debian#g' \
        -e 's#http://security.debian.org/debian-security#https://mirrors.aliyun.com/debian-security#g' \
        -e 's#https://security.debian.org/debian-security#https://mirrors.aliyun.com/debian-security#g' \
        /etc/apt/sources.list; \
    fi; \
    find /etc/apt/sources.list.d -type f \( -name '*.list' -o -name '*.sources' \) -print0 2>/dev/null | xargs -0 -r sed -i \
      -e 's#http://deb.debian.org/debian#https://mirrors.aliyun.com/debian#g' \
      -e 's#https://deb.debian.org/debian#https://mirrors.aliyun.com/debian#g' \
      -e 's#http://security.debian.org/debian-security#https://mirrors.aliyun.com/debian-security#g' \
      -e 's#https://security.debian.org/debian-security#https://mirrors.aliyun.com/debian-security#g'; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl bash python3-minimal tar; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /opt/opengrep /scan

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
    chmod +x /usr/local/bin/opengrep-scan; \
    mkdir -p /opt/opengrep/rules /scan; \
    /usr/local/bin/opengrep-scan --self-test; \
    rm -rf /tmp/* /var/cache/apt /usr/share/doc/* /usr/share/locale/* /usr/share/man/* 2>/dev/null || true

WORKDIR /scan
CMD ["opengrep-scan", "--self-test"]
