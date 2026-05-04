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
    primary="${CUBE_CODEQL_BUNDLE_URL}"; \
    gh_url="$(printf '%s' "${primary}" | sed -E 's#^https?://[^/]+/(https?://github\.com/.*)$#\1#')"; \
    : "${gh_url:=${primary}}"; \
    download_with_fallback() { \
      output="$1"; shift; \
      for url in "$@"; do \
        echo "[codeql-bundle] trying: ${url}"; \
        if curl -fL --connect-timeout 15 --max-time 1500 --retry 3 --retry-delay 5 --retry-connrefused "${url}" -o "${output}.tmp"; then \
          mv "${output}.tmp" "${output}"; return 0; \
        fi; \
        rm -f "${output}.tmp"; \
      done; \
      return 1; \
    }; \
    download_with_fallback /tmp/codeql-bundle.tar.zst \
      "${primary}" \
      "https://gh-proxy.com/${gh_url}" \
      "https://gh-proxy.org/${gh_url}" \
      "https://v6.gh-proxy.org/${gh_url}" \
      "${gh_url}"; \
    tar --use-compress-program=unzstd -xf /tmp/codeql-bundle.tar.zst -C "${CODEQL_DIST_DIR}"; \
    rm -f /tmp/codeql-bundle.tar.zst; \
    # Slim the codeql distribution: cubemaster builds the template ext4 sized
    # to next_pow_of_2(rootfs+256MB)GiB. With all language packs the rootfs
    # straddles the 8GiB threshold and mkfs.ext4 fails ("No space left
    # while populating" while copying e.g. libjvm.so). We only run cpp scans,
    # so drop the non-cpp language extractor directories AND their qlpacks.
    # Together this saves ~3-4 GB and keeps rootfs comfortably under 7.75 GiB.
    cd "${CODEQL_DIST_DIR}/codeql"; \
    for lang in csharp go java javascript python ruby swift actions html xml ql; do \
      [ -d "${lang}" ] && rm -rf "${lang}"; \
    done; \
    if [ -d qlpacks/codeql ]; then \
      find qlpacks/codeql -mindepth 1 -maxdepth 1 -type d \
        ! -name 'cpp-*' ! -name 'shared-*' ! -name 'suite-helpers' \
        ! -name 'mad' ! -name 'meta' ! -name 'cwe-*' ! -name 'tutorial' \
        -exec rm -rf {} +; \
    fi; \
    cd /; \
    rm -rf /var/lib/apt/lists/* /var/cache/apt /usr/share/doc/* /usr/share/locale/* /usr/share/man/* /tmp/* 2>/dev/null || true; \
    codeql version; \
    codeql resolve languages || true
