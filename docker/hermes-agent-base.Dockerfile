# Hermes Agent — 基于官方 nousresearch/hermes-agent 的派生镜像
# 官方镜像已包含: hermes CLI, Python 3.13, curl, git, jq, playwright
# 官方 entrypoint 已做: bootstrap config.yaml/.env/SOUL.md, skill sync, privilege drop
# 本层仅添加: 自定义 healthcheck + 角色 SOUL.md 覆盖脚本 + sleep infinity CMD

FROM nousresearch/hermes-agent:latest

USER root
RUN mkdir -p /opt/bin
COPY --chmod=755 backend/agents/shared/bin/healthcheck.sh /opt/bin/healthcheck.sh
COPY --chmod=755 backend/agents/shared/bin/role-init.sh /opt/bin/role-init.sh
USER root

HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=5 \
    CMD ["sh", "/opt/bin/healthcheck.sh"]

# 官方 entrypoint 以 root 启动 → chown /opt/data → gosu hermes → exec CMD
CMD ["sh", "-c", "/opt/bin/role-init.sh && exec sleep infinity"]
