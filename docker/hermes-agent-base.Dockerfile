FROM ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie@sha256:b3c543b6c4f23a5f2df22866bd7857e5d304b67a564f4feab6ac22044dde719b AS uv_source
FROM tianon/gosu:1.19-trixie@sha256:3b176695959c71e123eb390d427efc665eeb561b1540e82679c15e992006b8b9 AS gosu_source
FROM debian:13.4

ARG VCS_REF=unknown
ARG HERMES_UPSTREAM_SHA=bf196a3fc0fd1f79353369e8732051db275c6276
ARG HERMES_SUBMODULE_STATUS=third_party/hermes-agent=bf196a3fc0fd1f79353369e8732051db275c6276;third_party/hermes-agent/tinker-atropos=65f084ee8054a5d02aeac76e24ed60388511c82b
ARG HERMES_SOURCE_DIGEST=sha256:e0c66b8305e844fcf469412d99f0016f35382d3bc1f04159a61319c67a5f63fc

LABEL org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://github.com/NousResearch/hermes-agent" \
      org.vulhunter.hermes.upstream_sha="${HERMES_UPSTREAM_SHA}" \
      org.vulhunter.hermes.submodules="${HERMES_SUBMODULE_STATUS}" \
      org.opencontainers.image.digest="${HERMES_SOURCE_DIGEST}"

ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/hermes/.playwright

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential nodejs npm python3 ripgrep ffmpeg gcc python3-dev libffi-dev procps git openssh-client docker-cli && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -u 10000 -m -d /opt/data hermes

COPY --chmod=0755 --from=gosu_source /gosu /usr/local/bin/
COPY --chmod=0755 --from=uv_source /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /opt/hermes

COPY third_party/hermes-agent/package.json third_party/hermes-agent/package-lock.json ./
COPY third_party/hermes-agent/web/package.json third_party/hermes-agent/web/package-lock.json web/

RUN npm install --prefer-offline --no-audit && \
    npx playwright install --with-deps chromium --only-shell && \
    (cd web && npm install --prefer-offline --no-audit) && \
    npm cache clean --force

COPY --chown=hermes:hermes third_party/hermes-agent/. .

RUN cd web && npm run build

USER hermes
RUN uv venv && \
    uv pip install --no-cache-dir -e ".[all]"

USER root
RUN mkdir -p /opt/bin
COPY --chmod=0755 backend/agents/shared/bin/healthcheck.sh /opt/bin/healthcheck.sh
COPY --chmod=0755 backend/agents/shared/bin/role-init.sh /opt/bin/role-init.sh

ENV HERMES_WEB_DIST=/opt/hermes/hermes_cli/web_dist
ENV HERMES_HOME=/opt/data
ENV PATH="/opt/data/.local/bin:${PATH}"

HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=5 \
    CMD ["sh", "/opt/bin/healthcheck.sh"]

VOLUME ["/opt/data"]
ENTRYPOINT ["/opt/hermes/docker/entrypoint.sh"]
CMD ["sh", "-c", "/opt/bin/role-init.sh && exec sleep infinity"]
