ARG CUBE_LOCAL_REGISTRY_IMAGE=m.daocloud.io/docker.io/library/registry:2
FROM ${CUBE_LOCAL_REGISTRY_IMAGE} AS dockerhub_mirror_probe
FROM ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest

ARG CUBE_CODEQL_BUNDLE_URL

ENV CODEQL_DIST_DIR=/opt/codeql
ENV PATH=/opt/codeql/codeql:${PATH}

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
    grep -R "URIs:\|^deb " /etc/apt/sources.list /etc/apt/sources.list.d 2>/dev/null || true; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl zstd xz-utils cmake make gcc g++ git bash file; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    test -n "${CUBE_CODEQL_BUNDLE_URL}"; \
    mkdir -p "${CODEQL_DIST_DIR}"; \
    curl -fL "${CUBE_CODEQL_BUNDLE_URL}" -o /tmp/codeql-bundle.tar.zst; \
    tar --use-compress-program=unzstd -xf /tmp/codeql-bundle.tar.zst -C "${CODEQL_DIST_DIR}"; \
    rm -f /tmp/codeql-bundle.tar.zst; \
    codeql version; \
    codeql resolve languages
