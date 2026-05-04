ARG CUBE_LOCAL_REGISTRY_IMAGE=m.daocloud.io/docker.io/library/registry:2
FROM ${CUBE_LOCAL_REGISTRY_IMAGE} AS dockerhub_mirror_probe
FROM ccr.ccs.tencentyun.com/ags-image/sandbox-code:latest

ARG CUBE_CODEQL_BUNDLE_URL

ENV CODEQL_DIST_DIR=/opt/codeql
ENV PATH=/opt/codeql/codeql:${PATH}

# ── Stage 0: Slim the e2b/code-interpreter base image ──────────────────────
# `sandbox-code:latest` chains to `e2bdev/code-interpreter:ags` ->
# `python:3.12.13-trixie` (per oci/cubesandbox/README.md:65-80). That stack
# carries Jupyter, NumPy/Pandas/SciPy, ML frameworks, Node, and e2b runtime
# wiring. None of those are needed for cpp-only CodeQL extraction. The
# rootfs straddles 7.5 GiB, which makes mkfs.ext4 fail at the very last
# files when CubeMaster sizes the ext4 to next-pow-2(rootfs+256MB)GiB == 8 GiB
# (ext4 metadata at 8 GiB ≈ 460 MB, leaving ~50 MB for the final files).
#
# Trim each known-redundant tree in its own ignore-missing block so the
# build stays tolerant when upstream renames or removes a path.
RUN set -eux; \
    log_size() { du -sh "$1" 2>/dev/null || true; }; \
    drop()     { rm -rf "$@" 2>/dev/null || true; }; \
    echo "==== rootfs size BEFORE base-image slim ===="; du -sh / 2>/dev/null || true; \
    # e2b code-interpreter runtime + helper trees
    drop /opt/code-interpreter /opt/e2b /opt/jupyter /opt/notebooks /opt/ms-playwright; \
    # System Jupyter/IPython kernels and shares
    drop /usr/local/share/jupyter /usr/share/jupyter; \
    # Python data-science / ML packages (we only need Python's stdlib for build glue, if anything).
    # Walk every site-packages / dist-packages root the image carries.
    for pyroot in /usr/lib/python3*/dist-packages /usr/local/lib/python3*/dist-packages /usr/local/lib/python3*/site-packages /opt/python*/lib/python3*/site-packages; do \
      [ -d "$pyroot" ] || continue; \
      cd "$pyroot"; \
      drop \
        jupyter* notebook* ipykernel* IPython ipython* ipywidgets* nbformat* nbconvert* nbclient* \
        numpy pandas scipy sklearn scikit_learn* matplotlib seaborn plotly bokeh dash streamlit \
        torch* tensorflow* transformers* sentence_transformers* keras* xgboost* lightgbm* catboost* \
        pyarrow fastparquet duckdb* polars sqlglot* \
        PIL Pillow* pillow* cv2 opencv* skimage scikit_image* \
        pydeck altair* statsmodels* sympy networkx \
        spacy* nltk gensim* langchain* openai anthropic huggingface_hub; \
    done; \
    cd /; \
    # Bytecode caches across all Python trees
    find /usr /opt -depth -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true; \
    # Node ecosystem (codeql-cpp does not need node)
    drop /usr/local/lib/node_modules /usr/lib/node_modules /opt/yarn* /root/.npm /root/.yarn /root/.cache/yarn; \
    # Pip / package caches
    drop /root/.cache/pip /root/.cache/uv /root/.cache/huggingface /root/.cache/torch /root/.cache/matplotlib /root/.cache/fontconfig; \
    # Pre-existing system JVM (CodeQL ships its own JRE under /opt/codeql/tools)
    drop /usr/lib/jvm /opt/java /opt/jdk* /opt/jre*; \
    # Tencent / e2b-specific user trees not needed in scan VM
    drop /home/user/.cache /home/user/.npm /home/user/.pip /home/user/.local/lib/python*/site-packages/jupyter* /home/user/.ipython; \
    echo "==== rootfs size AFTER base-image slim ===="; du -sh / 2>/dev/null || true; \
    echo "==== top-15 dirs after slim ===="; du -h --max-depth=3 / 2>/dev/null | sort -h | tail -15 || true

# ── Stage 0.5: Aggressive non-essential cleanup (FINAL plan Phase 0) ───────
# Remove alternate-language runtimes and decoration content NOT needed for
# {CodeQL CLI extract+analyze cpp, gcc/cmake/make/git build chain, sandbox-code
# envd backend agent}. Stage 0 already trimmed Python ML libs; this stage hits
# the remaining ~642 MiB of bloat (deno / go / R / perl / python3.13 / fonts /
# icons). Python 3.11 and 3.12 are explicitly preserved (sandbox-code envd
# depends on Python); only python3.13 is dropped. A python-preserve sanity
# check FAILS the build if neither 3.11 nor 3.12 imports after the slim.
RUN set -eux; \
    drop()    { rm -rf "$@" 2>/dev/null || true; }; \
    log_size_at() { echo "==== $1: $(du -sh / 2>/dev/null | awk '{print $1}') ===="; }; \
    log_size_at "Stage 0.5 BEFORE"; \
    # Alternate language runtimes — not used by codeql-cpp scan
    drop /opt/deno; \
    drop /usr/lib/go-1.24 /usr/share/go-1.24 /usr/share/doc/golang-1.24-* /etc/profile.d/go-*; \
    drop /usr/lib/R /usr/share/R /usr/bin/R /usr/bin/Rscript; \
    drop /usr/share/perl5 /usr/share/perl /usr/lib/x86_64-linux-gnu/libperl* /usr/bin/perl /usr/bin/perl5*; \
    # python3.13 ONLY (3.11 / 3.12 preserved per R1 mitigation; AC2-gated)
    drop /usr/lib/python3.13 /usr/share/python3.13; \
    # Decoration not user-visible inside sandbox
    drop /usr/share/fonts /usr/share/icons /usr/share/gir-1.0 /usr/share/applications; \
    drop /usr/share/hwdata /usr/share/X11; \
    log_size_at "Stage 0.5 AFTER"; \
    # Python-preserve sanity check (R1): fail build if neither 3.11 nor 3.12 importable
    if ! { command -v python3.11 >/dev/null 2>&1 && python3.11 -c 'import sys' 2>/dev/null; } \
       && ! { command -v python3.12 >/dev/null 2>&1 && python3.12 -c 'import sys' 2>/dev/null; }; then \
      echo "ERROR Stage 0.5: neither python3.11 nor python3.12 importable after slim"; \
      command -v python3 >/dev/null 2>&1 && python3 --version || true; \
      exit 1; \
    fi; \
    echo "==== Stage 0.5 python-preserve sanity check OK ===="

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
        \( -name 'csharp-*' -o -name 'go-*' -o -name 'java-*' \
        -o -name 'javascript-*' -o -name 'python-*' -o -name 'ruby-*' \
        -o -name 'swift-*' -o -name 'actions-*' -o -name 'html-*' \
        -o -name 'ql-*' \) \
        -exec rm -rf {} +; \
    fi; \
    cd /; \
    # Trim CodeQL-side help, docs, and any leftover non-cpp resources.
    rm -rf "${CODEQL_DIST_DIR}/codeql/docs" "${CODEQL_DIST_DIR}/codeql/help" 2>/dev/null || true; \
    find "${CODEQL_DIST_DIR}/codeql" -maxdepth 3 -type d -name '__macosx' -prune -exec rm -rf {} + 2>/dev/null || true; \
    rm -rf /var/lib/apt/lists/* /var/cache/apt /usr/share/doc/* /usr/share/locale/* /usr/share/man/* /tmp/* 2>/dev/null || true; \
    codeql version; \
    codeql resolve languages || true; \
    echo "==== final rootfs size ===="; du -sh / 2>/dev/null || true; \
    echo "==== top-15 dirs at finish ===="; du -h --max-depth=3 / 2>/dev/null | sort -h | tail -15 || true
