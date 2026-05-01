ARG DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
ARG BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_SECURITY_PRIMARY=mirrors.aliyun.com
ARG BACKEND_APT_MIRROR_FALLBACK=deb.debian.org
ARG BACKEND_APT_SECURITY_FALLBACK=security.debian.org
ARG CODEQL_BUNDLE_VERSION=2.20.5
ARG CODEQL_BUNDLE_ARCH=linux64

FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim-trixie AS codeql-runner

ARG BACKEND_APT_MIRROR_PRIMARY
ARG BACKEND_APT_SECURITY_PRIMARY
ARG BACKEND_APT_MIRROR_FALLBACK
ARG BACKEND_APT_SECURITY_FALLBACK
ARG CODEQL_BUNDLE_VERSION
ARG CODEQL_BUNDLE_ARCH

ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1 \
  CODEQL_DIST_DIR=/opt/codeql \
  PATH=/opt/codeql/codeql:${PATH}

RUN set -eux; \
  . /etc/os-release; \
  CODENAME="${VERSION_CODENAME:-trixie}"; \
  write_sources() { \
  main_host="$1"; security_host="$2"; \
  rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
  printf 'deb https://%s/debian %s main\n' "${main_host}" "${CODENAME}" > /etc/apt/sources.list; \
  printf 'deb https://%s/debian %s-updates main\n' "${main_host}" "${CODENAME}" >> /etc/apt/sources.list; \
  printf 'deb https://%s/debian-security %s-security main\n' "${security_host}" "${CODENAME}" >> /etc/apt/sources.list; \
  }; \
  install_runtime_packages() { \
  apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  ca-certificates curl unzip xz-utils zstd git bash make gcc g++ nodejs npm openjdk-21-jdk-headless maven gradle golang-go; \
  }; \
  write_sources "${BACKEND_APT_MIRROR_PRIMARY}" "${BACKEND_APT_SECURITY_PRIMARY}"; \
  if ! install_runtime_packages; then \
  rm -rf /var/lib/apt/lists/*; \
  write_sources "${BACKEND_APT_MIRROR_FALLBACK}" "${BACKEND_APT_SECURITY_FALLBACK}"; \
  install_runtime_packages; \
  fi; \
  rm -rf /var/lib/apt/lists/*

RUN set -eux; \
  mkdir -p ${CODEQL_DIST_DIR} /scan; \
  BUNDLE="codeql-bundle-${CODEQL_BUNDLE_ARCH}.tar.zst"; \
  URL_BASE="https://v6.gh-proxy.org/https://github.com/github/codeql-action/releases/download/codeql-bundle-v${CODEQL_BUNDLE_VERSION}"; \
  curl -fL "${URL_BASE}/${BUNDLE}" -o /tmp/codeql-bundle.tar.zst; \
  tar --use-compress-program=unzstd -xf /tmp/codeql-bundle.tar.zst -C ${CODEQL_DIST_DIR}; \
  rm -f /tmp/codeql-bundle.tar.zst; \
  codeql version; \
  codeql resolve languages

COPY docker/codeql-scan.sh /usr/local/bin/codeql-scan
COPY docker/codeql-compile-sandbox.sh /usr/local/bin/codeql-compile-sandbox
RUN chmod +x /usr/local/bin/codeql-scan /usr/local/bin/codeql-compile-sandbox \
  && codeql-scan --self-test \
  && codeql-compile-sandbox --self-test

WORKDIR /scan
CMD ["codeql-scan", "--self-test"]
